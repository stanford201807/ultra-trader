# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Added
- 新增 `pytest.ini`，將 pytest 收集範圍限制在 `tests/`，避免誤收 `scripts/`（可能觸發 Shioaji 登入）與 `everything-claude-code/` 的內嵌測試。

### Changed
- 回測測試中的 helper 策略類別改名，避免 pytest 收集警告（該類別非測試案例）。

### Fixed
- 修復 `TradingEngine.set_risk_profile()` 僅同步風控、但未同步策略層 risk profile 與 orderbook profile 的問題（`dangerous -> crisis` 後，策略仍停留在 `balanced`）。

## [0.2.2] - 2026-04-08

### Added
- 新增「🤖 自動交易」切換按鈕，位於 Dashboard Header 暫停/停止按鈕旁。
  - `auto_trade` 預設為 `False`（僅觀察+手動模式）。
  - 啟用後引擎依策略信號自動進場下單；關閉時信號僅廣播不執行。
  - `live` 模式啟用前需二次確認（`confirm` 彈窗）。
  - 啟用狀態按鈕顯示藍色發光 + pulse 動畫。
- 新增 `TradingEngine.toggle_auto_trade()` 方法與 `/api/auto-trade` GET/POST 端點。
- 新增 WebSocket `auto_trade_signal` 事件，auto_trade 關閉時廣播偵測到的進場信號供手動參考。
- 新增 `tests/test_auto_trade.py`（9 個測試案例），覆蓋預設值、toggle、broadcast、get_state、進場門檻。
- 交易紀錄持久化：引擎重啟不遺失當日交易紀錄，新增刪除/修改單筆交易 API。
- 新增交易績效追蹤系統 (`core/performance.py`)，自動結算每日統計。

### Changed
- `_process_kbar()` 進場邏輯改為受 `auto_trade` 門檻控制：
  - `auto_trade = True`：維持原行為，有信號即自動進場。
  - `auto_trade = False`：僅廣播信號，不執行 `_execute_entry()`。
- `get_state()` 新增回傳 `auto_trade` 欄位，WebSocket 即時同步。
- Dashboard 帳戶快覽列改用 CSS Grid 排版，提升對齊穩定性。
- 次要文字色 (`--text-secondary`, `--text-muted`) 大幅提亮，改善深色主題可讀性。

## [0.2.1] - 2026-04-08

### Added
- 實作交易績效記錄系統 (`core/performance.py`)，自動結算每日勝負筆數、勝率與損益。
- 擴充 `Trade` 與 `Position` 模型結構，新增 `strategy`、`market_regime` 與 `signal_strength`，並將資訊連動至引擎 `_execute_entry` 與部位管理器中。
- 新增 `risk/profile_config.py`，集中管理風險等級 canonical、`dangerous -> crisis` alias 與固定映射表。
- 新增 `strategy/orderbook_profiles.py`，集中管理 `A1 ~ A5` 參數組合。
- 新增 `tests/test_risk_profile_config.py`，驗證風險等級正規化、非法值拒絕與固定映射。

### Changed
- Dashboard 字體縮放上限由 `130%` 提升至 `200%`，保留下限 `85%` 與 `100%` 一鍵重置。
- `core/engine.py`、`risk/manager.py`、`risk/position_sizing.py` 改為強制使用正規化後的風險等級，統一處理 `dangerous` 別名。
- `core/engine.py` 在風險切換時，會同步套用「四級風險對應 orderbook A1~A5 固定映射」到策略的 `OrderbookFilter`。
- `scripts/backtest_runner.py` 的 `--risk` 新增 `crisis` / `dangerous`，且未指定 `--orderbook-profile` 時改為自動套用固定映射（可用顯式 `--orderbook-profile` 覆蓋）。
- Dashboard 新增「Orderbook 監控卡」，顯示 `ready`、`spread`、`pressure_bias` 與方向色彩提示。
- `.env.example`、`README.md` 同步補上 `crisis` 與 `dangerous` alias 說明。

### Fixed
- 修復 Dashboard `A- / A+` 僅更新百分比文字、但實際字體未改變的問題。
  - 將 `--uifs` 實際套用到 `.app` 節點的 inline CSS variable。
  - 移除根節點無效的 Vue `:style` 綁定，避免縮放值卡在預設 `1`。
- 修復 Dashboard 風險切換可能出現「前端顯示已切換，但後端未套用」的不一致問題：`/api/settings` 現在會驗證與回傳 canonical 值，前端依回傳值更新。

## [0.2.0] - 2026-04-07

### Added
- 完成專案依賴安裝 (`pip install -r requirements.txt`) 於 `.\venv`。
- 新增「日內交易優化方案只交易一口」規劃文件，補上 `Implementation Plan`、`Module Architecture`、`Task List`、驗收標準與執行順序。
- 新增 orderbook 納入規劃與實作路線，先從 `L1 orderbook` 做進場過濾與觸發。
- 新增 1-6 章節進度總表與文件開頭快覽，方便快速辨識規劃與實作狀態。
- 新增 TMF 30 天真實歷史資料校準流程與操作版 checklist。

### Changed
- `strategy/orderbook_filter.py` 將 `spread_threshold_strong_night` 由 `4.0` 收斂至 `3.5`，並同步回寫 TMF 校準 / 驗證 / 保留集結果到 `日內交易優化方案只交易一口.md`。
- 回測腳本 `scripts/backtest_runner.py` 新增 `--compare-orderbook`、`--profile-grid`、`--start-date`、`--end-date` 與 `--summary-only`，可直接跑校準集 / 驗證集 / 保留集比較。
- `strategy/momentum.py` 現在可注入自訂 `OrderbookFilter`，並把 `kbar.datetime`、`ATR ratio` 傳入 orderbook 門檻判斷。
- `strategy/orderbook_filter.py` 改為受限的動態 `spread` 調整器，依 `regime + session + volatility` 決定門檻。
- `scripts/fetch_historical.py` 修正 `TMF` 商品映射與 K 棒時間戳轉換，確保抓取資料和 `SessionManager` 時段定義一致。
- `日內交易優化方案只交易一口.md` 已更新校準集、驗證集、保留集與 A1 ~ A5 的完整進度與結果。

### Fixed
- 修復 `scripts/start.py` 啟動時發生的 `[Broker] connection failed` 錯誤。
  - 在 `core/engine.py` 中將 `load_dotenv` 的 `override` 設為 `True`。
  - 對讀取到的環境變數加上 `.strip().lower()` 進行淨化，解決因隱藏空白或換行導致字串比對失敗的問題。
  - 確保引擎能穩定識別 `simulation` 模式，並正確套用 `MockBroker`。
- 修復 `intelligence/data_collector.py` 發生 `[TWSE] spot request failed` 且伴隨 `[SSL: CERTIFICATE_VERIFY_FAILED]` 的錯誤。
  - 對向 TWSE 和 TAIFEX 呼叫的 requests 請求加入 `verify=False` 參數，略過預設的伺服器憑證驗證。
  - 引用 `urllib3` 並設定取消 `InsecureRequestWarning` 的警告顯示。
- 修復 `scripts/fetch_historical.py` 讀取歷史 K 棒時 `TMF` 會誤抓到 `MXF` 合約的問題。
- 修復 `scripts/fetch_historical.py` 對 `kbars.ts` 的時間轉換，避免本地時區偏移造成盤別對不齊。
- 修復回測與策略在 Windows 終端機下可能因 `cp950` 與 emoji 輸出而中斷的問題。
- 修復 `strategy/momentum.py` 與 `strategy/orderbook_filter.py` 的接線問題，讓強趨勢 / 日夜盤 / 波動率的動態 spread 調整能正常運作。
