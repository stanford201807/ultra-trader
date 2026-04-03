"""
UltraTrader 風控狀態持久化
peak_equity、熔斷狀態、每日損益 — 重啟不遺失
"""

import json
from datetime import datetime
from pathlib import Path
from typing import Optional

from loguru import logger


STATE_FILE = Path(__file__).parent.parent / "data" / "risk_state.json"


def save_risk_state(
    peak_equity: float,
    daily_loss: float,
    consecutive_losses: int,
    circuit_state: str,
    halt_reason: str,
    today: str,
):
    """儲存風控狀態到磁碟"""
    state = {
        "peak_equity": peak_equity,
        "daily_loss": daily_loss,
        "consecutive_losses": consecutive_losses,
        "circuit_state": circuit_state,
        "halt_reason": halt_reason,
        "today": today,
        "updated_at": datetime.now().isoformat(),
    }
    try:
        STATE_FILE.parent.mkdir(parents=True, exist_ok=True)
        STATE_FILE.write_text(json.dumps(state, ensure_ascii=False, indent=2), encoding="utf-8")
    except Exception as e:
        logger.error(f"[Persist] 儲存風控狀態失敗: {e}")


def load_risk_state() -> Optional[dict]:
    """從磁碟載入風控狀態"""
    try:
        if STATE_FILE.exists():
            data = json.loads(STATE_FILE.read_text(encoding="utf-8"))
            logger.info(f"[Persist] 載入風控狀態: peak={data.get('peak_equity', 0):,.0f} daily_loss={data.get('daily_loss', 0):,.0f} state={data.get('circuit_state', 'active')}")
            return data
    except Exception as e:
        logger.warning(f"[Persist] 載入風控狀態失敗: {e}")
    return None
