"""EventProcessor — 行情事件分派、Tick/KBar 處理、策略決策路由

職責：
- 接收 Broker Tick 回調，入隊處理
- 主迴圈從佇列取出事件分派到對應的 pipeline
- Tick 級：聚合器更新、orderbook 更新、硬停損、策略出場
- KBar 級：指標更新、收盤檢查、策略進場/出場
- MTF KBar（5m / 15m）指標更新
- 廣播 Tick / KBar / Signal 到 Dashboard
"""

import queue
import threading
from datetime import datetime
from typing import Any, Callable, Dict, Optional

from loguru import logger

from core.engine.models import EngineState, InstrumentPipeline
from core.market_data import MarketSnapshot
from core.position import Side
from strategy.base import Signal, SignalDirection
from strategy.filters import SessionManager, SessionPhase
from strategy.orderbook_features import OrderbookFeatures


class EventProcessor:
    """處理行情資料訂閱、Tick 分派、K 棒策略決策"""

    def __init__(self, engine: Any):
        self.engine = engine
        self._event_queue: queue.Queue = queue.Queue(maxsize=10000)
        self._thread: Optional[threading.Thread] = None
        self._running = False

        self._tick_count = 0
        self._heartbeat_count = 0
        self._sessions: Dict[str, SessionManager] = {}
        self._session_ended_today: str = ""

    # ━━━━━━━━━━━━━━━━ 生命週期 ━━━━━━━━━━━━━━━━

    def start(self):
        """啟動事件處理執行緒"""
        if self._thread and self._thread.is_alive():
            return
        self._running = True
        self._thread = threading.Thread(
            target=self._engine_loop, daemon=True, name="EngineEventThread"
        )
        self._thread.start()
        logger.info("[Event] 行情處理執行緒已啟動")

    def stop(self):
        """停止事件處理執行緒"""
        self._running = False
        if self._thread:
            self._thread.join(timeout=3.0)
            self._thread = None
        logger.info("[Event] 行情處理執行緒已停止")

    # ━━━━━━━━━━━━━━━━ Tick 回調（Broker 執行緒） ━━━━━━━━━━━━━━━━

    def on_tick(self, tick: Any):
        """Tick 回調 — 硬停損有最高優先級（從 Broker 執行緒呼叫）"""
        pos = self.engine.position_manager.positions.get(tick.instrument)
        is_urgent = False
        if pos and not pos.is_flat and pos.stop_loss > 0:
            if (pos.side == Side.LONG and tick.price <= pos.stop_loss) or \
               (pos.side == Side.SHORT and tick.price >= pos.stop_loss):
                is_urgent = True

        try:
            if is_urgent:
                self._event_queue.put(("tick", tick), timeout=0.1)
            else:
                self._event_queue.put_nowait(("tick", tick))
        except (queue.Full, Exception):
            if is_urgent:
                try:
                    self._event_queue.get_nowait()
                    self._event_queue.put_nowait(("tick", tick))
                except Exception:
                    pass

    # ━━━━━━━━━━━━━━━━ KBar 回調 ━━━━━━━━━━━━━━━━

    def on_kbar_complete(self, instrument: str, kbar: Any):
        """K 棒完成回調 — 放入佇列"""
        try:
            self._event_queue.put_nowait(("kbar", (instrument, kbar)))
        except queue.Full:
            logger.warning(
                f"[Queue] K 棒丟棄！{instrument} @ {kbar.datetime}"
                f" — 事件佇列已滿（{self._event_queue.qsize()}）"
            )

    def _on_kbar_5m_complete(self, instrument: str, kbar: Any):
        """5 分 K 完成 — 更新 MTF 指標"""
        pipeline = self.engine.pipelines.get(instrument)
        if not pipeline:
            return
        df = pipeline.aggregator.get_bars_dataframe(5, count=200)
        if len(df) >= 5:
            pipeline.snapshot_5m = pipeline.indicator_engine_5m.update(df)

    def _on_kbar_15m_complete(self, instrument: str, kbar: Any):
        """15 分 K 完成 — 更新 MTF 指標"""
        pipeline = self.engine.pipelines.get(instrument)
        if not pipeline:
            return
        df = pipeline.aggregator.get_bars_dataframe(15, count=200)
        if len(df) >= 5:
            pipeline.snapshot_15m = pipeline.indicator_engine_15m.update(df)

    # ━━━━━━━━━━━━━━━━ 主迴圈 ━━━━━━━━━━━━━━━━

    def _engine_loop(self):
        """引擎主迴圈 — 從佇列取事件分派"""
        logger.info("[Engine] event loop started")

        while self._running:
            try:
                event_type, data = self._event_queue.get(timeout=1.0)

                if event_type == "tick":
                    self._process_tick(data)
                elif event_type == "kbar":
                    instrument, kbar = data
                    self._process_kbar(instrument, kbar)

            except queue.Empty:
                self._heartbeat_count += 1
                if self._heartbeat_count % 60 == 0:
                    if hasattr(self.engine, 'health_monitor'):
                        self.engine.health_monitor.tick_heartbeat()
            except Exception as e:
                logger.error(f"引擎迴圈錯誤: {e}")

        logger.info("[Engine] event loop ended")

    # ━━━━━━━━━━━━━━━━ Tick 處理 ━━━━━━━━━━━━━━━━

    def _process_tick(self, tick: Any):
        """處理 Tick — 路由到對應的商品管線"""
        self._tick_count += 1

        instrument = tick.instrument
        pipeline = self.engine.pipelines.get(instrument)
        if not pipeline:
            return

        # 更新聚合器
        pipeline.aggregator.on_tick(tick)
        pipeline.orderbook_features = pipeline.orderbook_engine.update(tick)
        self._apply_orderbook_snapshot(
            pipeline.snapshot, pipeline.orderbook_features
        )

        # 更新持倉追蹤
        self.engine.position_manager.update_price(instrument, tick.price)

        # 更新 MockBroker 損益
        if hasattr(self.engine.broker, 'update_pnl'):
            prices = {
                inst: p.aggregator.current_price
                for inst, p in self.engine.pipelines.items()
            }
            total_pnl = self.engine.position_manager.get_total_unrealized_pnl(
                prices
            )
            self.engine.broker.update_pnl(total_pnl)

        # 盤中停損停利（每個 Tick 都檢查）
        self._check_tick_exit(instrument, tick, pipeline)

        # 廣播 Tick
        self.engine._broadcast("tick", {
            "instrument": instrument,
            "price": tick.price,
            "volume": tick.volume,
            "time": tick.datetime.isoformat(),
            "bid": tick.bid_price,
            "ask": tick.ask_price,
        })

        # 定期廣播完整狀態
        if self._tick_count % 10 == 0:
            self.engine._broadcast("state", self.engine.get_state())

    def _check_tick_exit(self, instrument: str, tick: Any,
                         pipeline: InstrumentPipeline):
        """Tick 級出場檢查：硬停損 → 策略出場"""
        pos = self.engine.position_manager.positions.get(instrument)
        if self.engine.state != EngineState.RUNNING:
            return
        if not pos or pos.is_flat:
            return

        # 快速硬停損
        hard_stop_hit = False
        if pos.stop_loss > 0:
            if pos.side == Side.LONG and tick.price <= pos.stop_loss:
                hard_stop_hit = True
            elif pos.side == Side.SHORT and tick.price >= pos.stop_loss:
                hard_stop_hit = True

        if hard_stop_hit:
            hard_signal = Signal(
                direction=SignalDirection.CLOSE,
                strength=1.0,
                stop_loss=0,
                take_profit=0,
                reason=f"硬停損 @ {tick.price:.0f}（停損價 {pos.stop_loss:.0f}）",
                source="hard_stop",
            )
            self.engine.executor.execute_exit(
                instrument, hard_signal, tick.price
            )
        else:
            # 策略出場檢查
            pipeline.snapshot.price = tick.price
            pipeline.snapshot.timestamp = tick.datetime
            exit_signal = pipeline.strategy.check_exit(pos, pipeline.snapshot)
            if exit_signal:
                self.engine.executor.execute_exit(
                    instrument, exit_signal, tick.price
                )

    # ━━━━━━━━━━━━━━━━ KBar 處理 ━━━━━━━━━━━━━━━━

    def _process_kbar(self, instrument: str, kbar: Any):
        """處理完成的 K 棒 — 更新指標 → 廣播 → 策略決策"""
        pipeline = self.engine.pipelines.get(instrument)
        if not pipeline:
            return

        # 更新指標
        df = pipeline.aggregator.get_bars_dataframe(
            self.engine.timeframe, count=200
        )
        if len(df) < 5:
            return

        pipeline.snapshot = pipeline.indicator_engine.update(df)
        self._apply_orderbook_snapshot(
            pipeline.snapshot, pipeline.orderbook_features
        )

        # 更新向後相容
        if instrument == self.engine.instruments[0]:
            self.engine.snapshot = pipeline.snapshot

        # 更新持倉 K 棒計數
        self.engine.position_manager.increment_bars(instrument)

        # 廣播 K 棒
        self.engine._broadcast("kbar", {
            "instrument": instrument,
            "time": kbar.datetime.isoformat(),
            "open": kbar.open,
            "high": kbar.high,
            "low": kbar.low,
            "close": kbar.close,
            "volume": kbar.volume,
            "interval": kbar.interval,
            "ema20": round(pipeline.snapshot.ema20, 1),
            "ema60": round(pipeline.snapshot.ema60, 1),
            "ema200": (
                round(pipeline.snapshot.ema200, 1)
                if hasattr(pipeline.snapshot, 'ema200')
                and pipeline.snapshot.ema200
                else None
            ),
        })

        # 廣播指標
        regime_info = {}
        if hasattr(pipeline.strategy, 'regime_classifier'):
            regime_info = pipeline.strategy.regime_classifier.get_regime_info()
        self.engine._broadcast("signal", {
            "instrument": instrument,
            "regime": regime_info,
            "signal_strength": (
                pipeline.strategy._last_signal_strength
                if hasattr(pipeline.strategy, '_last_signal_strength')
                else 0
            ),
            "adx": round(pipeline.snapshot.adx, 1),
            "rsi": round(pipeline.snapshot.rsi, 1),
            "atr": round(pipeline.snapshot.atr, 1),
            "ema20": round(pipeline.snapshot.ema20, 1),
            "ema60": round(pipeline.snapshot.ema60, 1),
        })

        if self.engine.state != EngineState.RUNNING:
            return

        # 收盤前強制平倉
        if self._check_session_close(instrument):
            return

        # 策略決策
        self._kbar_strategy_decision(instrument, kbar, pipeline)

    def _check_session_close(self, instrument: str) -> bool:
        """收盤前強制平倉檢查。回傳 True 表示已處理收盤，不需繼續策略決策。"""
        if instrument not in self._sessions:
            self._sessions[instrument] = SessionManager(instrument)
        session = self._sessions[instrument]
        phase = session.get_phase()
        minutes_left = session.minutes_to_close()

        if phase == SessionPhase.CLOSING or \
           (phase == SessionPhase.LAST_30 and minutes_left <= 5):
            pos = self.engine.position_manager.positions.get(instrument)
            if pos and not pos.is_flat:
                self.engine.executor.force_close(
                    instrument,
                    f"session close ({minutes_left}m left)",
                    self.engine.pipelines[instrument].snapshot.price,
                )
            if minutes_left <= 2:
                today = datetime.now().strftime("%Y-%m-%d")
                if self._session_ended_today != today:
                    if self.engine.performance and \
                       self.engine.position_manager:
                        try:
                            self.engine.performance.on_session_end(
                                self.engine.position_manager.balance
                            )
                            self._session_ended_today = today
                        except Exception:
                            pass
            return True
        return False

    def _kbar_strategy_decision(self, instrument: str, kbar: Any,
                                pipeline: InstrumentPipeline):
        """K 棒策略決策 — 出場優先、再檢查進場"""
        pos = self.engine.position_manager.positions.get(instrument)

        # 先檢查出場
        if pos and not pos.is_flat:
            exit_signal = pipeline.strategy.check_exit(
                pos, pipeline.snapshot
            )
            if exit_signal:
                self.engine.executor.execute_exit(
                    instrument, exit_signal, pipeline.snapshot.price
                )
                return
            unrealized = pos.unrealized_pnl(pipeline.snapshot.price)
            if self.engine.performance:
                self.engine.performance.on_signal_scan({
                    "type": "holding",
                    "message": (
                        f"[{instrument}] 持倉中 {pos.side.value}"
                        f" @ {pos.entry_price:.1f}"
                        f" | 未實現 {unrealized:+.0f}"
                        f" | K{pos.bars_since_entry}"
                    ),
                    "data": {
                        "instrument": instrument,
                        "unrealized": unrealized,
                        "bars": pos.bars_since_entry,
                    },
                })

        # 再檢查進場
        if pos and pos.is_flat:
            if hasattr(pipeline.strategy, 'update_orderbook_features'):
                pipeline.strategy.update_orderbook_features(
                    pipeline.orderbook_features
                )
            entry_signal = pipeline.strategy.on_kbar(
                kbar, pipeline.snapshot,
                snapshot_5m=pipeline.snapshot_5m,
                snapshot_15m=pipeline.snapshot_15m,
            )
            if entry_signal:
                if self.engine.auto_trade:
                    engine_execute_entry = getattr(type(self.engine), "_execute_entry", None)
                    if callable(engine_execute_entry):
                        self.engine._execute_entry(
                            instrument, entry_signal, pipeline
                        )
                    else:
                        self.engine.executor.execute_entry(
                            instrument, entry_signal, pipeline
                        )
                else:
                    logger.info(
                        f"[AutoTrade OFF] [{instrument}]"
                        f" 信號偵測但未自動進場: {entry_signal.reason}"
                    )
                    self.engine._broadcast("auto_trade_signal", {
                        "instrument": instrument,
                        "direction": (
                            "buy" if entry_signal.is_buy else "sell"
                        ),
                        "strength": round(entry_signal.strength, 2),
                        "reason": entry_signal.reason,
                        "stop_loss": entry_signal.stop_loss,
                        "take_profit": entry_signal.take_profit,
                    })
            else:
                signal_str = (
                    pipeline.strategy._last_signal_strength
                    if hasattr(pipeline.strategy, '_last_signal_strength')
                    else 0
                )
                if self.engine.performance:
                    self.engine.performance.on_signal_scan({
                        "type": "scan_no_signal",
                        "message": (
                            f"[{instrument}] K棒掃描"
                            f" | 訊號 {signal_str:.2f}"
                            f" | 價格 {pipeline.snapshot.price:.1f}"
                        ),
                        "data": {
                            "instrument": instrument,
                            "price": pipeline.snapshot.price,
                        },
                    })

    # ━━━━━━━━━━━━━━━━ 工具方法 ━━━━━━━━━━━━━━━━

    @staticmethod
    def _apply_orderbook_snapshot(snapshot: MarketSnapshot,
                                  features: OrderbookFeatures):
        """將 orderbook 特徵寫入 MarketSnapshot"""
        if not snapshot or not features:
            return
        snapshot.spread = features.spread
        snapshot.mid_price = features.mid_price
        snapshot.bid_ask_pressure = features.bid_ask_pressure
        snapshot.pressure_bias = features.pressure_bias
        snapshot.microprice_proxy = features.microprice_proxy
        snapshot.orderbook_ready = features.orderbook_ready
        snapshot.last_bid_price = features.last_bid_price
        snapshot.last_ask_price = features.last_ask_price
