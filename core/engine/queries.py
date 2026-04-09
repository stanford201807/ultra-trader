from typing import Dict, Any, List, Optional
from core.engine.models import EngineState, InstrumentPipeline
from core.position import PositionManager
from core.instrument_config import get_spec

def _safe_round(val, decimals=1, default=0):
    import math
    if val is None or (isinstance(val, float) and (math.isnan(val) or math.isinf(val))):
        return default
    return round(val, decimals)

class EngineQueries:
    def __init__(self, engine: Any):
        self.engine = engine

    @property
    def state(self): return self.engine.state
    @property
    def trading_mode(self): return self.engine.trading_mode
    @property
    def risk_profile(self): return self.engine.risk_profile
    @property
    def auto_trade(self): return self.engine.auto_trade
    @property
    def instruments(self): return self.engine.instruments
    @property
    def pipelines(self): return self.engine.pipelines
    @property
    def broker(self): return self.engine.broker
    @property
    def position_manager(self): return self.engine.position_manager
    @property
    def risk_manager(self): return self.engine.risk_manager
    @property
    def performance(self): return self.engine.performance
    @property
    def data_collector(self): return getattr(self.engine, 'data_collector', None)
    @property
    def left_side_engine(self): return getattr(self.engine, 'left_side_engine', None)

    def get_state(self) -> dict:
        prices = {}
        instruments_data = {}
        pm = self.position_manager

        for inst in self.instruments:
            pipeline = self.pipelines.get(inst)
            price = pipeline.aggregator.current_price if pipeline and hasattr(pipeline, "aggregator") and pipeline.aggregator else 0
            prices[inst] = price

            pos = pm.positions.get(inst) if pm else None
            config = get_spec(inst)
            unrealized = pos.unrealized_pnl(price, config.point_value) if pos and not pos.is_flat else 0

            instruments_data[inst] = {
                "name": config.name,
                "price": price,
                "point_value": config.point_value,
                "position": {
                    "side": pos.side.value if pos else "flat",
                    "entry_price": pos.entry_price if pos else 0,
                    "quantity": pos.quantity if pos else 0,
                    "entry_time": pos.entry_time.isoformat() if pos and pos.entry_time else None,
                    "stop_loss": pos.stop_loss if pos else 0,
                    "take_profit": pos.take_profit if pos else 0,
                    "trailing_stop": pos.trailing_stop if pos else 0,
                    "trailing_activated": pos.trailing_activated if pos else False,
                    "breakeven_activated": pos.breakeven_activated if pos else False,
                    "max_unrealized_profit": pos.max_unrealized_profit if pos else 0,
                    "bars_since_entry": pos.bars_since_entry if pos else 0,
                    "unrealized_pnl": round(unrealized, 0),
                },
                "snapshot": {
                    "adx": _safe_round(pipeline.snapshot.adx) if pipeline and hasattr(pipeline, "snapshot") else 0,
                    "rsi": _safe_round(pipeline.snapshot.rsi, default=50) if pipeline and hasattr(pipeline, "snapshot") else 50,
                    "atr": _safe_round(pipeline.snapshot.atr) if pipeline and hasattr(pipeline, "snapshot") else 0,
                    "ema20": _safe_round(pipeline.snapshot.ema20) if pipeline and hasattr(pipeline, "snapshot") else 0,
                    "ema60": _safe_round(pipeline.snapshot.ema60) if pipeline and hasattr(pipeline, "snapshot") else 0,
                    "ema200": _safe_round(pipeline.snapshot.ema200) if pipeline and hasattr(pipeline, "snapshot") and hasattr(pipeline.snapshot, 'ema200') and pipeline.snapshot.ema200 else 0,
                    "spread": _safe_round(pipeline.snapshot.spread) if pipeline and hasattr(pipeline, "snapshot") else 0,
                    "pressure_bias": pipeline.snapshot.pressure_bias if pipeline and hasattr(pipeline, "snapshot") else "neutral",
                    "orderbook_ready": pipeline.snapshot.orderbook_ready if pipeline and hasattr(pipeline, "snapshot") else False,
                },
                "strategy": pipeline.strategy.get_parameters() if pipeline and hasattr(pipeline, "strategy") and pipeline.strategy else {},
            }

        total_unrealized = pm.get_total_unrealized_pnl(prices) if pm else 0
        balance = pm.balance if pm else 0
        equity = balance + total_unrealized
        margin_used = pm.get_total_margin_used() if pm else 0

        account_info = {
            "balance": round(balance, 0),
            "equity": round(equity, 0),
            "margin_used": round(margin_used, 0),
            "margin_available": round(equity - margin_used, 0),
            "unrealized_pnl": round(total_unrealized, 0),
        }

        intel_data = {}
        if self.data_collector:
            try:
                intel_snapshot = self.data_collector.snapshot
                if self.left_side_engine:
                    self.left_side_engine.calculate(intel_snapshot)
                intel_data = intel_snapshot.to_dict()
            except Exception:
                pass

        activity = self.performance.get_activity_log(20) if self.performance else []
        paper_signals_count = len(self.performance.paper_signals) if self.performance else 0

        if self.instruments:
            first_inst = self.instruments[0]
            first_data = instruments_data[first_inst]
        else:
            first_data = {"price": 0, "position": {}, "strategy": {}, "snapshot": {}}

        return {
            "engine_state": self.state.value if isinstance(self.state, EngineState) else self.state,
            "trading_mode": self.trading_mode,
            "risk_profile": self.risk_profile,
            "contract": self.broker.get_contract_name() if self.broker and hasattr(self.broker, "get_contract_name") else "",
            "instruments": self.instruments,
            "instruments_data": instruments_data,
            "price": first_data["price"],
            "account": account_info,
            "position": first_data["position"],
            "daily_pnl": pm.get_daily_pnl() if pm else 0,
            "daily_trades": pm.get_daily_trade_count() if pm else 0,
            "paper_signals": paper_signals_count,
            "strategy": first_data["strategy"],
            "risk": self.risk_manager.to_dict() if self.risk_manager and hasattr(self.risk_manager, "to_dict") else {},
            "snapshot": first_data["snapshot"],
            "intelligence": intel_data,
            "activity": activity,
            "auto_trade": self.auto_trade,
        }

    def get_positions(self) -> dict:
        if not self.position_manager:
            return {}

        prices = {}
        for inst in self.instruments:
            pipeline = self.pipelines.get(inst)
            if pipeline and hasattr(pipeline, "aggregator") and pipeline.aggregator:
                prices[inst] = pipeline.aggregator.current_price
        return self.position_manager.to_dict(prices)

    def get_trade_history(self) -> list[dict]:
        if not self.position_manager:
            return []
        return [
            {
                "id": getattr(t, "id", ""),
                "instrument": t.instrument,
                "entry_time": t.entry_time.isoformat() if t.entry_time else None,
                "exit_time": t.exit_time.isoformat() if t.exit_time else None,
                "side": t.side,
                "entry_price": t.entry_price,
                "exit_price": t.exit_price,
                "quantity": t.quantity,
                "pnl": round(t.net_pnl, 0),
                "pnl_points": round(t.pnl_points, 1),
                "reason": t.reason,
                "bars_held": t.bars_held,
            }
            for t in self.position_manager.trades
        ]

    def delete_trade(self, trade_id: str) -> bool:
        if self.position_manager:
            return self.position_manager.delete_trade(trade_id)
        return False

    def update_trade(self, trade_id: str, updates: dict) -> bool:
        if self.position_manager:
            return self.position_manager.update_trade(trade_id, updates)
        return False

    def get_kbars(self, timeframe: int = 1, count: int = 200, instrument: str = "") -> list[dict]:
        inst = instrument or self.instruments[0]
        pipeline = self.pipelines.get(inst)
        if not pipeline or not hasattr(pipeline, "aggregator") or not pipeline.aggregator:
            return []

        bars = list(pipeline.aggregator.get_bars(timeframe, count))
        current = pipeline.aggregator.get_current_bar(timeframe)
        if current and current.close > 0:
            bars.append(current)
        if not bars:
            return []

        def _to_iso(dt):
            if hasattr(dt, 'isoformat'):
                return dt.isoformat()
            if isinstance(dt, (int, float)):
                from datetime import datetime as _dt
                if dt > 1e18:       return _dt.fromtimestamp(dt / 1e9).isoformat()
                elif dt > 1e15:     return _dt.fromtimestamp(dt / 1e6).isoformat()
                elif dt > 1e12:     return _dt.fromtimestamp(dt / 1e3).isoformat()
                else:               return _dt.fromtimestamp(dt).isoformat()
            return str(dt)

        seen = {}
        for i, b in enumerate(bars):
            t = _to_iso(b.datetime)
            seen[t] = i
        sorted_times = sorted(seen.keys())
        bars = [bars[seen[t]] for t in sorted_times]
        
        if len(bars) > 1:
            gap_threshold = max(timeframe * 60 * 10, 3600)
            cut = 0
            for i in range(len(bars) - 1, 0, -1):
                dt_curr = bars[i].datetime
                dt_prev = bars[i-1].datetime
                if hasattr(dt_curr, 'to_pydatetime'): dt_curr = dt_curr.to_pydatetime()
                if hasattr(dt_prev, 'to_pydatetime'): dt_prev = dt_prev.to_pydatetime()
                try:
                    gap = (dt_curr - dt_prev).total_seconds()
                except:
                    continue
                if gap > gap_threshold:
                    cut = i
                    break
            if cut > 0:
                bars = bars[cut:]
                
        closes = [b.close for b in bars]
        ema20_vals = self._calc_ema(closes, 20)
        ema60_vals = self._calc_ema(closes, 60)
        ema200_vals = self._calc_ema(closes, 200)

        return [
            {
                "time": _to_iso(b.datetime),
                "open": b.open,
                "high": b.high,
                "low": b.low,
                "close": b.close,
                "volume": b.volume,
                "ema20": round(ema20_vals[i], 1) if i < len(ema20_vals) and ema20_vals[i] is not None else None,
                "ema60": round(ema60_vals[i], 1) if i < len(ema60_vals) and ema60_vals[i] is not None else None,
                "ema200": round(ema200_vals[i], 1) if i < len(ema200_vals) and ema200_vals[i] is not None else None,
            }
            for i, b in enumerate(bars)
        ]

    @staticmethod
    def _calc_ema(data: list[float], period: int) -> list[float]:
        if len(data) < period:
            return [None] * len(data)
        result = [None] * (period - 1)
        sma = sum(data[:period]) / period
        result.append(sma)
        multiplier = 2.0 / (period + 1)
        for i in range(period, len(data)):
            sma = (data[i] - result[-1]) * multiplier + result[-1]
            result.append(sma)
        return result
