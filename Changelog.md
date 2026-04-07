# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Added

### Changed

### Fixed

## [0.2.0] - 2026-04-07

### Added
- 完成專案依賴安裝 (`pip install -r requirements.txt`) 於 `.\venv`。
- 新增「日內交易優化方案只交易一口」規劃文件，補上 `Implementation Plan`、`Module Architecture`、`Task List`、驗收標準與執行順序。
- 新增 orderbook 納入規劃與實作路線，先從 `L1 orderbook` 做進場過濾與觸發。
- 新增 1-6 章節進度總表與文件開頭快覽，方便快速辨識規劃與實作狀態。
- 新增 TMF 30 天真實歷史資料校準流程與操作版 checklist。

### Changed
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
