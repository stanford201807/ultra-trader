"""
UltraTrader 部位管理
追蹤持倉、記錄交易、計算績效
"""

import threading
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Optional
import json
import os
import uuid
from pathlib import Path


class Side(Enum):
    FLAT = "flat"
    LONG = "long"
    SHORT = "short"


@dataclass
class Position:
    """當前持倉"""
    side: Side = Side.FLAT
    entry_price: float = 0.0
    quantity: int = 0
    entry_time: Optional[datetime] = None
    stop_loss: float = 0.0
    take_profit: float = 0.0
    trailing_stop: float = 0.0
    trailing_activated: bool = False
    breakeven_activated: bool = False       # 保本停損已啟動
    max_unrealized_profit: float = 0.0     # 最大未實現獲利（點數）
    highest_since_entry: float = 0.0
    lowest_since_entry: float = 999999.0
    bars_since_entry: int = 0
    # 分段停利：[(price, fraction), ...]
    take_profit_levels: list = field(default_factory=list)
    original_quantity: int = 0  # 原始數量（分段出場用）

    # 績效追蹤
    strategy: str = ""
    market_regime: str = ""
    signal_strength: float = 0.0

    @property
    def is_flat(self) -> bool:
        return self.side == Side.FLAT

    def unrealized_pnl(self, current_price: float, point_value: float = 1.0) -> float:
        """計算未實現損益"""
        if self.is_flat:
            return 0.0
        if self.side == Side.LONG:
            return (current_price - self.entry_price) * self.quantity * point_value
        else:  # SHORT
            return (self.entry_price - current_price) * self.quantity * point_value

    def unrealized_points(self, current_price: float) -> float:
        """計算未實現點數"""
        if self.is_flat:
            return 0.0
        if self.side == Side.LONG:
            return (current_price - self.entry_price) * self.quantity
        else:
            return (self.entry_price - current_price) * self.quantity


@dataclass
class Trade:
    """已完成的交易紀錄"""
    entry_time: datetime
    exit_time: datetime
    side: str  # "long" / "short"
    entry_price: float
    exit_price: float
    quantity: int
    pnl: float  # 損益（元）
    pnl_points: float  # 損益（點）
    commission: float  # 手續費
    reason: str  # 出場原因
    bars_held: int = 0  # 持倉 K 棒數
    instrument: str = ""  # 商品代碼
    id: str = field(default_factory=lambda: str(uuid.uuid4()))  # 交易紀錄唯一識別碼

    # === 績效追蹤新增欄位 ===
    strategy: str = ""                  # "momentum" / "mean_reversion"
    market_regime: str = ""             # "TRENDING_UP" / "RANGING" / etc.
    signal_strength: float = 0.0        # 進場信號強度 0-1
    max_favorable: float = 0.0          # 最大有利點數（MFE）
    max_adverse: float = 0.0            # 最大不利點數（MAE）

    @property
    def is_winner(self) -> bool:
        return self.pnl > 0

    @property
    def net_pnl(self) -> float:
        """扣除手續費後的淨損益"""
        return self.pnl - self.commission

    def to_perf_dict(self) -> dict:
        """轉為績效記錄用 dict"""
        return {
            "entry_time": self.entry_time.isoformat() if self.entry_time else "",
            "exit_time": self.exit_time.isoformat() if self.exit_time else "",
            "side": self.side,
            "entry_price": self.entry_price,
            "exit_price": self.exit_price,
            "quantity": self.quantity,
            "pnl": self.pnl,
            "pnl_points": self.pnl_points,
            "net_pnl": self.net_pnl,
            "commission": self.commission,
            "reason": self.reason,
            "bars_held": self.bars_held,
            "strategy": self.strategy,
            "market_regime": self.market_regime,
            "signal_strength": self.signal_strength,
            "max_favorable": self.max_favorable,
            "max_adverse": self.max_adverse,
            "id": self.id,
        }


# ============================================================
# 部位管理器
# ============================================================

class PositionManager:
    """
    管理持倉狀態和交易紀錄
    支援多商品同時持倉（每個商品獨立一個 Position）
    餘額跨商品共用
    """

    def __init__(self, instruments: list[str] = None, configs: dict = None,
                 initial_balance: float = 0.0, auto_load: bool = True):
        """
        instruments: 商品代碼列表，如 ["TMF", "TGF"]
        configs: 每個商品的規格 {code: InstrumentSpec}
        """
        self.instruments = instruments or ["TMF"]
        self.configs = configs or {}
        self.initial_balance = initial_balance
        self.balance = initial_balance
        self._lock = threading.Lock()  # 線程安全鎖

        # 每個商品各一個 Position
        self.positions: dict[str, Position] = {inst: Position() for inst in self.instruments}

        # 向後相容：單商品時 self.position 指向第一個
        self.position = self.positions[self.instruments[0]]

        self.trades: list[Trade] = []
        self.daily_trades: list[Trade] = []
        self._today: Optional[str] = None
        
        if auto_load:
            self.load_daily_trades()

    def _get_config(self, instrument: str):
        """取得商品規格"""
        return self.configs.get(instrument, None)

    def open_position(
        self,
        instrument: str,
        side: Side,
        price: float,
        quantity: int,
        stop_loss: float,
        take_profit: float,
        timestamp: Optional[datetime] = None,
        take_profit_levels: list = None,
        strategy: str = "",
        market_regime: str = "",
        signal_strength: float = 0.0,
    ) -> Position:
        """開倉（指定商品）— 線程安全"""
        with self._lock:
            pos = self.positions.get(instrument)
            if pos is None:
                raise ValueError(f"未知商品: {instrument}")
            if not pos.is_flat:
                raise ValueError(f"已有 {instrument} 持倉，請先平倉")

            new_pos = Position(
                side=side,
                entry_price=price,
                quantity=quantity,
                entry_time=timestamp or datetime.now(),
                stop_loss=stop_loss,
                take_profit=take_profit,
                trailing_stop=0.0,
                trailing_activated=False,
                highest_since_entry=price,
                lowest_since_entry=price,
                bars_since_entry=0,
                take_profit_levels=take_profit_levels or [],
                original_quantity=quantity,
                strategy=strategy,
                market_regime=market_regime,
                signal_strength=signal_strength,
            )
            self.positions[instrument] = new_pos
            # 向後相容
            if instrument == self.instruments[0]:
                self.position = new_pos
            return new_pos

    def close_position(
        self,
        instrument: str,
        price: float,
        reason: str,
        timestamp: Optional[datetime] = None,
    ) -> Optional[Trade]:
        """平倉（指定商品），回傳交易紀錄 — 線程安全"""
        with self._lock:
            pos = self.positions.get(instrument)
            if pos is None or pos.is_flat:
                return None

            exit_time = timestamp or datetime.now()
            config = self._get_config(instrument)
            point_value = config.point_value if config else 10.0
            commission_rate = config.commission if config else 18.0
            tax_rate = config.tax if config else 7.0

            # 計算損益
            if pos.side == Side.LONG:
                pnl_points = (price - pos.entry_price) * pos.quantity
            else:
                pnl_points = (pos.entry_price - price) * pos.quantity

            pnl = pnl_points * point_value
            commission = (commission_rate + tax_rate) * 2 * pos.quantity

            # MFE / MAE
            if pos.side == Side.LONG:
                max_favorable = (pos.highest_since_entry - pos.entry_price) * pos.quantity
                max_adverse = (pos.entry_price - pos.lowest_since_entry) * pos.quantity
            else:
                max_favorable = (pos.entry_price - pos.lowest_since_entry) * pos.quantity
                max_adverse = (pos.highest_since_entry - pos.entry_price) * pos.quantity

            trade = Trade(
                entry_time=pos.entry_time,
                exit_time=exit_time,
                side=pos.side.value,
                entry_price=pos.entry_price,
                exit_price=price,
                quantity=pos.quantity,
                pnl=pnl,
                pnl_points=pnl_points,
                commission=commission,
                reason=reason,
                bars_held=pos.bars_since_entry,
                max_favorable=max_favorable,
                max_adverse=max_adverse,
                instrument=instrument,
                strategy=pos.strategy,
                market_regime=pos.market_regime,
                signal_strength=pos.signal_strength,
            )

            self.trades.append(trade)
            self._update_daily_trades(trade)
            self.balance += trade.net_pnl
            
            # 持久化當日紀錄
            self.save_daily_trades()

            # 清空持倉
            self.positions[instrument] = Position()
            if instrument == self.instruments[0]:
                self.position = self.positions[instrument]
            return trade

    def update_price(self, instrument: str, price: float):
        """更新指定商品的當前價格（追蹤最高/最低價）"""
        with self._lock:
            pos = self.positions.get(instrument)
            if pos is None or pos.is_flat:
                return
            pos.highest_since_entry = max(pos.highest_since_entry, price)
            pos.lowest_since_entry = min(pos.lowest_since_entry, price)

    def increment_bars(self, instrument: str):
        """K 棒收盤，增加指定商品的持倉 K 棒計數"""
        with self._lock:
            pos = self.positions.get(instrument)
            if pos and not pos.is_flat:
                pos.bars_since_entry += 1

    def get_total_unrealized_pnl(self, prices: dict[str, float]) -> float:
        """計算所有商品的未實現損益總和"""
        total = 0.0
        for inst in self.instruments:
            pos = self.positions[inst]
            if not pos.is_flat and inst in prices:
                config = self._get_config(inst)
                pv = config.point_value if config else 1.0
                total += pos.unrealized_pnl(prices[inst], pv)
        return total

    def get_total_margin_used(self) -> float:
        """計算所有持倉佔用的保證金"""
        total = 0.0
        for inst in self.instruments:
            pos = self.positions[inst]
            if not pos.is_flat:
                config = self._get_config(inst)
                margin = config.margin if config else 20600
                total += margin * pos.quantity
        return total

    def _update_daily_trades(self, trade: Trade):
        """更新每日交易紀錄"""
        today = trade.exit_time.strftime("%Y-%m-%d")
        if self._today != today:
            self._today = today
            self.daily_trades = []
        self.daily_trades.append(trade)

    # ---- 統計 ----

    def get_daily_pnl(self) -> float:
        """今日已實現損益"""
        return sum(t.net_pnl for t in self.daily_trades)

    def get_daily_trade_count(self) -> int:
        """今日交易次數（自動重置隔天計數）"""
        today = datetime.now().strftime("%Y-%m-%d")
        if self._today != today:
            self._today = today
            self.daily_trades = []
        return len(self.daily_trades)

    def get_consecutive_losses(self) -> int:
        """當前連續虧損次數"""
        count = 0
        for trade in reversed(self.daily_trades):
            if trade.net_pnl < 0:
                count += 1
            else:
                break
        return count

    def get_stats(self) -> dict:
        """計算整體績效統計"""
        if not self.trades:
            return {
                "total_trades": 0,
                "win_rate": 0.0,
                "avg_win": 0.0,
                "avg_loss": 0.0,
                "profit_factor": 0.0,
                "total_pnl": 0.0,
                "max_drawdown": 0.0,
            }

        winners = [t for t in self.trades if t.net_pnl > 0]
        losers = [t for t in self.trades if t.net_pnl <= 0]

        total_wins = sum(t.net_pnl for t in winners) if winners else 0
        total_losses = abs(sum(t.net_pnl for t in losers)) if losers else 0

        equity_curve = []
        running = 0.0
        for t in self.trades:
            running += t.net_pnl
            equity_curve.append(running)

        max_dd = 0.0
        peak = 0.0
        for eq in equity_curve:
            peak = max(peak, eq)
            dd = peak - eq
            max_dd = max(max_dd, dd)

        return {
            "total_trades": len(self.trades),
            "winners": len(winners),
            "losers": len(losers),
            "win_rate": len(winners) / len(self.trades) * 100 if self.trades else 0,
            "avg_win": total_wins / len(winners) if winners else 0,
            "avg_loss": total_losses / len(losers) if losers else 0,
            "profit_factor": total_wins / total_losses if total_losses > 0 else 999.0,
            "total_pnl": sum(t.net_pnl for t in self.trades),
            "max_drawdown": max_dd,
            "avg_bars_held": sum(t.bars_held for t in self.trades) / len(self.trades),
        }

    def to_dict(self, prices: dict[str, float] = None) -> dict:
        """序列化為 dict（供 Dashboard 顯示）— 多商品版本"""
        prices = prices or {}
        result = {}
        for inst in self.instruments:
            pos = self.positions[inst]
            price = prices.get(inst, 0.0)
            config = self._get_config(inst)
            pv = config.point_value if config else 1.0
            result[inst] = {
                "side": pos.side.value,
                "entry_price": pos.entry_price,
                "quantity": pos.quantity,
                "entry_time": pos.entry_time.isoformat() if pos.entry_time else None,
                "stop_loss": pos.stop_loss,
                "take_profit": pos.take_profit,
                "trailing_stop": pos.trailing_stop,
                "trailing_activated": pos.trailing_activated,
                "bars_since_entry": pos.bars_since_entry,
                "unrealized_pnl": pos.unrealized_pnl(price, pv),
                "unrealized_points": pos.unrealized_points(price),
            }
        return result

    # ============================================================
    # 持久化與增刪查改 (Persistence & CRUD)
    # ============================================================

    def _get_daily_trades_path(self) -> Path:
        """取得今日交易紀錄檔案路徑"""
        today = datetime.now().strftime("%Y-%m-%d")
        trades_dir = Path("data/trades")
        trades_dir.mkdir(parents=True, exist_ok=True)
        return trades_dir / f"daily_trades_{today}.json"

    def load_daily_trades(self):
        """啟動時載入當日的歷史交易紀錄"""
        path = self._get_daily_trades_path()
        if not path.exists():
            return
            
        try:
            with open(path, "r", encoding="utf-8") as f:
                data = json.load(f)
                
            self.trades = []
            for t_dict in data:
                # 解析時間
                entry_time = datetime.fromisoformat(t_dict["entry_time"]) if t_dict.get("entry_time") else None
                exit_time = datetime.fromisoformat(t_dict["exit_time"]) if t_dict.get("exit_time") else None
                
                trade = Trade(
                    entry_time=entry_time,
                    exit_time=exit_time,
                    side=t_dict["side"],
                    entry_price=t_dict["entry_price"],
                    exit_price=t_dict["exit_price"],
                    quantity=t_dict["quantity"],
                    pnl=t_dict["pnl"],
                    pnl_points=t_dict["pnl_points"],
                    commission=t_dict["commission"],
                    reason=t_dict["reason"],
                    bars_held=t_dict.get("bars_held", 0),
                    instrument=t_dict.get("instrument", ""),
                    strategy=t_dict.get("strategy", ""),
                    market_regime=t_dict.get("market_regime", ""),
                    signal_strength=t_dict.get("signal_strength", 0.0),
                    max_favorable=t_dict.get("max_favorable", 0.0),
                    max_adverse=t_dict.get("max_adverse", 0.0),
                    id=t_dict.get("id", str(uuid.uuid4())),
                )
                self.trades.append(trade)
                
            # 重建 daily_trades
            self.daily_trades = self.trades.copy()
            self._today = datetime.now().strftime("%Y-%m-%d")
            
            # 從 trades 重新累加初始餘額
            self.balance = self.initial_balance + sum(t.net_pnl for t in self.trades)
            
            # import loguru (防呆確認 logger 可用)
            from loguru import logger
            logger.info(f"[PositionManager] 成功載入當日交易紀錄: {len(self.trades)} 筆")
        except Exception as e:
            from loguru import logger
            logger.error(f"[PositionManager] 載入當日交易紀錄失敗: {e}")

    def save_daily_trades(self):
        """將當日交易紀錄寫入 JSON（包含觀盤模式的紀錄）"""
        path = self._get_daily_trades_path()
        try:
            data = [t.to_perf_dict() for t in self.trades]
            with open(path, "w", encoding="utf-8") as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
        except Exception as e:
            from loguru import logger
            logger.error(f"[PositionManager] 儲存當日交易紀錄失敗: {e}")

    def delete_trade(self, trade_id: str) -> bool:
        """刪除指定交易紀錄，並重新計算餘額"""
        with self._lock:
            initial_count = len(self.trades)
            self.trades = [t for t in self.trades if t.id != trade_id]
            self.daily_trades = [t for t in self.daily_trades if t.id != trade_id]
            
            if len(self.trades) < initial_count:
                # 重新計算餘額
                self.balance = self.initial_balance + sum(t.net_pnl for t in self.trades)
                self.save_daily_trades()
                from loguru import logger
                logger.info(f"[PositionManager] 成功刪除交易紀錄 {trade_id}")
                return True
            return False

    def update_trade(self, trade_id: str, updates: dict) -> bool:
        """修改指定交易紀錄，並重新計算餘額"""
        with self._lock:
            for t in self.trades:
                if t.id == trade_id:
                    # 允許修改特定欄位
                    if "pnl" in updates: t.pnl = float(updates["pnl"])
                    if "pnl_points" in updates: t.pnl_points = float(updates["pnl_points"])
                    if "commission" in updates: t.commission = float(updates["commission"])
                    if "entry_price" in updates: t.entry_price = float(updates["entry_price"])
                    if "exit_price" in updates: t.exit_price = float(updates["exit_price"])
                    if "reason" in updates: t.reason = str(updates["reason"])
                    
                    self.balance = self.initial_balance + sum(t_inner.net_pnl for t_inner in self.trades)
                    self.save_daily_trades()
                    from loguru import logger
                    logger.info(f"[PositionManager] 成功修改交易紀錄 {trade_id}")
                    return True
            return False
