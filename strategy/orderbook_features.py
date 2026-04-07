"""
UltraTrader L1 orderbook 特徵引擎
由 bid/ask tick 序列產生可供策略使用的即時特徵
"""

from collections import deque
from dataclasses import dataclass

from core.market_data import Tick


@dataclass
class OrderbookFeatures:
    """L1 orderbook 特徵快照"""
    spread: float = 0.0
    mid_price: float = 0.0
    bid_change: float = 0.0
    ask_change: float = 0.0
    bid_ask_pressure: float = 0.0
    pressure_score: int = 0
    pressure_bias: str = "neutral"
    microprice_proxy: float = 0.0
    orderbook_ready: bool = False
    last_bid_price: float = 0.0
    last_ask_price: float = 0.0
    ticks_seen: int = 0


class OrderbookFeatureEngine:
    """根據 L1 bid/ask 變化計算 orderbook 特徵"""

    def __init__(self, window_size: int = 20, tick_size: float = 1.0, bias_threshold: int = 2):
        self.window_size = max(2, window_size)
        self.tick_size = max(0.1, tick_size)
        self.bias_threshold = max(1, bias_threshold)
        self._pressure_history: deque[int] = deque(maxlen=self.window_size)
        self._features = OrderbookFeatures()
        self._prev_bid = 0.0
        self._prev_ask = 0.0

    def update(self, tick: Tick) -> OrderbookFeatures:
        """輸入單筆 tick，更新目前 orderbook 特徵"""
        bid = float(getattr(tick, "bid_price", 0.0) or 0.0)
        ask = float(getattr(tick, "ask_price", 0.0) or 0.0)

        if bid <= 0 or ask <= 0 or bid > ask:
            return self._features

        spread = ask - bid
        mid_price = (bid + ask) / 2.0

        bid_change = bid - self._prev_bid if self._prev_bid > 0 else 0.0
        ask_change = ask - self._prev_ask if self._prev_ask > 0 else 0.0

        pressure_delta = 0
        if bid_change > 0:
            pressure_delta += 1
        elif bid_change < 0:
            pressure_delta -= 1

        if ask_change < 0:
            pressure_delta += 1
        elif ask_change > 0:
            pressure_delta -= 1

        self._pressure_history.append(pressure_delta)
        pressure_score = sum(self._pressure_history)

        if pressure_score >= self.bias_threshold:
            pressure_bias = "bullish"
        elif pressure_score <= -self.bias_threshold:
            pressure_bias = "bearish"
        else:
            pressure_bias = "neutral"

        max_abs_score = max(1, len(self._pressure_history) * 2)
        pressure_ratio = pressure_score / max_abs_score
        microprice_proxy = mid_price + pressure_ratio * max(spread / 2.0, self.tick_size * 0.5)

        self._features = OrderbookFeatures(
            spread=spread,
            mid_price=mid_price,
            bid_change=bid_change,
            ask_change=ask_change,
            bid_ask_pressure=pressure_ratio,
            pressure_score=pressure_score,
            pressure_bias=pressure_bias,
            microprice_proxy=microprice_proxy,
            orderbook_ready=len(self._pressure_history) >= 2,
            last_bid_price=bid,
            last_ask_price=ask,
            ticks_seen=self._features.ticks_seen + 1,
        )
        self._prev_bid = bid
        self._prev_ask = ask
        return self._features

    def get_snapshot(self) -> OrderbookFeatures:
        """取得目前特徵快照"""
        return self._features

    def reset(self):
        """清空內部狀態"""
        self._pressure_history.clear()
        self._features = OrderbookFeatures()
        self._prev_bid = 0.0
        self._prev_ask = 0.0
