# UltraTrader

**台灣期貨自動交易系統 — 開源**

**[English](#english) | [繁體中文](#繁體中文)**

---

<a name="english"></a>

## What is this?

UltraTrader is an open-source algorithmic trading system for Taiwan futures (TAIFEX), built with Python and Shioaji (Sinopac Securities API).

Features:
- **3 built-in strategies**: Adaptive Momentum, Mean Reversion, Gold Trend
- **Full risk management**: Circuit breaker, position sizing, drawdown protection
- **Auto-trade toggle**: One-click to enable/disable automatic order execution from signals
- **Backtesting engine**: Historical data replay with detailed reports
- **Real-time dashboard**: FastAPI + WebSocket live monitoring
- **Market intelligence**: Multi-timeframe regime detection
- **3 trading modes**: Simulation (local) → Paper (Sinopac sandbox) → Live

Zero cloud dependencies. Runs entirely on your machine.

## Architecture

```
UltraTrader/
├── core/           # Engine, broker API, market data, position management
│   └── engine/     # Engine facade split: events/executor/queries/health/models
├── strategy/       # Trading strategies (momentum, mean_reversion, gold_trend)
├── risk/           # Circuit breaker, position sizing, drawdown limits
├── backtest/       # Backtesting engine + report generator
├── dashboard/      # FastAPI + WebSocket real-time UI
├── intelligence/   # Market regime classifier, signal scoring
├── scripts/        # CLI tools (start, backtest, diagnostics)
├── tests/          # Unit tests
└── data/           # Historical data, backtest results (gitignored)
```

## Quick Start

```bash
git clone https://github.com/ppcvote/ultra-trader.git
cd ultra-trader
pip install -r requirements.txt
cp .env.example .env
# Edit .env (simulation mode works without API keys)
python scripts/start.py
```

### Trading Modes

| Mode | What it does | Needs API key? |
|------|-------------|----------------|
| `simulation` | Local mock broker, fake ticks | No |
| `paper` | Sinopac sandbox, real market data | Yes |
| `live` | Real money, real orders | Yes + CA cert |

### Run Backtest

```bash
python scripts/backtest_runner.py
# Results saved to data/backtest_results/
```

### Run Tests

Pytest is configured to only collect tests under `tests/` (see `pytest.ini`).

```bash
python -m pytest -q
```

Risk + orderbook mapping (default):
- If `--orderbook-profile` is omitted, it will auto-map from risk:
  - `conservative -> A1`
  - `balanced -> A3`
  - `aggressive -> A4`
  - `crisis` (or alias `dangerous`) `-> A5`

### Dashboard

```bash
python scripts/start.py --port 8888
# Open http://localhost:8888
```

UI accessibility:
- Top-right font controls (`A-`, `100%`, `A+`)
- Adjustable range: `85%` to `200%`
- Click percentage button to reset to `100%`

Auto-Trade:
- When the engine is running, a `🤖 Auto-Trade` button appears next to Pause/Stop
- **Off (default)**: signals are detected and broadcast but no orders are placed
- **On**: the engine automatically executes entry orders based on strategy signals
- In `live` mode, enabling auto-trade requires a confirmation dialog
- Exit logic (stop-loss, take-profit, strategy exits) always runs regardless of the toggle

## Strategies

### Adaptive Momentum (Primary)
- 7-factor entry signals with multi-timeframe confirmation (5m/15m)
- Session-aware: higher thresholds at open, no new positions near close
- Chandelier Exit + continuous adaptive stop-loss
- Partial take-profit at 2x/3x/4x ATR (1/3 each)
- Slippage buffer on all stops

### Mean Reversion
- Bollinger Band extremes + RSI divergence
- Best in ranging/sideways markets
- Tight stops, quick exits

### Gold Trend
- Designed for gold futures (TGF)
- Trend-following with momentum filters

## Risk Management

- **Circuit Breaker**: Auto-stop trading after N consecutive losses or daily loss limit
- **Position Sizing**: Kelly criterion with configurable risk profiles (conservative/balanced/aggressive/crisis; dangerous alias -> crisis)
- **Drawdown Protection**: Max drawdown % triggers trading halt
- **Session Management**: No new positions in last 30 min, force close in last 5 min

Risk profile validation:
- All entry points normalize and validate risk profile (`start` CLI, dashboard settings API, engine, backtest runner)
- Invalid values are rejected explicitly (no silent fallback)

## Tech Stack

- **Language**: Python 3.10+
- **Broker API**: [Shioaji](https://sinotrade.github.io/) (Sinopac Securities)
- **Dashboard**: FastAPI + WebSocket
- **Data**: pandas + numpy
- **Logging**: loguru

## Disclaimer

**This software is for educational and research purposes only.** Trading futures involves substantial risk of loss. Past performance (including backtests) does not guarantee future results. Use at your own risk. The authors are not responsible for any financial losses.

---

<a name="繁體中文"></a>

## 這是什麼？

UltraTrader 是開源的台灣期貨自動交易系統，使用 Python + 永豐證券 Shioaji API。

功能：
- **3 個內建策略**：自適應動量、均值回歸、黃金趨勢
- **完整風控**：熔斷機制、部位管理、回撤保護
- **自動交易開關**：一鍵切換是否依策略信號自動下單
- **回測引擎**：歷史數據回放 + 詳細報告
- **即時儀表板**：FastAPI + WebSocket 即時監控
- **市場情報**：多時框盤勢分類
- **3 種模式**：本地模擬 → 永豐模擬盤 → 實單

完全本地運行，不需要雲端。

## 快速開始
```bash
git clone https://github.com/ppcvote/ultra-trader.git
cd ultra-trader
pip install -r requirements.txt
cp .env.example .env
# 編輯 .env（模擬模式不需要 API key）
python scripts/start.py
```

### Dashboard（儀表板）

```bash
python scripts/start.py --port 8888
# 開啟 http://localhost:8888
```

介面可用性：
- 右上角提供字體控制（`A-`、`100%`、`A+`）
- 字體可調範圍：`85%` 到 `200%`
- 點擊百分比按鈕可一鍵重置為 `100%`

自動交易：
- 引擎運行中時，暫停/停止按鈕旁會出現 `🤖 自動交易` 按鈕
- **關閉（預設）**：引擎偵測信號並廣播，但不自動下單
- **開啟**：引擎依策略信號自動執行進場下單
- `live` 模式下啟用自動交易需二次確認
- 出場邏輯（停損/停利/策略出場）始終自動執行，不受開關影響

## 策略簡介

### 自適應動量策略（主策略）
- 7 因子進場：多時框確認（5 分 K / 15 分 K）
- 盤別感知：開盤 15 分提高門檻、收盤前不開新倉
- Chandelier Exit + 連續自適應停損
- 分段停利：2x/3x/4x ATR 各出 1/3
- 含滑價修正

### 均值回歸策略
- 布林通道極端值 + RSI 背離
- 適合盤整行情
- 快進快出

### 黃金趨勢策略
- 針對黃金期貨（TGF）設計
- 趨勢跟隨 + 動量過濾

## 風控機制

- **熔斷**：連續虧損 N 次或單日虧損上限 → 自動停止交易
- **部位管理**：Kelly 公式 + 風險等級（保守/平衡/積極/危機；`dangerous` 會自動映射為 `crisis`）
- **回撤保護**：最大回撤 % 觸發交易暫停
- **盤別管理**：收盤前 30 分不開新倉、收盤前 5 分強制平倉

### 風險與 Orderbook 固定映射（預設）

當回測未指定 `--orderbook-profile` 時，會自動套用固定映射：

- `conservative -> A1`
- `balanced -> A3`
- `aggressive -> A4`
- `crisis`（或別名 `dangerous`）`-> A5`

### 風險等級入口驗證

以下入口都會做正規化與驗證：

- `scripts/start.py --risk`
- `scripts/backtest_runner.py --risk`
- Dashboard `POST /api/settings` (`risk_profile`)
- `core/engine.py` 初始化與 `set_risk_profile()`

若值不合法會明確拒絕，不再採用靜默 fallback。

## 免責聲明

**本軟體僅供教育和研究用途。** 期貨交易具有高度風險，可能導致重大損失。歷史績效（含回測）不代表未來表現。使用風險自負，作者不承擔任何財務損失責任。

---

## Credits

Built by [Ultra Lab](https://ultralab.tw) — a one-person AI product studio from Taiwan.

[![Discord](https://img.shields.io/discord/1459618830773911633?color=5865F2&label=Discord&logo=discord&logoColor=white)](https://discord.gg/ewS4rWXvWk)

## License

MIT
