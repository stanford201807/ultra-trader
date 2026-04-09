# Engine Refactoring Task List

- [x] 1. **Setup & Models** (`core/engine/models.py`)
  - [x] 1.1 撰寫 `test_models.py` (針對 `InstrumentPipeline` 初始化邏輯的測試)
  - [x] 1.2 實作 `core/engine/models.py` (搬移 `EngineState`, `InstrumentPipeline` 等 dataclass)
  - [x] 1.3 運行測試確保綠燈
- [x] 2. **Health Monitor** (`core/engine/health.py`)
  - [x] 2.1 撰寫 `test_health.py` (防爆機制、斷路器、異常價差警報)
  - [x] 2.2 實作 `HealthMonitor` 類別 (搬移 `_heartbeat`, `_check_price_anomaly`, `_reconcile_positions`)
  - [x] 2.3 運行測試確保綠燈
- [x] 3. **Order Executor** (`core/engine/executor.py`)
  - [x] 3.1 撰寫 `test_executor.py` (測試 `execute_entry/exit`、冷卻機制、熔斷機制)
  - [x] 3.2 實作 `OrderExecutor` 類別 (搬移 `_execute_entry`, `_execute_exit`, 手動下單功能)
  - [x] 3.3 運行測試確保綠燈
- [x] 4. **Queries & State** (`core/engine/queries.py`)
  - [x] 4.1 撰寫 `test_queries.py` (測試 `get_state`, `get_kbars`, 相容第一種商品的邏輯)
  - [x] 4.2 實作 `EngineQueries` 類別
  - [x] 4.3 運行測試確保綠燈
- [x] 5. **Event Processor** (`core/engine/events.py`)
  - [x] 5.1 撰寫 `test_events.py` (測試 Tick/Kbar 路由、指標更新、調用 Executor)
  - [x] 5.2 實作 `EventProcessor` 類別 (包含 `_engine_loop`, `_process_tick`, `_on_kbar_complete`)
  - [x] 5.3 運行測試確保綠燈
- [x] 6. **Facade & Core Integration** (`core/engine/__init__.py`)
  - [x] 6.1 更新 `TradingEngine` façade，注入 models / health / executor / queries / events
  - [x] 6.2 補上 refactor 後的相容修復
    - [x] `toggle_auto_trade(enabled)` 顯式開關與廣播格式
    - [x] 補回 `_process_kbar` / `_process_tick` / `_execute_entry` / `_execute_exit` façade 委派
    - [x] 修正 `initialize()` 內舊介面殘留（logger / broker / risk / performance / instrument / aggregator callback）
    - [x] 補強 `EngineQueries.get_state()` 空狀態防呆與 `get_positions()`
  - [x] 6.3 執行 Engine 回歸測試
    - [x] `.\venv\Scripts\python -m pytest tests/test_auto_trade.py tests/engine -q`
    - [x] 結果：`34 passed`
  - [x] 6.4 舊單檔 `core/engine.py` 已由套件目錄 `core/engine/` 取代

## 後續待續

- [ ] 7. **Dashboard Backtest Flow**
  - [x] 7.1 驗證 `dashboard.schemas/services/app/static` 對應測試
    - [x] `.\venv\Scripts\python -m pytest tests/test_dashboard_backtest_api.py tests/test_dashboard_backtest_service.py tests/test_dashboard_backtest_schema.py tests/test_dashboard_backtest_ui.py -q`
    - [x] 結果：`11 passed`
  - [ ] 7.2 整理真正會阻塞 CI 的 pytest 收集問題
    - [x] 新增 `pytest.ini`，將 pytest 收集邊界限制在 `tests/`
    - [x] 排除 `everything-claude-code/` 內嵌測試
    - [x] 排除 `scripts/` 下會直接登入 Shioaji 的腳本
    - [x] 排除受權限影響的 `pytest-cache-files-*`
  - [x] 7.3 執行一次 `.\venv\Scripts\python -m pytest -q` 並確認專案測試收集正常
    - [x] 結果：`208 passed`
    - [x] 已知 warnings：
      - [x] `tests/test_backtest.py` 內 `TestOrderbookBacktestStrategy` 因自訂 `__init__` 被 pytest 跳過收集
      - [x] `.pytest_cache` 在目前 Windows 環境下仍有 cache 建立警告，但不影響測試結果
