from typing import Dict, Any, Optional
from loguru import logger
from core.engine.models import InstrumentPipeline
from core.position import PositionManager
from core.instrument_config import get_spec

class HealthMonitor:
    def __init__(self, engine: Any):
        self.engine = engine
        self._heartbeat_count = 0
        self._running = False

    def start(self) -> None:
        """
        向後相容：TradingEngine.start() 會呼叫 health_monitor.start()。
        本 HealthMonitor 以主迴圈 tick_heartbeat() 驅動，不需要額外執行緒；
        這裡僅維護狀態，避免 AttributeError 造成引擎啟動失敗。
        """
        self._running = True

    def stop(self) -> None:
        """向後相容：停止心跳監控（不終止主迴圈）。"""
        self._running = False

    @property
    def pipelines(self): return self.engine.pipelines

    @property
    def instruments(self): return self.engine.instruments

    @property
    def position_manager(self): return self.engine.position_manager

    @property
    def broker(self): return self.engine.broker

    @property
    def risk_manager(self): return self.engine.risk_manager

    @property
    def trading_mode(self): return self.engine.trading_mode
    def tick_heartbeat(self):
        """主迴圈呼叫的心跳計數與觸發"""
        if not self._running:
            return
        self._heartbeat_count += 1
        if self._heartbeat_count % 60 == 0:
            self._heartbeat()

    def _heartbeat(self):
        for inst in self.instruments:
            pos = self.position_manager.positions.get(inst)
            pipeline = self.pipelines.get(inst)
            price = pipeline.aggregator.current_price if pipeline else 0
            if pos and not pos.is_flat:
                config = get_spec(inst)
                pnl = pos.unrealized_pnl(price, config.point_value)
                logger.debug(f"[Heartbeat] {inst}: {price:.1f} | {pos.side.value} @ {pos.entry_price:.1f} | pnl: {pnl:+.0f}")
            else:
                logger.debug(f"[Heartbeat] {inst}: {price:.1f} | flat")

        # 每 1 分鐘做一次持倉核對（heartbeat 每 60 次空轉 = 60 秒）
        if self._heartbeat_count % 60 == 0 and self.trading_mode == "live":
            self._reconcile_positions()

        # 價格異常偵測
        self._check_price_anomaly()

    def _reconcile_positions(self):
        """定期比對引擎持倉和券商真實持倉"""
        if not hasattr(self.broker, 'get_real_positions'):
            return
        try:
            real_positions = self.broker.get_real_positions()
            for inst in self.instruments:
                engine_pos = self.position_manager.positions.get(inst)
                spec = get_spec(inst)
                contract_code = spec.code

                # 找到券商的真實持倉
                real_qty = 0
                real_side = None
                for rp in real_positions:
                    if rp['code'].startswith(contract_code) and rp['quantity'] > 0:
                        real_qty = rp['quantity']
                        real_side = "long" if "Buy" in rp['direction'] else "short"

                engine_qty = engine_pos.quantity if engine_pos and not engine_pos.is_flat else 0
                engine_side = engine_pos.side.value if engine_pos and not engine_pos.is_flat else "flat"

                if engine_qty != real_qty or (real_qty > 0 and engine_side != real_side):
                    logger.error(
                        f"[RECONCILE] {inst} 持倉不一致！"
                        f" 引擎={engine_side}×{engine_qty}"
                        f" 券商={real_side}×{real_qty}"
                        f" — 請手動檢查！"
                    )
        except Exception as e:
            logger.warning(f"[RECONCILE] 持倉核對失敗: {e}")

    def _check_price_anomaly(self):
        """價格異常偵測 — 超過 5x ATR 自動暫停交易"""
        for inst in self.instruments:
            pipeline = self.pipelines.get(inst)
            if not pipeline or not pipeline.snapshot or pipeline.snapshot.atr <= 0:
                continue
            price = pipeline.aggregator.current_price
            atr = pipeline.snapshot.atr
            if not hasattr(pipeline, '_last_heartbeat_price'):
                pipeline._last_heartbeat_price = price
                continue
            deviation = abs(price - pipeline._last_heartbeat_price)
            if deviation > atr * 5:
                # 嚴重異常：自動觸發熔斷保護帳戶
                logger.error(
                    f"[ANOMALY] {inst} 價格劇烈異常: {pipeline._last_heartbeat_price:.1f} → {price:.1f}"
                    f"（偏離 {deviation:.1f} > 5×ATR {atr * 5:.1f}）— 自動暫停交易！"
                )
                if self.risk_manager:
                    self.risk_manager.circuit_breaker.on_connection_lost()
                    self.risk_manager.circuit_breaker._halt_reason = f"價格異常: {inst} 偏離 {deviation:.0f} 點"
            elif deviation > atr * 3:
                logger.warning(
                    f"[ANOMALY] {inst} 價格異常波動: {pipeline._last_heartbeat_price:.1f} → {price:.1f}"
                    f"（偏離 {deviation:.1f} > 3×ATR {atr * 3:.1f}）"
                )
            pipeline._last_heartbeat_price = price
