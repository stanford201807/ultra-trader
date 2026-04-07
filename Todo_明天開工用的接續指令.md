# Todo_明天開工用的接續指令

## 目前進度摘要

- `日內交易優化方案只交易一口.md` 已整理完成，且已加入 `1-6` 快覽與進度總表。
- `Changelog.md` 已整理成正式 release note 風格，版本號為 `0.2.0`，日期為 `2026-04-07`。
- `strategy/orderbook_filter.py` 已完成 `regime + session + volatility` 的動態 `spread` 調整。
- `strategy/momentum.py` 已把 `kbar.datetime` 與 `ATR ratio` 傳入 orderbook filter。
- `tests/test_strategy.py` 已補對應單元測試。
- `scripts/fetch_historical.py` 已修正 `TMF` 合約映射與時間戳轉換。
- `tests/test_fetch_historical.py`、`tests/test_backtest.py`、`tests/test_strategy.py` 已通過。

## 明天建議從哪裡接

### 優先順序

1. 先檢查目前 `strong_night` 的門檻是否還能再微調。
2. 如果要停在現狀，則把這版收斂成「可用次優版本」並整理最終結論。
3. 如果要繼續優化，則只做最小變更，不要同時改 `normal`、`day`、`night` 多個維度。

### 目前最自然的下一步

- 只調 `strategy/orderbook_filter.py` 的 `spread_threshold_strong_night`
- 固定 `spread_threshold_strong_day = 5.0`
- 以小範圍回測確認夜盤是否仍過嚴或過鬆

## 明天可直接貼給我的開工指令

請從目前的 `strategy/orderbook_filter.py` 動態 spread 版本接著做，先只微調 `spread_threshold_strong_night`，保持最小變更，目標是找出 strong trend 夜盤是否還能比現在更穩定。  
請同步跑驗證集與保留集回測，並更新 `日內交易優化方案只交易一口.md` 的進度與結果；如果沒有更好的改善，就把這版收斂成可用次優版本。

## 若要直接驗證

```powershell
python -m unittest tests.test_strategy tests.test_backtest tests.test_fetch_historical
```

## 目前關鍵檔案

- `strategy/orderbook_filter.py`
- `strategy/momentum.py`
- `tests/test_strategy.py`
- `scripts/backtest_runner.py`
- `日內交易優化方案只交易一口.md`
- `Changelog.md`

