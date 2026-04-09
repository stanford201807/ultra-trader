"""
UltraTrader Dashboard — FastAPI 伺服器
提供 REST API + WebSocket 即時推送 + 靜態檔案
"""

import asyncio
import math
from pathlib import Path
from contextlib import asynccontextmanager

from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse, JSONResponse
from fastapi.middleware.cors import CORSMiddleware

from dashboard.schemas.backtest import BacktestRunRequest
from dashboard.services.backtest_service import run_backtest as run_backtest_service
from dashboard.websocket import DashboardWebSocket


def _sanitize_for_json(obj):
    """遞迴清理 NaN/Infinity，替換為 None（JSON 不支援 NaN/Inf）"""
    if isinstance(obj, float):
        if math.isnan(obj) or math.isinf(obj):
            return None
        return obj
    if isinstance(obj, dict):
        return {k: _sanitize_for_json(v) for k, v in obj.items()}
    if isinstance(obj, (list, tuple)):
        return [_sanitize_for_json(v) for v in obj]
    return obj

# 全域引用
_engine = None
_ws_manager = DashboardWebSocket()

STATIC_DIR = Path(__file__).parent / "static"


def _build_pm_account_snapshot(engine, positions: list[dict]) -> dict:
    """以 PositionManager 狀態組裝帳戶快照。"""
    pm = engine.position_manager
    prices = {}
    for inst in engine.instruments:
        pipeline = engine.pipelines.get(inst)
        if pipeline:
            prices[inst] = pipeline.aggregator.current_price
    total_unrealized = pm.get_total_unrealized_pnl(prices)
    balance = pm.balance
    equity = balance + total_unrealized
    margin_used = pm.get_total_margin_used()
    return {
        "account": {
            "equity": round(equity, 0),
            "balance": round(balance, 0),
            "margin_used": round(margin_used, 0),
            "margin_available": round(equity - margin_used, 0),
            "unrealized_pnl": round(total_unrealized, 0),
        },
        "positions": positions,
    }


def _build_mode_switch_config(engine, mode: str) -> dict:
    """模式切換時保留目前執行參數，避免重新初始化後回到預設值。"""
    return {
        "trading_mode": mode,
        "risk_profile": engine.risk_profile,
        "timeframe": engine.timeframe,
        "instruments": list(engine.instruments),
        "auto_trade": engine.auto_trade,
    }


def _resolve_close_targets(engine, code: str) -> tuple[str, str]:
    """
    解析平倉目標：
    - `order_target`：實際送單用，可為內部商品代碼或真實合約碼
    - `sync_instrument`：若能對回引擎持倉則同步平倉，否則留空
    """
    if not code:
        return "", ""

    broker = getattr(engine, "broker", None)
    if broker and hasattr(broker, "resolve_instrument_from_code"):
        instrument = broker.resolve_instrument_from_code(code)
        if instrument:
            return instrument, instrument
        return code, ""

    for instrument in engine.instruments:
        if code.startswith(instrument):
            return instrument, instrument

    return code, ""


@asynccontextmanager
async def lifespan(app: FastAPI):
    """應用生命週期"""
    # 啟動：開始處理 WebSocket 佇列 + 啟動引擎
    queue_task = asyncio.create_task(_ws_manager.process_queue())

    if _engine:
        _engine.set_ws_broadcast(_ws_manager.broadcast_sync)
        _engine.start()

    yield

    # 關閉
    queue_task.cancel()
    if _engine:
        _engine.stop()


def create_app(engine=None) -> FastAPI:
    """建立 FastAPI 應用"""
    global _engine
    _engine = engine

    app = FastAPI(title="UltraTrader Dashboard", lifespan=lifespan)

    # CORS
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # ---- 靜態檔案 ----
    # 注意：index.html 走 `/`，其餘靜態資源走 `/static/*`
    app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")

    # ---- 靜態檔案 ----
    @app.get("/")
    async def index():
        return FileResponse(STATIC_DIR / "index.html", headers={
            "Cache-Control": "no-cache, no-store, must-revalidate",
            "Pragma": "no-cache",
            "Expires": "0",
        })

    @app.get("/backtest")
    async def backtest_page():
        return FileResponse(STATIC_DIR / "backtest" / "index.html", headers={
            "Cache-Control": "no-cache, no-store, must-revalidate",
            "Pragma": "no-cache",
            "Expires": "0",
        })

    # ---- REST API ----

    @app.get("/api/state")
    async def get_state():
        """取得引擎完整狀態"""
        if not _engine:
            return JSONResponse({"error": "引擎未初始化"}, status_code=503)
        state = _engine.get_state()
        return _sanitize_for_json(state)

    @app.get("/api/trades")
    async def get_trades():
        """取得交易紀錄"""
        if not _engine:
            return []
        return _engine.get_trade_history()

    @app.delete("/api/trades/{trade_id}")
    async def delete_trade(trade_id: str):
        """刪除單筆交易紀錄"""
        if not _engine:
            from fastapi.responses import JSONResponse
            return JSONResponse({"error": "引擎未初始化"}, status_code=503)
        success = _engine.delete_trade(trade_id)
        if success:
            return {"status": "ok", "message": f"Deleted trade {trade_id}"}
        from fastapi.responses import JSONResponse
        return JSONResponse({"error": "Trade not found or failed to delete"}, status_code=404)

    @app.put("/api/trades/{trade_id}")
    async def update_trade(trade_id: str, updates: dict):
        """修改單筆交易紀錄"""
        if not _engine:
            from fastapi.responses import JSONResponse
            return JSONResponse({"error": "引擎未初始化"}, status_code=503)
        success = _engine.update_trade(trade_id, updates)
        if success:
            return {"status": "ok", "message": f"Updated trade {trade_id}"}
        from fastapi.responses import JSONResponse
        return JSONResponse({"error": "Trade not found or failed to update"}, status_code=404)

    @app.get("/api/kbars")
    async def get_kbars(timeframe: int = 1, count: int = 200, instrument: str = ""):
        """取得 K 棒資料（可指定商品）"""
        if not _engine:
            return []
        return _engine.get_kbars(timeframe, count, instrument=instrument)

    @app.get("/api/stats")
    async def get_stats():
        """取得績效統計"""
        if not _engine:
            return {}
        return _engine.get_stats()

    @app.get("/api/intelligence")
    async def get_intelligence():
        """取得左側交易情報"""
        if not _engine or not _engine.data_collector:
            return {}
        try:
            snapshot = _engine.data_collector.snapshot
            if _engine.left_side_engine:
                _engine.left_side_engine.calculate(snapshot)
            return snapshot.to_dict()
        except Exception:
            return {}

    @app.post("/api/intelligence/refresh")
    async def refresh_intelligence():
        """手動觸發情報資料更新"""
        if not _engine or not _engine.data_collector:
            return JSONResponse({"error": "Intelligence 模組未初始化"}, status_code=503)
        import threading
        threading.Thread(
            target=_engine.data_collector.fetch_all,
            daemon=True,
        ).start()
        return {"status": "ok", "message": "資料更新中..."}

    # ---- 績效 API ----

    @app.get("/api/performance/daily/{date}")
    async def get_daily_performance(date: str):
        """取得指定日期績效 JSON"""
        if not _engine or not hasattr(_engine, 'performance') or not _engine.performance:
            return JSONResponse({"error": "績效模組未初始化"}, status_code=503)
        data = _engine.performance.get_daily_summary(date)
        if not data:
            return JSONResponse({"error": f"找不到 {date} 的績效資料"}, status_code=404)
        return data

    @app.get("/api/performance/latest")
    async def get_latest_daily():
        """取得最新一天的績效（即使引擎未啟動也能讀取）"""
        if _engine and hasattr(_engine, 'performance') and _engine.performance:
            return _engine.performance.get_latest_daily() or {}
        # fallback: 直接讀最新檔案
        import json
        daily_dir = Path(__file__).parent.parent / "data" / "performance" / "daily"
        if daily_dir.exists():
            files = sorted([f for f in daily_dir.glob("*.json") if not f.stem.endswith("_live")], reverse=True)
            if files:
                with open(files[0], "r", encoding="utf-8") as f:
                    return json.load(f)
        return {}

    @app.get("/api/performance/cumulative")
    async def get_cumulative():
        """取得累計績效（即使引擎未啟動也能讀取）"""
        if _engine and hasattr(_engine, 'performance') and _engine.performance:
            return _engine.performance.get_cumulative() or {}
        # fallback: 直接讀檔
        import json
        cum_path = Path(__file__).parent.parent / "data" / "performance" / "cumulative.json"
        if cum_path.exists():
            with open(cum_path, "r", encoding="utf-8") as f:
                return json.load(f)
        return {}

    @app.get("/api/performance/weekly/{week}")
    async def get_weekly_performance(week: str):
        """取得指定週績效，如 2026-W10"""
        if not _engine or not hasattr(_engine, 'performance') or not _engine.performance:
            return JSONResponse({"error": "績效模組未初始化"}, status_code=503)
        data = _engine.performance.get_weekly_summary(week)
        if not data:
            return JSONResponse({"error": f"找不到 {week} 的績效資料"}, status_code=404)
        return data

    @app.get("/api/performance/monthly/{month}")
    async def get_monthly_performance(month: str):
        """取得指定月績效，如 2026-03"""
        if not _engine or not hasattr(_engine, 'performance') or not _engine.performance:
            return JSONResponse({"error": "績效模組未初始化"}, status_code=503)
        data = _engine.performance.get_monthly_summary(month)
        if not data:
            return JSONResponse({"error": f"找不到 {month} 的績效資料"}, status_code=404)
        return data

    # ---- 發文接口 ----

    @app.get("/api/publish/daily-post")
    async def get_daily_post_content(date: str = None):
        """生成當日績效文案（結構化）"""
        if not _engine or not hasattr(_engine, 'performance') or not _engine.performance:
            return JSONResponse({"error": "績效模組未初始化"}, status_code=503)
        return _engine.performance.get_post_content(date)

    # ---- 活動日誌 API ----

    @app.get("/api/activity")
    async def get_activity_log(count: int = 50):
        """取得即時活動日誌"""
        if not _engine or not hasattr(_engine, 'performance') or not _engine.performance:
            return []
        return _engine.performance.get_activity_log(count)

    @app.post("/api/backtest/run")
    async def run_backtest_api(body: BacktestRunRequest):
        """執行回測並回傳摘要/報告。"""
        return _execute_backtest_run(body)

    @app.get("/api/real-account")
    async def get_real_account():
        """從 Shioaji 查詢真實帳戶資訊，查不到時 fallback 到引擎 PositionManager"""
        if not _engine or not _engine.broker:
            return JSONResponse({"error": "Broker 未初始化"}, status_code=503)
        try:
            if _engine.trading_mode == "paper" and _engine.position_manager:
                return _build_pm_account_snapshot(_engine, [])

            positions = []
            if hasattr(_engine.broker, 'get_real_positions'):
                positions = _engine.broker.get_real_positions()

            info = _engine.broker.get_account_info()

            # Shioaji 期貨帳戶無法 API 查餘額，fallback 到 PositionManager
            if info.equity <= 0 and info.balance <= 0 and _engine.position_manager:
                return _build_pm_account_snapshot(_engine, positions)

            return {
                "account": {
                    "equity": info.equity,
                    "balance": info.balance,
                    "margin_used": info.margin_used,
                    "margin_available": info.margin_available,
                    "unrealized_pnl": info.unrealized_pnl,
                },
                "positions": positions,
            }
        except Exception as e:
            return JSONResponse({"error": str(e)}, status_code=500)

    @app.post("/api/engine/{action}")
    async def engine_action(action: str, instrument: str = ""):
        """引擎控制"""
        if not _engine:
            return JSONResponse({"error": "引擎未初始化"}, status_code=503)

        if action == "start":
            _engine.start()
        elif action == "stop":
            _engine.stop()
        elif action == "pause":
            _engine.pause()
        elif action == "resume":
            _engine.resume()
        elif action == "close":
            _engine.manual_close(instrument=instrument)
        else:
            return JSONResponse({"error": f"未知操作: {action}"}, status_code=400)

        return {"status": "ok", "state": _engine.state.value}

    @app.post("/api/manual-open")
    async def manual_open(body: dict):
        """手動建倉"""
        if not _engine:
            return JSONResponse({"error": "引擎未初始化"}, status_code=503)
        instrument = body.get("instrument", "")
        side = body.get("side", "")
        quantity = int(body.get("quantity", 1))
        stop_loss = float(body.get("stop_loss", 0))
        take_profit = float(body.get("take_profit", 0))
        if side not in ("BUY", "SELL"):
            return JSONResponse({"error": f"無效方向: {side}，需要 BUY 或 SELL"}, status_code=400)
        result = _engine.manual_open(
            instrument=instrument, side=side, quantity=quantity,
            stop_loss=stop_loss, take_profit=take_profit,
        )
        if "error" in result:
            return JSONResponse(result, status_code=400)
        return result

    @app.post("/api/close-position")
    async def close_real_position(body: dict):
        """直接透過 Shioaji 平倉"""
        if not _engine or not _engine.broker:
            return JSONResponse({"error": "引擎未初始化"}, status_code=503)
        code = body.get("code", "")
        direction = body.get("direction", "")
        quantity = int(body.get("quantity", 1))
        # 反向下單平倉
        action = "BUY" if "Sell" in direction else "SELL"
        order_target, sync_instrument = _resolve_close_targets(_engine, code)
        if not order_target:
            return JSONResponse({"error": f"找不到對應商品: {code}"}, status_code=400)
        # Paper 模式不允許透過此 API 平倉（只操作引擎虛擬持倉）
        if _engine.trading_mode == "paper":
            if sync_instrument:
                _engine.manual_close(instrument=sync_instrument)
            return {"status": "ok", "action": action, "price": 0, "note": "paper mode - no real order"}
        result = _engine.broker.place_order(
            action=action, quantity=quantity, price_type="MKT", instrument=order_target,
        )
        if not result.success:
            return JSONResponse({"error": result.message}, status_code=400)
        # 同時關閉引擎持倉
        if sync_instrument:
            _engine.manual_close(instrument=sync_instrument)
        return {"status": "ok", "action": action, "price": result.fill_price, "target": order_target}

    @app.get("/api/instruments")
    async def get_instruments():
        """取得所有商品資訊"""
        if not _engine:
            return []
        return {
            "instruments": _engine.instruments,
            "data": _engine.get_state().get("instruments_data", {}),
        }

    @app.post("/api/settings")
    async def update_settings(settings: dict):
        """更新設定"""
        if not _engine:
            return JSONResponse({"error": "引擎未初始化"}, status_code=503)

        if "risk_profile" in settings:
            try:
                canonical = _engine.set_risk_profile(settings["risk_profile"])
            except ValueError as e:
                return JSONResponse({"error": str(e)}, status_code=400)
            return {"status": "ok", "risk_profile": canonical}

        return {"status": "ok"}

    @app.get("/api/auto-trade")
    async def get_auto_trade():
        """取得自動交易狀態"""
        if not _engine:
            return JSONResponse({"error": "引擎未初始化"}, status_code=503)
        return {"auto_trade": _engine.auto_trade}

    @app.post("/api/auto-trade")
    async def toggle_auto_trade(body: dict):
        """切換自動交易"""
        if not _engine:
            return JSONResponse({"error": "引擎未初始化"}, status_code=503)
        enabled = body.get("enabled", False)
        result = _engine.toggle_auto_trade(enabled)
        return {"status": "ok", "auto_trade": result}

    @app.post("/api/mode/{mode}")
    async def switch_mode(mode: str):
        """
        切換交易模式（simulation / paper / live）
        需要重啟引擎
        """
        if not _engine:
            return JSONResponse({"error": "引擎未初始化"}, status_code=503)

        valid_modes = ["simulation", "paper", "live"]
        if mode not in valid_modes:
            return JSONResponse({"error": f"無效模式: {mode}，可選: {valid_modes}"}, status_code=400)

        if mode == _engine.trading_mode:
            return {"status": "ok", "message": f"已經在 {mode} 模式", "mode": mode}

        init_config = _build_mode_switch_config(_engine, mode)

        # 先停止，切換模式，再重新初始化和啟動
        _engine.stop()
        import os
        os.environ["TRADING_MODE"] = mode
        _engine.trading_mode = mode

        success = _engine.initialize(init_config)
        if not success:
            return JSONResponse({"error": f"切換到 {mode} 失敗，請檢查 .env 設定"}, status_code=500)

        _engine.set_ws_broadcast(_ws_manager.broadcast_sync)
        _engine.start()

        return {"status": "ok", "message": f"已切換到 {mode} 模式", "mode": mode}

    @app.get("/api/modes")
    async def get_available_modes():
        """取得可用模式列表"""
        current = _engine.trading_mode if _engine else "unknown"
        return {
            "current": current,
            "available": [
                {"id": "simulation", "label": "模擬交易", "description": "本地模擬行情，不需要 API"},
                {"id": "paper", "label": "紙上交易", "description": "真實行情，不實際下單"},
                {"id": "live", "label": "實盤交易", "description": "真實行情 + 真實下單"},
            ],
        }

    # ---- WebSocket ----

    @app.websocket("/ws")
    async def websocket_endpoint(ws: WebSocket):
        await _ws_manager.connect(ws)

        # 連線後立即推送完整狀態
        if _engine:
            try:
                await ws.send_json({"type": "state", "data": _engine.get_state()})
            except Exception:
                pass

        try:
            while True:
                # 保持連線，接收客戶端訊息（如果有的話）
                data = await ws.receive_text()
                # 可以處理客戶端命令
        except WebSocketDisconnect:
            await _ws_manager.disconnect(ws)
        except Exception:
            await _ws_manager.disconnect(ws)

    return app


def _execute_backtest_run(body: BacktestRunRequest) -> dict | JSONResponse:
    """獨立可測的回測執行包裝。"""
    try:
        result = run_backtest_service(body)
        return _sanitize_for_json(result)
    except ValueError as exc:
        return JSONResponse({"error": str(exc)}, status_code=400)
    except FileNotFoundError as exc:
        return JSONResponse({"error": str(exc)}, status_code=404)
    except Exception as exc:
        return JSONResponse({"error": f"回測執行失敗: {exc}"}, status_code=500)
