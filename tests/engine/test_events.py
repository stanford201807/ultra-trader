"""EventProcessor 單元測試

測試範圍：
- Tick 路由（分派到正確 pipeline）
- Tick 處理（聚合器 / orderbook / 持倉更新）
- 硬停損觸發
- 策略出場信號觸發
- KBar 處理（指標更新、策略決策、收盤平倉）
- MTF KBar 更新（5m / 15m）
- Tick 回調入隊（緊急 / 一般）
- 主迴圈空轉時觸發心跳
"""
import queue
import pytest
from unittest.mock import MagicMock, patch, PropertyMock
from datetime import datetime
from core.engine.events import EventProcessor
from core.engine.models import EngineState, InstrumentPipeline
from core.position import Side


# ─── helpers ───────────────────────────────────────────────

def _make_engine(
    state=EngineState.RUNNING,
    trading_mode="paper",
    auto_trade=True,
    instruments=None,
):
    """建立共用的 mock engine"""
    engine = MagicMock()
    engine.state = state
    engine.trading_mode = trading_mode
    engine.auto_trade = auto_trade
    engine.instruments = instruments or ["TMF"]
    engine.timeframe = 1

    pipeline = MagicMock(spec=InstrumentPipeline)
    pipeline.aggregator = MagicMock()
    pipeline.aggregator.current_price = 20000
    pipeline.indicator_engine = MagicMock()
    pipeline.orderbook_engine = MagicMock()
    pipeline.orderbook_features = MagicMock()
    pipeline.snapshot = MagicMock()
    pipeline.snapshot.price = 20000
    pipeline.snapshot.adx = 25.0
    pipeline.snapshot.rsi = 50.0
    pipeline.snapshot.atr = 100.0
    pipeline.snapshot.ema20 = 19980.0
    pipeline.snapshot.ema60 = 19950.0
    pipeline.snapshot.ema200 = 19900.0
    pipeline.strategy = MagicMock()
    pipeline.strategy.on_tick = MagicMock(return_value=None)
    pipeline.strategy.check_exit = MagicMock(return_value=None)
    pipeline.strategy._last_signal_strength = 0.0
    pipeline.snapshot_5m = MagicMock()
    pipeline.snapshot_15m = MagicMock()

    engine.pipelines = {"TMF": pipeline}
    engine.position_manager = MagicMock()
    engine.position_manager.positions = {"TMF": MagicMock()}
    engine.executor = MagicMock()
    engine.performance = MagicMock()
    engine.risk_manager = MagicMock()
    engine.broker = MagicMock()

    return engine, pipeline


# ─── 5.1.1 Tick 路由 ──────────────────────────────────

class TestTickProcessing:
    def test_tick_routes_to_correct_pipeline(self):
        """Tick 正確路由到對應商品的 pipeline"""
        engine, pipeline = _make_engine()
        processor = EventProcessor(engine=engine)

        tick = MagicMock()
        tick.instrument = "TMF"
        tick.price = 20050
        tick.volume = 1
        tick.datetime = datetime.now()
        tick.bid_price = 20049
        tick.ask_price = 20051

        processor._process_tick(tick)
        pipeline.aggregator.on_tick.assert_called_once_with(tick)

    def test_tick_unknown_instrument_ignored(self):
        """未知商品的 Tick 被忽略"""
        engine, pipeline = _make_engine()
        processor = EventProcessor(engine=engine)

        tick = MagicMock()
        tick.instrument = "UNKNOWN"
        tick.price = 100

        # 不應該觸發任何 pipeline 處理
        processor._process_tick(tick)
        pipeline.aggregator.on_tick.assert_not_called()

    def test_tick_updates_position_price(self):
        """Tick 更新持倉的即時價格"""
        engine, pipeline = _make_engine()
        processor = EventProcessor(engine=engine)

        tick = MagicMock()
        tick.instrument = "TMF"
        tick.price = 20100
        tick.volume = 5
        tick.datetime = datetime.now()
        tick.bid_price = 20099
        tick.ask_price = 20101

        processor._process_tick(tick)
        engine.position_manager.update_price.assert_called_once_with("TMF", 20100)


class TestHardStopLoss:
    def test_hard_stop_triggers_for_long_position(self):
        """多頭硬停損觸發"""
        engine, pipeline = _make_engine()
        processor = EventProcessor(engine=engine)

        pos = MagicMock()
        pos.is_flat = False
        pos.stop_loss = 19800
        pos.side = Side.LONG
        engine.position_manager.positions = {"TMF": pos}

        tick = MagicMock()
        tick.instrument = "TMF"
        tick.price = 19750  # 低於停損價
        tick.volume = 1
        tick.datetime = datetime.now()
        tick.bid_price = 19749
        tick.ask_price = 19751

        processor._process_tick(tick)
        engine.executor.execute_exit.assert_called_once()
        call_args = engine.executor.execute_exit.call_args
        assert call_args[0][0] == "TMF"
        assert call_args[0][2] == 19750  # price

    def test_hard_stop_triggers_for_short_position(self):
        """空頭硬停損觸發"""
        engine, pipeline = _make_engine()
        processor = EventProcessor(engine=engine)

        pos = MagicMock()
        pos.is_flat = False
        pos.stop_loss = 20200
        pos.side = Side.SHORT
        engine.position_manager.positions = {"TMF": pos}

        tick = MagicMock()
        tick.instrument = "TMF"
        tick.price = 20250  # 高於停損價
        tick.volume = 1
        tick.datetime = datetime.now()
        tick.bid_price = 20249
        tick.ask_price = 20251

        processor._process_tick(tick)
        engine.executor.execute_exit.assert_called_once()

    def test_no_hard_stop_when_no_position(self):
        """無持倉時不觸發硬停損"""
        engine, pipeline = _make_engine()
        processor = EventProcessor(engine=engine)

        pos = MagicMock()
        pos.is_flat = True
        engine.position_manager.positions = {"TMF": pos}

        tick = MagicMock()
        tick.instrument = "TMF"
        tick.price = 19750
        tick.volume = 1
        tick.datetime = datetime.now()
        tick.bid_price = 19749
        tick.ask_price = 19751

        processor._process_tick(tick)
        engine.executor.execute_exit.assert_not_called()

    def test_strategy_exit_when_no_hard_stop(self):
        """沒有硬停損但策略觸發出場"""
        engine, pipeline = _make_engine()
        processor = EventProcessor(engine=engine)

        pos = MagicMock()
        pos.is_flat = False
        pos.stop_loss = 19500  # 還沒到停損
        pos.side = Side.LONG
        engine.position_manager.positions = {"TMF": pos}

        exit_signal = MagicMock()
        pipeline.strategy.check_exit.return_value = exit_signal

        tick = MagicMock()
        tick.instrument = "TMF"
        tick.price = 19600  # 高於停損，不觸發硬停損
        tick.volume = 1
        tick.datetime = datetime.now()
        tick.bid_price = 19599
        tick.ask_price = 19601

        processor._process_tick(tick)
        engine.executor.execute_exit.assert_called_once()


# ─── 5.1.2 KBar 處理 ──────────────────────────────────

class TestKBarProcessing:
    def test_kbar_updates_indicators(self):
        """K 棒完成後更新指標"""
        engine, pipeline = _make_engine()
        processor = EventProcessor(engine=engine)

        df_mock = MagicMock()
        df_mock.__len__ = MagicMock(return_value=50)
        pipeline.aggregator.get_bars_dataframe.return_value = df_mock
        pipeline.indicator_engine.update.return_value = pipeline.snapshot

        kbar = MagicMock()
        kbar.datetime = datetime.now()
        kbar.close = 20100
        kbar.volume = 10
        kbar.open = 20000
        kbar.high = 20150
        kbar.low = 19950
        kbar.interval = 1

        processor._process_kbar("TMF", kbar)
        pipeline.indicator_engine.update.assert_called_once_with(df_mock)

    def test_kbar_skipped_if_insufficient_data(self):
        """資料不足 5 根時跳過"""
        engine, pipeline = _make_engine()
        processor = EventProcessor(engine=engine)

        df_mock = MagicMock()
        df_mock.__len__ = MagicMock(return_value=3)
        pipeline.aggregator.get_bars_dataframe.return_value = df_mock

        kbar = MagicMock()
        kbar.datetime = datetime.now()
        kbar.close = 20100

        processor._process_kbar("TMF", kbar)
        pipeline.indicator_engine.update.assert_not_called()

    def test_kbar_triggers_entry_when_auto_trade(self):
        """自動交易開啟時 K 棒觸發進場"""
        engine, pipeline = _make_engine(auto_trade=True)
        processor = EventProcessor(engine=engine)
        # 模擬收盤檢查 — 不在收盤時段
        processor._sessions = {"TMF": MagicMock()}
        processor._sessions["TMF"].get_phase.return_value = MagicMock()
        processor._sessions["TMF"].minutes_to_close.return_value = 120

        # 用 patch 避免 SessionPhase 導入問題
        with patch.object(processor, '_check_session_close', return_value=False):
            df_mock = MagicMock()
            df_mock.__len__ = MagicMock(return_value=50)
            pipeline.aggregator.get_bars_dataframe.return_value = df_mock
            pipeline.indicator_engine.update.return_value = pipeline.snapshot

            pos = MagicMock()
            pos.is_flat = True
            engine.position_manager.positions = {"TMF": pos}

            entry_signal = MagicMock()
            entry_signal.is_buy = True
            entry_signal.strength = 0.8
            entry_signal.reason = "test signal"
            entry_signal.stop_loss = 19800
            entry_signal.take_profit = 20400
            pipeline.strategy.on_kbar.return_value = entry_signal

            kbar = MagicMock()
            kbar.datetime = datetime.now()
            kbar.close = 20100
            kbar.volume = 10
            kbar.open = 20000
            kbar.high = 20150
            kbar.low = 19950
            kbar.interval = 1

            processor._process_kbar("TMF", kbar)
            engine.executor.execute_entry.assert_called_once()

    def test_kbar_broadcasts_signal_when_auto_trade_off(self):
        """自動交易關閉時廣播信號但不進場"""
        engine, pipeline = _make_engine(auto_trade=False)
        processor = EventProcessor(engine=engine)

        with patch.object(processor, '_check_session_close', return_value=False):
            df_mock = MagicMock()
            df_mock.__len__ = MagicMock(return_value=50)
            pipeline.aggregator.get_bars_dataframe.return_value = df_mock
            pipeline.indicator_engine.update.return_value = pipeline.snapshot

            pos = MagicMock()
            pos.is_flat = True
            engine.position_manager.positions = {"TMF": pos}

            entry_signal = MagicMock()
            entry_signal.is_buy = True
            entry_signal.strength = 0.8
            entry_signal.reason = "test signal"
            entry_signal.stop_loss = 19800
            entry_signal.take_profit = 20400
            pipeline.strategy.on_kbar.return_value = entry_signal

            kbar = MagicMock()
            kbar.datetime = datetime.now()
            kbar.close = 20100
            kbar.volume = 10
            kbar.open = 20000
            kbar.high = 20150
            kbar.low = 19950
            kbar.interval = 1

            processor._process_kbar("TMF", kbar)
            engine.executor.execute_entry.assert_not_called()

    def test_kbar_exit_check_when_holding(self):
        """持倉中 K 棒觸發出場檢查"""
        engine, pipeline = _make_engine()
        processor = EventProcessor(engine=engine)

        with patch.object(processor, '_check_session_close', return_value=False):
            df_mock = MagicMock()
            df_mock.__len__ = MagicMock(return_value=50)
            pipeline.aggregator.get_bars_dataframe.return_value = df_mock
            pipeline.indicator_engine.update.return_value = pipeline.snapshot

            pos = MagicMock()
            pos.is_flat = False
            pos.side = MagicMock()
            pos.side.value = "long"
            pos.entry_price = 19900
            pos.bars_since_entry = 5
            engine.position_manager.positions = {"TMF": pos}

            exit_signal = MagicMock()
            pipeline.strategy.check_exit.return_value = exit_signal

            kbar = MagicMock()
            kbar.datetime = datetime.now()
            kbar.close = 20100
            kbar.volume = 10
            kbar.open = 20000
            kbar.high = 20150
            kbar.low = 19950
            kbar.interval = 1

            processor._process_kbar("TMF", kbar)
            engine.executor.execute_exit.assert_called_once()


# ─── 5.1.3 MTF KBar 更新 ──────────────────────────────

class TestMTFKBarProcessing:
    def test_5m_kbar_updates_indicator(self):
        """5 分 K 完成後更新 5m 指標引擎"""
        engine, pipeline = _make_engine()
        processor = EventProcessor(engine=engine)

        df_mock = MagicMock()
        df_mock.__len__ = MagicMock(return_value=50)
        pipeline.aggregator.get_bars_dataframe.return_value = df_mock

        kbar = MagicMock()
        processor._on_kbar_5m_complete("TMF", kbar)
        pipeline.indicator_engine_5m.update.assert_called_once()

    def test_15m_kbar_updates_indicator(self):
        """15 分 K 完成後更新 15m 指標引擎"""
        engine, pipeline = _make_engine()
        processor = EventProcessor(engine=engine)

        df_mock = MagicMock()
        df_mock.__len__ = MagicMock(return_value=50)
        pipeline.aggregator.get_bars_dataframe.return_value = df_mock

        kbar = MagicMock()
        processor._on_kbar_15m_complete("TMF", kbar)
        pipeline.indicator_engine_15m.update.assert_called_once()


# ─── 5.1.4 Tick 回調入隊 ──────────────────────────────

class TestTickCallback:
    def test_tick_enqueued_normally(self):
        """正常 tick 入隊"""
        engine, pipeline = _make_engine()
        processor = EventProcessor(engine=engine)

        pos = MagicMock()
        pos.is_flat = True
        engine.position_manager.positions = {"TMF": pos}

        tick = MagicMock()
        tick.instrument = "TMF"
        tick.price = 20000

        processor.on_tick(tick)
        assert not processor._event_queue.empty()
        event_type, data = processor._event_queue.get_nowait()
        assert event_type == "tick"
        assert data == tick

    def test_urgent_tick_still_enqueued_when_queue_full(self):
        """緊急 tick（觸及硬停損）在佇列滿時仍會被塞入"""
        engine, pipeline = _make_engine()
        processor = EventProcessor(engine=engine)
        processor._event_queue = queue.Queue(maxsize=1)

        # 先塞滿佇列
        processor._event_queue.put(("tick", MagicMock()))

        pos = MagicMock()
        pos.is_flat = False
        pos.stop_loss = 19800
        pos.side = Side.LONG
        engine.position_manager.positions = {"TMF": pos}

        tick = MagicMock()
        tick.instrument = "TMF"
        tick.price = 19750  # 低於停損 → 優先

        processor.on_tick(tick)
        # 應該成功塞入（犧牲舊的）
        event_type, data = processor._event_queue.get_nowait()
        assert data == tick


# ─── 5.1.5 廣播 ──────────────────────────────────────

class TestBroadcast:
    def test_tick_broadcasts_to_ws(self):
        """Tick 處理後廣播到 WebSocket"""
        engine, pipeline = _make_engine()
        processor = EventProcessor(engine=engine)

        pos = MagicMock()
        pos.is_flat = True
        engine.position_manager.positions = {"TMF": pos}

        tick = MagicMock()
        tick.instrument = "TMF"
        tick.price = 20000
        tick.volume = 1
        tick.datetime = datetime.now()
        tick.bid_price = 19999
        tick.ask_price = 20001

        processor._process_tick(tick)
        # _broadcast 應該被呼叫至少一次（tick 廣播）
        engine._broadcast.assert_called()

    def test_kbar_broadcasts_indicators(self):
        """K 棒處理後廣播指標"""
        engine, pipeline = _make_engine()
        processor = EventProcessor(engine=engine)

        with patch.object(processor, '_check_session_close', return_value=False):
            df_mock = MagicMock()
            df_mock.__len__ = MagicMock(return_value=50)
            pipeline.aggregator.get_bars_dataframe.return_value = df_mock
            pipeline.indicator_engine.update.return_value = pipeline.snapshot

            pos = MagicMock()
            pos.is_flat = True
            engine.position_manager.positions = {"TMF": pos}
            pipeline.strategy.on_kbar.return_value = None

            kbar = MagicMock()
            kbar.datetime = datetime.now()
            kbar.close = 20100
            kbar.volume = 10
            kbar.open = 20000
            kbar.high = 20150
            kbar.low = 19950
            kbar.interval = 1

            processor._process_kbar("TMF", kbar)
            # 至少有 kbar 和 signal 兩次廣播
            assert engine._broadcast.call_count >= 2
