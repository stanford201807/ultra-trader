"""
UltraTrader orderbook 進場過濾器
"""

from dataclasses import dataclass
from datetime import time as dtime

from strategy.base import SignalDirection
from strategy.orderbook_features import OrderbookFeatures


@dataclass
class OrderbookDecision:
    """進場過濾結果"""
    allowed: bool
    reason: str


class OrderbookFilter:
    """以 L1 orderbook 特徵判斷是否允許進場"""

    def __init__(
        self,
        spread_threshold_normal: float = 2.0,
        spread_threshold_open: float = 4.0,
        spread_threshold_crisis: float = 6.0,
        spread_threshold_strong_day: float = 5.0,
        spread_threshold_strong_night: float = 4.0,
        pressure_min_score: int = 2,
    ):
        self.spread_threshold_normal = spread_threshold_normal
        self.spread_threshold_open = spread_threshold_open
        self.spread_threshold_crisis = spread_threshold_crisis
        self.spread_threshold_strong_day = spread_threshold_strong_day
        self.spread_threshold_strong_night = spread_threshold_strong_night
        self.pressure_min_score = max(1, pressure_min_score)

    def allow_entry(
        self,
        direction,
        features: OrderbookFeatures,
        phase=None,
        regime=None,
        now=None,
        volatility_ratio: float = 1.0,
    ) -> OrderbookDecision:
        """檢查目前 orderbook 狀態是否允許進場"""
        if direction == SignalDirection.CLOSE:
            return OrderbookDecision(True, "close signal bypass")

        if not features or not features.orderbook_ready:
            return OrderbookDecision(True, "orderbook fallback: not ready")

        spread_limit = self._resolve_spread_threshold(phase, regime, now, volatility_ratio)
        if features.spread > spread_limit:
            return OrderbookDecision(False, f"spread too wide: {features.spread:.1f} > {spread_limit:.1f}")

        normalized_direction = self._normalize_direction(direction)
        if normalized_direction == "buy":
            if features.pressure_score <= -self.pressure_min_score or features.pressure_bias == "bearish":
                return OrderbookDecision(False, "orderbook bearish pressure")
        elif normalized_direction == "sell":
            if features.pressure_score >= self.pressure_min_score or features.pressure_bias == "bullish":
                return OrderbookDecision(False, "orderbook bullish pressure")

        return OrderbookDecision(True, "orderbook aligned")

    def _resolve_spread_threshold(self, phase=None, regime=None, now=None, volatility_ratio: float = 1.0) -> float:
        phase_name = getattr(phase, "name", str(phase or "")).upper()
        regime_name = getattr(regime, "name", str(regime or "")).upper()
        session_bucket = self._resolve_session_bucket(now)
        volatility_multiplier = self._resolve_volatility_multiplier(volatility_ratio)

        if "CRISIS" in regime_name:
            return self.spread_threshold_crisis * volatility_multiplier
        if "OPEN" in phase_name:
            return self.spread_threshold_open * volatility_multiplier
        if "STRONG_TREND" in regime_name:
            if session_bucket == "day":
                return self.spread_threshold_strong_day * volatility_multiplier
            if session_bucket == "night":
                return self.spread_threshold_strong_night * volatility_multiplier
            return self.spread_threshold_open * volatility_multiplier
        return self.spread_threshold_normal * volatility_multiplier

    @staticmethod
    def _resolve_volatility_multiplier(volatility_ratio: float) -> float:
        """用 ATR ratio 估算波動率修正，範圍保持在 0.85 ~ 1.25。"""
        if volatility_ratio <= 0:
            return 1.0
        multiplier = 1.0 + (volatility_ratio - 1.0) * 0.35
        return max(0.85, min(1.25, multiplier))

    @staticmethod
    def _resolve_session_bucket(now) -> str:
        """依時間粗分日盤 / 夜盤；未提供時間時回傳 unknown。"""
        if now is None:
            return "unknown"

        t = now.time()
        if dtime(8, 45) <= t <= dtime(13, 45):
            return "day"
        if t >= dtime(15, 0) or t <= dtime(5, 0):
            return "night"
        return "unknown"

    @staticmethod
    def _normalize_direction(direction) -> str:
        if direction == SignalDirection.BUY:
            return "buy"
        if direction == SignalDirection.SELL:
            return "sell"
        return str(direction).lower()
