import threading
from datetime import datetime, timedelta
from typing import Any, Callable, Optional, Dict
from loguru import logger
from core.position import PositionManager, Side, Position
from strategy.base import Signal, SignalDirection
from strategy.filters import SessionPhase, SessionManager
from core.logger import log_order, log_fill, log_pnl
from core.engine.models import InstrumentPipeline

class OrderExecutor:
    def __init__(self, engine: Any):
        self.engine = engine
        
        # 下單失敗冷卻（防止無限重試轟炸券商 API）
        self._order_fail_cooldown: dict[str, datetime] = {}
        self._ENTRY_FAIL_COOLDOWN_SEC = 60
        self._EXIT_FAIL_COOLDOWN_SEC = 30
        self._exit_fail_count: dict[str, int] = {}
        self._EXIT_MAX_RETRIES = 3
        self._exiting: set = set()
        self._exit_lock = threading.Lock()
        
        self._sessions: Dict[str, SessionManager] = {}

    @property
    def broker(self): return self.engine.broker

    @property
    def position_manager(self): return self.engine.position_manager

    @property
    def risk_manager(self): return self.engine.risk_manager

    @property
    def trading_mode(self): return self.engine.trading_mode
    
    @property
    def _broadcast(self): return self.engine._broadcast
    
    @property
    def performance(self): return self.engine.performance

    def _is_order_cooled_down(self, instrument: str) -> bool:
        cooldown_until = self._order_fail_cooldown.get(instrument)
        if cooldown_until and datetime.now() < cooldown_until:
            return True
        return False

    def _set_order_cooldown(self, instrument: str, seconds: int = None):
        cd = seconds or self._ENTRY_FAIL_COOLDOWN_SEC
        self._order_fail_cooldown[instrument] = datetime.now() + timedelta(seconds=cd)
        logger.warning(f"[Order] [{instrument}] 下單失敗，冷卻 {cd} 秒")

    def execute_entry(self, instrument: str, signal: Signal, pipeline: InstrumentPipeline):
        if instrument not in self._sessions:
            self._sessions[instrument] = SessionManager(instrument)
        phase = self._sessions[instrument].get_phase()
        if phase in (SessionPhase.CLOSED, SessionPhase.CLOSING):
            return

        if self._is_order_cooled_down(instrument):
            return

        price = pipeline.snapshot.price
        strategy_name = pipeline.strategy.name if hasattr(pipeline.strategy, 'name') else pipeline.strategy.__class__.__name__
        market_regime = "unknown"
        if hasattr(pipeline.strategy, 'regime_classifier'):
            regime = getattr(pipeline.strategy.regime_classifier, 'current_regime', None)
            if regime:
                market_regime = getattr(regime, 'value', str(regime))

        if self.trading_mode == "paper":
            if self.risk_manager and not self.risk_manager.circuit_breaker.can_trade:
                logger.info(f"[PAPER] [{instrument}] 熔斷中，跳過進場")
                return

            action = "BUY" if signal.is_buy else "SELL"
            side = Side.LONG if signal.is_buy else Side.SHORT
            logger.info(f"[PAPER] [{instrument}] {action} | strength {signal.strength:.2f} | {signal.reason}")

            self.position_manager.open_position(
                instrument=instrument,
                side=side,
                price=price,
                quantity=1,
                stop_loss=signal.stop_loss,
                take_profit=signal.take_profit,
                take_profit_levels=signal.take_profit_levels,
                strategy=strategy_name,
                market_regime=market_regime,
                signal_strength=signal.strength,
            )

            signal_data = {
                "time": datetime.now().isoformat(),
                "instrument": instrument,
                "action": action.lower(),
                "price": price,
                "quantity": 1,
                "reason": signal.reason,
                "signal_strength": round(signal.strength, 2),
                "stop_loss": signal.stop_loss,
                "take_profit": signal.take_profit,
            }
            self._broadcast("trade", {**signal_data, "reason": f"[PAPER] {signal.reason}"})
            if self.performance:
                self.performance.on_paper_signal(signal_data)
            return

        account = self.broker.get_account_info()
        if account.balance <= 0 and account.equity <= 0:
            pm_balance = self.position_manager.balance
            account.balance = pm_balance
            account.equity = pm_balance + self.position_manager.get_total_unrealized_pnl({})
            
        decision = self.risk_manager.evaluate(
            signal, self.position_manager, account, pipeline.snapshot, instrument=instrument
        )

        if not decision.approved:
            logger.info(f"[Risk] [{instrument}] rejected: {decision.rejection_reason}")
            return

        action = "BUY" if signal.is_buy else "SELL"
        log_order(action, price, decision.quantity, f"MKT {instrument}")

        result = self.broker.place_order(
            action=action,
            quantity=decision.quantity,
            price_type="MKT",
            instrument=instrument,
        )

        if not result.success:
            logger.error(f"[Order] [{instrument}] failed: {result.message}")
            self._set_order_cooldown(instrument)
            return

        fill_price = result.fill_price if result.fill_price > 0 else price
        side = Side.LONG if signal.is_buy else Side.SHORT

        try:
            self.position_manager.open_position(
                instrument=instrument,
                side=side,
                price=fill_price,
                quantity=decision.quantity,
                stop_loss=signal.stop_loss,
                take_profit=signal.take_profit,
                take_profit_levels=signal.take_profit_levels,
                strategy=strategy_name,
                market_regime=market_regime,
                signal_strength=signal.strength,
            )
        except Exception as e:
            logger.critical(f"[GHOST] [{instrument}] 開倉記錄失敗: {e} — 嘗試反向平倉")
            try:
                reverse = "SELL" if action == "BUY" else "BUY"
                self.broker.place_order(action=reverse, quantity=decision.quantity, price_type="MKT", instrument=instrument)
            except Exception as e2:
                logger.critical(f"[GHOST] [{instrument}] 反向平倉也失敗: {e2} — 請手動處理！")
            return

        log_fill(action, fill_price, decision.quantity)
        self._broadcast("trade", {
            "time": datetime.now().isoformat(),
            "instrument": instrument,
            "action": action.lower(),
            "price": fill_price,
            "quantity": decision.quantity,
            "stop_loss": signal.stop_loss,
            "take_profit": signal.take_profit,
            "reason": signal.reason,
            "signal_strength": round(signal.strength, 2),
        })

    def execute_exit(self, instrument: str, signal: Signal, price: float):
        with self._exit_lock:
            if instrument in self._exiting:
                return
            self._exiting.add(instrument)

        try:
            self._execute_exit_inner(instrument, signal, price)
        finally:
            with self._exit_lock:
                self._exiting.discard(instrument)

    def _execute_exit_inner(self, instrument: str, signal: Signal, price: float):
        pos = self.position_manager.positions.get(instrument)
        if not pos or pos.is_flat:
            return

        is_hard_stop = getattr(signal, 'source', '') == 'hard_stop'
        is_session_close = '收盤' in getattr(signal, 'reason', '')
        if self._is_order_cooled_down(instrument):
            if not is_hard_stop and not is_session_close:
                return
            logger.warning(f"[Order] [{instrument}] 冷卻中但硬停損/收盤強制執行")

        if self.trading_mode == "paper":
            action = "SELL" if pos.side == Side.LONG else "BUY"
            pnl = round(pos.unrealized_pnl(price), 0)
            logger.info(f"[PAPER] [{instrument}] CLOSE {action} | PnL={pnl} | {signal.reason}")

            trade = self.position_manager.close_position(instrument, price, f"[PAPER] {signal.reason}")
            self._broadcast("trade", {
                "time": datetime.now().isoformat(),
                "instrument": instrument,
                "action": "close",
                "price": price,
                "pnl": trade.net_pnl if trade else pnl,
                "reason": f"[PAPER] {signal.reason}",
                "side": pos.side.value,
            })

            if trade and self.risk_manager:
                self.risk_manager.on_trade_closed(trade.net_pnl)

            if self.performance:
                if trade:
                    self.performance.on_trade_closed(trade.to_perf_dict())
                else:
                    self.performance.on_paper_signal({
                        "time": datetime.now().isoformat(),
                        "instrument": instrument,
                        "action": "close",
                        "price": price,
                        "reason": signal.reason,
                    })
            return

        action = "SELL" if pos.side == Side.LONG else "BUY"
        log_order(action, price, pos.quantity, f"MKT 平倉 {instrument}")

        result = self.broker.place_order(action=action, quantity=pos.quantity, price_type="MKT", instrument=instrument)

        if not result.success:
            fail_count = self._exit_fail_count.get(instrument, 0) + 1
            self._exit_fail_count[instrument] = fail_count
            logger.error(f"[Order] [{instrument}] close failed ({fail_count}/{self._EXIT_MAX_RETRIES}): {result.message}")

            if fail_count >= self._EXIT_MAX_RETRIES:
                logger.critical(f"[EMERGENCY] [{instrument}] 出場連續失敗 {fail_count} 次！強制重置持倉狀態")
                self.position_manager.positions[instrument] = Position()
                if instrument == self.position_manager.instruments[0]:
                    self.position_manager.position = self.position_manager.positions[instrument]
                self._exit_fail_count[instrument] = 0
                self._set_order_cooldown(instrument, 300)
            else:
                self._set_order_cooldown(instrument, self._EXIT_FAIL_COOLDOWN_SEC)
            return

        self._exit_fail_count[instrument] = 0
        fill_price = result.fill_price if result.fill_price > 0 else price
        try:
            trade = self.position_manager.close_position(instrument, fill_price, signal.reason)
        except Exception as e:
            logger.critical(f"[GHOST] [{instrument}] 平倉記錄失敗: {e} — 強制重置持倉")
            self.position_manager.positions[instrument] = Position()
            return

        if trade:
            log_pnl(trade.net_pnl, f"[{instrument}] {signal.reason}")
            # MockBroker 處理可以移出，或由外層事件處理，這裡為了相容保留
            if hasattr(self.broker, "update_balance"):
                self.broker.update_balance(trade.pnl)

            self.risk_manager.on_trade_closed(trade.net_pnl)
            if self.performance:
                self.performance.on_trade_closed(trade.to_perf_dict())

            self._broadcast("trade", {
                "time": datetime.now().isoformat(),
                "instrument": instrument,
                "action": "close",
                "price": fill_price,
                "pnl": round(trade.net_pnl, 0),
                "pnl_points": round(trade.pnl_points, 1),
                "reason": signal.reason,
                "side": trade.side,
            })

    def force_close(self, instrument: str, reason: str, price: float):
        signal = Signal(direction=SignalDirection.CLOSE, strength=1.0, stop_loss=0, take_profit=0, reason=reason, source="Engine")
        self.execute_exit(instrument, signal, price)

    def manual_open(self, instrument: str, side: str, quantity: int = 1,
                    stop_loss: float = 0, take_profit: float = 0) -> dict:
        """手動建倉（Dashboard 手動下單用）

        Args:
            instrument: 商品代碼
            side: 方向 "BUY" 或 "SELL"
            quantity: 口數
            stop_loss: 停損價（0 = 不設定）
            take_profit: 停利價（0 = 不設定）

        Returns:
            {"status": "ok", ...} 或 {"error": "..."}
        """
        if side not in ("BUY", "SELL"):
            return {"error": f"無效方向: {side}，需要 BUY 或 SELL"}

        pipeline = self.engine.pipelines.get(instrument)
        if not pipeline:
            return {"error": f"找不到商品管線: {instrument}"}

        price = pipeline.snapshot.price
        if price <= 0:
            return {"error": f"商品 {instrument} 目前無報價"}

        is_buy = (side == "BUY")
        side_enum = Side.LONG if is_buy else Side.SHORT
        strategy_name = "manual"

        if self.trading_mode == "paper":
            # Paper 模式：直接開虛擬倉
            try:
                self.position_manager.open_position(
                    instrument=instrument,
                    side=side_enum,
                    price=price,
                    quantity=quantity,
                    stop_loss=stop_loss,
                    take_profit=take_profit,
                    strategy=strategy_name,
                )
            except Exception as e:
                return {"error": f"開倉失敗: {e}"}

            self._broadcast("trade", {
                "time": datetime.now().isoformat(),
                "instrument": instrument,
                "action": side.lower(),
                "price": price,
                "quantity": quantity,
                "stop_loss": stop_loss,
                "take_profit": take_profit,
                "reason": "手動進場（Paper）",
            })
            return {"status": "ok", "price": price, "quantity": quantity, "mode": "paper"}

        # Live / Simulation 模式：透過 Broker 下單
        result = self.broker.place_order(
            action=side,
            quantity=quantity,
            price_type="MKT",
            instrument=instrument,
        )
        if not result.success:
            return {"error": f"下單失敗: {result.message}"}

        fill_price = result.fill_price if result.fill_price > 0 else price
        try:
            self.position_manager.open_position(
                instrument=instrument,
                side=side_enum,
                price=fill_price,
                quantity=quantity,
                stop_loss=stop_loss,
                take_profit=take_profit,
                strategy=strategy_name,
            )
        except Exception as e:
            logger.critical(f"[GHOST] [{instrument}] 手動開倉記錄失敗: {e}")
            return {"error": f"開倉記錄失敗: {e}"}

        self._broadcast("trade", {
            "time": datetime.now().isoformat(),
            "instrument": instrument,
            "action": side.lower(),
            "price": fill_price,
            "quantity": quantity,
            "stop_loss": stop_loss,
            "take_profit": take_profit,
            "reason": "手動進場",
        })
        return {"status": "ok", "price": fill_price, "quantity": quantity}

    def manual_close(self, instrument: str, is_simulation: bool = None) -> dict:
        """手動平倉（委派 force_close）"""
        pipeline = self.engine.pipelines.get(instrument)
        price = pipeline.snapshot.price if pipeline else 0
        pos = self.position_manager.positions.get(instrument)
        if not pos or pos.is_flat:
            return {"error": f"{instrument} 目前無持倉"}
        self.force_close(instrument, "手動平倉", price)
        return {"status": "ok", "instrument": instrument}
