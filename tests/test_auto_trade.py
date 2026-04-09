"""
自動交易（Auto-Trade）功能單元測試

TDD Phase: RED → 先寫測試，確認失敗後再實作

測試邊界：
- TradingEngine.auto_trade 屬性的預設值、切換邏輯
- _process_kbar 對 auto_trade 的門檻控制
- get_state() 回傳 auto_trade 狀態
"""

import os
import sys
from pathlib import Path
from unittest.mock import MagicMock, patch, PropertyMock
from datetime import datetime

# 確保 project root 在 sys.path
PROJECT_ROOT = Path(__file__).parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

# 設定必要環境變數（避免 .env 影響）
os.environ.setdefault("TRADING_MODE", "simulation")
os.environ.setdefault("RISK_PROFILE", "balanced")
os.environ.setdefault("INSTRUMENTS", "TMF")

from core.engine import TradingEngine, EngineState
from strategy.base import Signal, SignalDirection


# ============================================================
# 輔助函式
# ============================================================

def _make_engine_minimal() -> TradingEngine:
    """建立最小化引擎實例（不呼叫 initialize / start）"""
    engine = TradingEngine()
    return engine


def _make_initialized_engine() -> TradingEngine:
    """建立已初始化的引擎（simulation 模式，不 start）"""
    engine = TradingEngine()
    engine.initialize({})
    return engine


def _make_buy_signal() -> Signal:
    """建立一個買入信號"""
    return Signal(
        direction=SignalDirection.BUY,
        strength=0.85,
        stop_loss=21000.0,
        take_profit=22000.0,
        reason="test signal",
        source="test",
    )


# ============================================================
# 測試：預設值
# ============================================================

class TestAutoTradeDefault:
    """auto_trade 預設值測試"""

    def test_auto_trade_default_false(self):
        """引擎建立後 auto_trade 預設為 False"""
        engine = _make_engine_minimal()
        assert hasattr(engine, "auto_trade"), "TradingEngine 應有 auto_trade 屬性"
        assert engine.auto_trade is False, "auto_trade 預設應為 False"

    def test_auto_trade_after_initialize(self):
        """引擎初始化後 auto_trade 仍為 False"""
        engine = _make_initialized_engine()
        assert engine.auto_trade is False


# ============================================================
# 測試：toggle_auto_trade
# ============================================================

class TestToggleAutoTrade:
    """toggle_auto_trade 方法測試"""

    def test_toggle_on(self):
        """toggle_auto_trade(True) 應啟用自動交易"""
        engine = _make_initialized_engine()
        result = engine.toggle_auto_trade(True)
        assert result is True
        assert engine.auto_trade is True

    def test_toggle_off(self):
        """toggle_auto_trade(False) 應停用自動交易"""
        engine = _make_initialized_engine()
        engine.auto_trade = True
        result = engine.toggle_auto_trade(False)
        assert result is False
        assert engine.auto_trade is False

    def test_toggle_broadcasts(self):
        """toggle 應透過 WebSocket 廣播狀態"""
        engine = _make_initialized_engine()
        broadcast_mock = MagicMock()
        engine._ws_broadcast = broadcast_mock

        engine.toggle_auto_trade(True)

        broadcast_mock.assert_called()
        call_data = broadcast_mock.call_args[0][0]
        assert call_data["type"] == "settings"
        assert call_data["data"]["auto_trade"] is True


# ============================================================
# 測試：get_state 包含 auto_trade
# ============================================================

class TestGetStateAutoTrade:
    """get_state() 回傳 auto_trade 狀態"""

    def test_get_state_includes_auto_trade_false(self):
        """get_state 應包含 auto_trade = False"""
        engine = _make_initialized_engine()
        state = engine.get_state()
        assert "auto_trade" in state, "get_state() 應包含 auto_trade"
        assert state["auto_trade"] is False

    def test_get_state_includes_auto_trade_true(self):
        """toggle 後 get_state 應反映新狀態"""
        engine = _make_initialized_engine()
        engine.toggle_auto_trade(True)
        state = engine.get_state()
        assert state["auto_trade"] is True


# ============================================================
# 測試：_process_kbar 的 auto_trade 門檻
# ============================================================

class TestProcessKbarAutoTrade:
    """_process_kbar 中依 auto_trade 控制進場行為"""

    def test_auto_trade_off_no_entry(self):
        """auto_trade=False 時，策略有信號不應自動進場"""
        engine = _make_initialized_engine()
        engine.state = EngineState.RUNNING
        engine.auto_trade = False

        inst = engine.instruments[0]
        pipeline = engine.pipelines[inst]

        # Mock 策略返回買入信號
        buy_signal = _make_buy_signal()
        pipeline.strategy.on_kbar = MagicMock(return_value=buy_signal)
        pipeline.strategy.check_exit = MagicMock(return_value=None)

        # Mock 持倉為 flat
        pos_mock = MagicMock()
        pos_mock.is_flat = True
        pos_mock.side = MagicMock()
        pos_mock.side.value = "flat"
        engine.position_manager.positions[inst] = pos_mock

        # Mock snapshot
        pipeline.snapshot.price = 21500.0
        pipeline.snapshot.atr = 50.0

        # Mock _execute_entry 追蹤呼叫
        engine._execute_entry = MagicMock()

        # 模擬 K 棒處理
        from core.market_data import KBar
        kbar = KBar(
            datetime=datetime.now(),
            open=21500, high=21550, low=21450,
            close=21500, volume=100, interval=1,
        )

        # 確保有足夠 bars 讓指標更新
        import pandas as pd
        fake_df = pd.DataFrame({
            "open": [21500] * 10,
            "high": [21550] * 10,
            "low": [21450] * 10,
            "close": [21500] * 10,
            "volume": [100] * 10,
        })
        pipeline.aggregator.get_bars_dataframe = MagicMock(return_value=fake_df)
        pipeline.indicator_engine.update = MagicMock(return_value=pipeline.snapshot)

        engine._process_kbar(inst, kbar)

        # 關鍵斷言：auto_trade=False 時不應呼叫 _execute_entry
        engine._execute_entry.assert_not_called()

    def test_auto_trade_on_entry(self):
        """auto_trade=True 時，策略有信號應自動進場"""
        engine = _make_initialized_engine()
        engine.state = EngineState.RUNNING
        engine.auto_trade = True

        inst = engine.instruments[0]
        pipeline = engine.pipelines[inst]

        # Mock 策略返回買入信號
        buy_signal = _make_buy_signal()
        pipeline.strategy.on_kbar = MagicMock(return_value=buy_signal)
        pipeline.strategy.check_exit = MagicMock(return_value=None)

        # Mock 持倉為 flat
        pos_mock = MagicMock()
        pos_mock.is_flat = True
        pos_mock.side = MagicMock()
        pos_mock.side.value = "flat"
        engine.position_manager.positions[inst] = pos_mock

        # Mock snapshot
        pipeline.snapshot.price = 21500.0
        pipeline.snapshot.atr = 50.0

        # Mock _execute_entry
        engine._execute_entry = MagicMock()

        # 模擬
        from core.market_data import KBar
        kbar = KBar(
            datetime=datetime.now(),
            open=21500, high=21550, low=21450,
            close=21500, volume=100, interval=1,
        )

        import pandas as pd
        fake_df = pd.DataFrame({
            "open": [21500] * 10,
            "high": [21550] * 10,
            "low": [21450] * 10,
            "close": [21500] * 10,
            "volume": [100] * 10,
        })
        pipeline.aggregator.get_bars_dataframe = MagicMock(return_value=fake_df)
        pipeline.indicator_engine.update = MagicMock(return_value=pipeline.snapshot)

        engine._process_kbar(inst, kbar)

        # 關鍵斷言：auto_trade=True 時應呼叫 _execute_entry
        engine._execute_entry.assert_called_once()
