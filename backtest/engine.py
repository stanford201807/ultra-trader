"""
UltraTrader 回測引擎
用歷史資料模擬策略運行，評估績效
"""

from datetime import datetime, timedelta
from typing import Optional, Callable
from dataclasses import dataclass, field

import pandas as pd
import numpy as np
from loguru import logger

from core.market_data import KBar, IndicatorEngine, Tick, MarketSnapshot
from core.position import PositionManager, Position, Side
from core.instrument_config import INSTRUMENT_SPECS
from strategy.base import BaseStrategy, Signal, SignalDirection
from strategy.momentum import AdaptiveMomentumStrategy
from strategy.mean_reversion import MeanReversionStrategy
from strategy.orderbook_features import OrderbookFeatureEngine, OrderbookFeatures
from strategy.filters import SessionPhase
from risk.manager import RiskManager
from risk.circuit_breaker import CircuitState
from core.broker import AccountInfo


@dataclass
class BacktestResult:
    """回測結果"""
    trades: list
    equity_curve: list[float]
    daily_pnl: dict  # date -> pnl
    total_bars: int = 0
    start_date: str = ""
    end_date: str = ""
    initial_balance: float = 100000.0
    final_balance: float = 100000.0
    orderbook_enabled: bool = False
    orderbook_metrics: dict = field(default_factory=dict)


class BacktestEngine:
    """
    回測引擎

    將歷史 K 棒資料逐根餵入策略 + 風控管道
    模擬真實交易流程，包含滑價和手續費
    """

    def __init__(
        self,
        initial_balance: float = 100000.0,
        slippage: int = 1,        # 滑價（點）
        commission: float = 18.0,  # 單邊手續費
        instrument: str = "TMF",  # 回測商品
        orderbook_tick_size: float = 1.0,
    ):
        self.initial_balance = initial_balance
        self.slippage = slippage
        self.commission = commission
        self.instrument = instrument
        self.orderbook_tick_size = max(0.1, orderbook_tick_size)

    def run(
        self,
        data: pd.DataFrame,
        strategy: Optional[BaseStrategy] = None,
        risk_profile: str = "balanced",
        use_orderbook_filter: bool = False,
    ) -> BacktestResult:
        """
        執行回測

        data: K 棒 DataFrame（columns: datetime, open, high, low, close, volume）
        strategy: 策略實例（預設用動量策略）
        risk_profile: 風險預設
        """
        if strategy is None:
            strategy = AdaptiveMomentumStrategy()

        # 初始化元件
        inst = self.instrument
        spec = INSTRUMENT_SPECS.get(inst)
        configs = {inst: spec} if spec else {}
        indicator_engine = IndicatorEngine(lookback_period=200)
        position_manager = PositionManager(
            instruments=[inst], configs=configs,
            initial_balance=self.initial_balance,
            auto_load=False,
        )
        risk_manager = RiskManager(profile=risk_profile)
        risk_manager._peak_equity = self.initial_balance
        # 回測模式：跳過即時盤別檢查（歷史資料有自己的時間戳）
        risk_manager._backtest_mode = True
        # 回測必須隔離實盤持久化風控狀態，避免被前一次交易污染
        risk_manager.circuit_breaker._daily_loss = 0.0
        risk_manager.circuit_breaker._consecutive_losses = 0
        risk_manager.circuit_breaker._state = CircuitState.ACTIVE
        risk_manager.circuit_breaker._halt_reason = ""
        risk_manager.circuit_breaker._cooldown_until = None
        risk_manager.circuit_breaker._trade_timestamps = []
        risk_manager.circuit_breaker._today = None
        orderbook_engine = OrderbookFeatureEngine(tick_size=self.orderbook_tick_size) if use_orderbook_filter else None

        # 讓策略的 SessionManager 使用 K 棒的時間而非 datetime.now()
        if hasattr(strategy, '_session'):
            original_get_phase = strategy._session.get_phase
            def backtest_get_phase(now=None):
                return original_get_phase(now=self._current_bar_time)
            strategy._session.get_phase = backtest_get_phase
        self._current_bar_time = None

        balance = self.initial_balance
        equity_curve = [balance]
        daily_pnl = {}
        previous_close = None
        checked_spreads: list[float] = []
        entry_spreads: list[float] = []
        orderbook_metrics = {
            "proxy_bars": 0,
            "entry_checks": 0,
            "entry_allowed": 0,
            "entry_rejected": 0,
            "fallback_allowed": 0,
            "avg_spread_checked": 0.0,
            "avg_spread_at_entry": 0.0,
        }

        logger.info(f"📊 回測開始 | 資料: {len(data)} 根K棒 | 策略: {strategy.name}")
        logger.info(
            f"💰 初始資金: {balance:,.0f} 元 | 風險: {risk_profile} | "
            f"orderbook={'on' if use_orderbook_filter else 'off'}"
        )

        # 逐根 K 棒跑
        for i in range(len(data)):
            # 取到目前為止的資料計算指標
            window = data.iloc[max(0, i - 199):i + 1].copy()
            if len(window) < 10:
                continue

            snapshot = indicator_engine.update(window)
            self._current_bar_time = data.iloc[i]["datetime"]
            kbar = KBar(
                datetime=data.iloc[i]["datetime"],
                open=float(data.iloc[i]["open"]),
                high=float(data.iloc[i]["high"]),
                low=float(data.iloc[i]["low"]),
                close=float(data.iloc[i]["close"]),
                volume=int(data.iloc[i]["volume"]),
            )

            if use_orderbook_filter and hasattr(strategy, "update_orderbook_features"):
                features = self._build_orderbook_proxy_features(kbar, previous_close, orderbook_engine)
                self._apply_orderbook_snapshot(snapshot, features)
                strategy.update_orderbook_features(features)
                orderbook_metrics["proxy_bars"] += 1

            # 更新部位追蹤
            position_manager.update_price(inst, kbar.close)
            position_manager.increment_bars(inst)

            # ---- 出場檢查 ----
            pos = position_manager.positions[inst]
            if not pos.is_flat:
                exit_signal = strategy.check_exit(pos, snapshot)
                if exit_signal:
                    exit_price = kbar.close
                    if self.slippage > 0:
                        if pos.side == Side.LONG:
                            exit_price -= self.slippage
                        else:
                            exit_price += self.slippage

                    trade = position_manager.close_position(inst, exit_price, exit_signal.reason, kbar.datetime)
                    if trade:
                        balance += trade.net_pnl
                        risk_manager.on_trade_closed(trade.net_pnl)

                        # 記錄每日損益
                        day = trade.exit_time.strftime("%Y-%m-%d")
                        daily_pnl[day] = daily_pnl.get(day, 0) + trade.net_pnl

            # ---- 進場檢查 ----
            pos = position_manager.positions[inst]
            if pos.is_flat:
                entry_signal = strategy.on_kbar(kbar, snapshot)
                if use_orderbook_filter:
                    decision_reason = getattr(strategy, "_last_orderbook_decision_reason", "")
                    decision_blocked = getattr(strategy, "_last_orderbook_blocked", False)
                    if decision_reason:
                        orderbook_metrics["entry_checks"] += 1
                        checked_spreads.append(snapshot.spread)
                        if decision_blocked:
                            orderbook_metrics["entry_rejected"] += 1
                        else:
                            orderbook_metrics["entry_allowed"] += 1
                            if "fallback" in decision_reason:
                                orderbook_metrics["fallback_allowed"] += 1
                if entry_signal:
                    # 風控評估
                    account = AccountInfo(
                        balance=balance,
                        equity=balance,
                        margin_available=balance,
                    )
                    decision = risk_manager.evaluate(
                        entry_signal, position_manager, account, snapshot,
                        instrument=inst,
                    )

                    if decision.approved:
                        entry_price = kbar.close
                        if self.slippage > 0:
                            if entry_signal.is_buy:
                                entry_price += self.slippage
                            else:
                                entry_price -= self.slippage

                        side = Side.LONG if entry_signal.is_buy else Side.SHORT
                        position_manager.open_position(
                            instrument=inst,
                            side=side,
                            price=entry_price,
                            quantity=decision.quantity,
                            stop_loss=entry_signal.stop_loss,
                            take_profit=entry_signal.take_profit,
                            timestamp=kbar.datetime,
                        )
                        if use_orderbook_filter:
                            entry_spreads.append(snapshot.spread)

            # 記錄權益曲線
            pos = position_manager.positions[inst]
            unrealized = pos.unrealized_pnl(kbar.close)
            equity_curve.append(balance + unrealized)
            previous_close = kbar.close

        # 收尾：強制平倉
        pos = position_manager.positions[inst]
        if not pos.is_flat:
            last_price = float(data.iloc[-1]["close"])
            trade = position_manager.close_position(inst, last_price, "回測結束平倉", data.iloc[-1]["datetime"])
            if trade:
                balance += trade.net_pnl

        result = BacktestResult(
            trades=[
                {
                    "entry_time": t.entry_time.isoformat() if isinstance(t.entry_time, datetime) else str(t.entry_time),
                    "exit_time": t.exit_time.isoformat() if isinstance(t.exit_time, datetime) else str(t.exit_time),
                    "side": t.side,
                    "entry_price": t.entry_price,
                    "exit_price": t.exit_price,
                    "quantity": t.quantity,
                    "pnl": round(t.net_pnl, 0),
                    "pnl_points": round(t.pnl_points, 0),
                    "reason": t.reason,
                    "bars_held": t.bars_held,
                }
                for t in position_manager.trades
            ],
            equity_curve=equity_curve,
            daily_pnl=daily_pnl,
            total_bars=len(data),
            start_date=str(data.iloc[0]["datetime"]),
            end_date=str(data.iloc[-1]["datetime"]),
            initial_balance=self.initial_balance,
            final_balance=balance,
            orderbook_enabled=use_orderbook_filter,
            orderbook_metrics=self._finalize_orderbook_metrics(
                orderbook_metrics,
                checked_spreads,
                entry_spreads,
            ),
        )

        logger.info(f"📊 回測完成 | 交易 {len(result.trades)} 筆 | 最終餘額: {balance:,.0f} 元")
        return result

    def run_orderbook_comparison(
        self,
        data: pd.DataFrame,
        strategy_factory: Optional[Callable[[], BaseStrategy]] = None,
        risk_profile: str = "balanced",
    ) -> dict[str, BacktestResult]:
        """同一資料集同時比較原策略與 orderbook filter 版本"""
        factory = strategy_factory or AdaptiveMomentumStrategy
        baseline = self.run(
            data=data,
            strategy=factory(),
            risk_profile=risk_profile,
            use_orderbook_filter=False,
        )
        filtered = self.run(
            data=data,
            strategy=factory(),
            risk_profile=risk_profile,
            use_orderbook_filter=True,
        )
        return {
            "baseline": baseline,
            "orderbook_filtered": filtered,
        }

    def _build_orderbook_proxy_features(
        self,
        kbar: KBar,
        previous_close: Optional[float],
        orderbook_engine: Optional[OrderbookFeatureEngine],
    ) -> OrderbookFeatures:
        """由 K 棒生成保守的 L1 orderbook proxy 特徵"""
        if orderbook_engine is None:
            return OrderbookFeatures()

        spread = self._estimate_proxy_spread(kbar)
        half_spread = spread / 2.0
        range_size = max(kbar.high - kbar.low, self.orderbook_tick_size)
        body = kbar.close - kbar.open
        close_position = (kbar.close - kbar.low) / range_size if range_size > 0 else 0.5

        start_mid = previous_close if previous_close is not None else kbar.open
        mid_2 = (kbar.open + kbar.close) / 2.0
        end_mid = kbar.close

        bullish_bias = body > 0 and close_position > 0.55
        bearish_bias = body < 0 and close_position < 0.45

        bid_offsets = [0.0, 0.0, 0.0]
        ask_offsets = [0.0, 0.0, 0.0]
        if bullish_bias:
            bid_offsets = [0.0, self.orderbook_tick_size * 0.5, self.orderbook_tick_size]
        elif bearish_bias:
            ask_offsets = [0.0, self.orderbook_tick_size * 0.5, self.orderbook_tick_size]

        mids = [start_mid, mid_2, end_mid]
        features = orderbook_engine.get_snapshot()
        for idx, mid in enumerate(mids):
            bid = mid - half_spread + bid_offsets[idx]
            ask = mid + half_spread + ask_offsets[idx]
            if bid > ask:
                ask = bid
            proxy_tick = Tick(
                datetime=kbar.datetime + timedelta(seconds=idx * 20),
                price=mid,
                volume=max(1, int(kbar.volume / 3)),
                bid_price=bid,
                ask_price=ask,
                instrument=self.instrument,
            )
            features = orderbook_engine.update(proxy_tick)
        return features

    def _estimate_proxy_spread(self, kbar: KBar) -> float:
        """用 K 棒波動與量能估計保守 spread"""
        bar_range = max(kbar.high - kbar.low, self.orderbook_tick_size)
        base_ticks = max(1.0, min(4.0, round(bar_range / max(self.orderbook_tick_size * 8.0, 1.0))))
        if kbar.volume < 20:
            base_ticks = min(4.0, base_ticks + 1.0)
        return float(base_ticks * self.orderbook_tick_size)

    @staticmethod
    def _apply_orderbook_snapshot(snapshot: MarketSnapshot, features: OrderbookFeatures):
        """將 proxy orderbook 特徵寫回 snapshot"""
        snapshot.spread = features.spread
        snapshot.mid_price = features.mid_price
        snapshot.bid_ask_pressure = features.bid_ask_pressure
        snapshot.pressure_bias = features.pressure_bias
        snapshot.microprice_proxy = features.microprice_proxy
        snapshot.orderbook_ready = features.orderbook_ready
        snapshot.last_bid_price = features.last_bid_price
        snapshot.last_ask_price = features.last_ask_price

    @staticmethod
    def _finalize_orderbook_metrics(metrics: dict, checked_spreads: list[float], entry_spreads: list[float]) -> dict:
        """整理 orderbook 回測統計"""
        metrics["avg_spread_checked"] = round(float(np.mean(checked_spreads)), 2) if checked_spreads else 0.0
        metrics["avg_spread_at_entry"] = round(float(np.mean(entry_spreads)), 2) if entry_spreads else 0.0
        return metrics
