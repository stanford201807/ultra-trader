"""
UltraTrader 回測執行腳本

用法：
    python scripts/backtest_runner.py
    python scripts/backtest_runner.py --days 60 --risk aggressive
    python scripts/backtest_runner.py --data data/historical/mxf_2025.csv
"""

import sys
import argparse
from pathlib import Path
from typing import Callable, Optional

PROJECT_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from strategy.orderbook_filter import OrderbookFilter
from strategy.orderbook_profiles import ORDERBOOK_PROFILES
from risk.profile_config import normalize_risk_profile, get_orderbook_profile_for_risk


def _parse_args():
    parser = argparse.ArgumentParser(description="UltraTrader 策略回測")
    parser.add_argument("--data", type=str, default=None, help="歷史資料 CSV 路徑")
    parser.add_argument("--days", type=int, default=30, help="合成資料天數（無 CSV 時使用）")
    parser.add_argument(
        "--strategy",
        choices=["momentum", "mean_reversion"],
        default="momentum",
        help="策略",
    )
    parser.add_argument(
        "--risk",
        choices=["conservative", "balanced", "aggressive", "crisis", "dangerous"],
        default="balanced",
        help="風險等級",
    )
    parser.add_argument("--seed", type=int, default=42, help="隨機種子")
    parser.add_argument("--timeframe", type=int, default=1, help="K棒週期（分鐘）")
    parser.add_argument("--instrument", type=str, default="TMF", help="商品 (TMF/TGF)")
    parser.add_argument("--balance", type=float, default=43000.0, help="初始資金")
    parser.add_argument("--compare-orderbook", action="store_true", help="同時比較原策略與 orderbook filter 版本")
    parser.add_argument("--orderbook-profile", choices=sorted(ORDERBOOK_PROFILES.keys()), default=None, help="orderbook 參數組合（未指定時依風險等級固定映射）")
    parser.add_argument("--profile-grid", action="store_true", help="一次跑完 A1 ~ A5")
    parser.add_argument("--start-date", type=str, default=None, help="回測起始日期 YYYY-MM-DD")
    parser.add_argument("--end-date", type=str, default=None, help="回測結束日期 YYYY-MM-DD")
    parser.add_argument("--summary-only", action="store_true", help="只輸出比較摘要，不列完整報告")
    return parser.parse_args()


def _filter_data_by_date(data, start_date: Optional[str] = None, end_date: Optional[str] = None):
    filtered = data.copy()
    filtered["datetime"] = filtered["datetime"].copy()
    if start_date:
        filtered = filtered[filtered["datetime"] >= start_date]
    if end_date:
        filtered = filtered[filtered["datetime"] < f"{end_date} 23:59:59"]
    return filtered.reset_index(drop=True)


def _build_strategy_factory(strategy_name: str, orderbook_profile: Optional[str] = None) -> Callable[[], object]:
    from strategy.momentum import AdaptiveMomentumStrategy
    from strategy.mean_reversion import MeanReversionStrategy

    if strategy_name == "momentum":
        profile = ORDERBOOK_PROFILES.get(orderbook_profile or "A3", ORDERBOOK_PROFILES["A3"])

        def factory():
            return AdaptiveMomentumStrategy(orderbook_filter=OrderbookFilter(**profile))

        return factory

    return MeanReversionStrategy


def _resolve_orderbook_profile(risk_profile: str, explicit_profile: Optional[str]) -> str:
    """解析要使用的 orderbook profile：顯式優先，否則走固定映射。"""
    if explicit_profile:
        return explicit_profile
    return get_orderbook_profile_for_risk(risk_profile)


def _summarize_result(result) -> dict:
    from backtest.report import BacktestReport

    total_win = sum(trade["pnl"] for trade in result.trades if trade["pnl"] > 0)
    total_loss = abs(sum(trade["pnl"] for trade in result.trades if trade["pnl"] <= 0))
    max_dd, max_dd_pct, _ = BacktestReport._max_drawdown(result.equity_curve)
    return {
        "trades": len(result.trades),
        "pnl": result.final_balance - result.initial_balance,
        "max_drawdown": max_dd,
        "max_drawdown_pct": max_dd_pct,
        "profit_factor": 999.0 if total_loss == 0 and total_win > 0 else (total_win / total_loss if total_loss > 0 else 0.0),
        "rejects": result.orderbook_metrics.get("entry_rejected", 0),
        "entry_checks": result.orderbook_metrics.get("entry_checks", 0),
        "avg_spread_checked": result.orderbook_metrics.get("avg_spread_checked", 0.0),
        "avg_spread_at_entry": result.orderbook_metrics.get("avg_spread_at_entry", 0.0),
    }


def _print_comparison_summary(profile_name: str, baseline, filtered):
    baseline_summary = _summarize_result(baseline)
    filtered_summary = _summarize_result(filtered)
    print(f"  [{profile_name}] 比較摘要")
    print(f"  交易次數: {baseline_summary['trades']} -> {filtered_summary['trades']}")
    print(f"  總損益: {baseline_summary['pnl']:+,.0f} -> {filtered_summary['pnl']:+,.0f}")
    print(f"  最大回撤: {baseline_summary['max_drawdown']:,.0f} -> {filtered_summary['max_drawdown']:,.0f}")
    baseline_pf = "∞" if baseline_summary["profit_factor"] >= 999.0 else f"{baseline_summary['profit_factor']:.2f}"
    filtered_pf = "∞" if filtered_summary["profit_factor"] >= 999.0 else f"{filtered_summary['profit_factor']:.2f}"
    print(f"  獲利因子: {baseline_pf} -> {filtered_pf}")
    print(f"  Orderbook 拒絕次數: {filtered_summary['rejects']}")
    print(f"  檢查時平均 Spread: {filtered_summary['avg_spread_checked']:.2f}")
    print(f"  進場時平均 Spread: {filtered_summary['avg_spread_at_entry']:.2f}")
    print()


def main():
    args = _parse_args()
    risk_profile = normalize_risk_profile(args.risk)
    selected_orderbook_profile = _resolve_orderbook_profile(risk_profile, args.orderbook_profile)

    print()
    print("  UltraTrader 回測引擎")
    print("  ═══════════════════════")
    print()

    from core.logger import setup_logger
    setup_logger(console_level="ERROR")

    from backtest.data_loader import DataLoader
    from backtest.engine import BacktestEngine
    from backtest.report import BacktestReport

    if args.data:
        print(f"  載入資料: {args.data}")
        data = DataLoader.load_csv(args.data)
    else:
        print(f"  產生合成資料: {args.days} 天（seed={args.seed}）")
        data = DataLoader.generate_synthetic(
            days=args.days,
            timeframe_minutes=args.timeframe,
            seed=args.seed,
        )

    data = _filter_data_by_date(data, args.start_date, args.end_date)
    print(f"  K棒數量: {len(data)}")
    if args.start_date or args.end_date:
        print(f"  日期範圍: {args.start_date or '開始'} ~ {args.end_date or '結束'}")
    print(f"  風險等級: {risk_profile} | 預設 Orderbook: {selected_orderbook_profile}")
    print()

    engine = BacktestEngine(
        initial_balance=args.balance,
        slippage=1,
        commission=18.0,
        instrument=args.instrument,
    )

    if args.profile_grid:
        if not args.compare_orderbook:
            raise ValueError("--profile-grid 需要搭配 --compare-orderbook")
        if args.strategy != "momentum":
            raise ValueError("--profile-grid 目前只支援 momentum")

        baseline_factory = _build_strategy_factory(args.strategy, selected_orderbook_profile)
        baseline = engine.run(
            data=data,
            strategy=baseline_factory(),
            risk_profile=risk_profile,
            use_orderbook_filter=False,
        )

        if not args.summary_only:
            print("  [Baseline] 原策略")
            BacktestReport(baseline).print_report()

        for profile_name in ORDERBOOK_PROFILES:
            filtered = engine.run(
                data=data,
                strategy=_build_strategy_factory(args.strategy, profile_name)(),
                risk_profile=risk_profile,
                use_orderbook_filter=True,
            )
            if not args.summary_only:
                print(f"  [{profile_name}] 加入 filter")
                BacktestReport(filtered).print_report()
            _print_comparison_summary(profile_name, baseline, filtered)
        return

    strategy_factory = _build_strategy_factory(args.strategy, selected_orderbook_profile)
    strategy = strategy_factory()

    if args.compare_orderbook:
        if args.strategy != "momentum":
            print("  orderbook 比較目前只對 momentum 策略有意義，將仍執行但差異可能有限。")
            print()

        baseline = engine.run(
            data=data,
            strategy=_build_strategy_factory(args.strategy, selected_orderbook_profile)(),
            risk_profile=risk_profile,
            use_orderbook_filter=False,
        )
        filtered = engine.run(
            data=data,
            strategy=_build_strategy_factory(args.strategy, selected_orderbook_profile)(),
            risk_profile=risk_profile,
            use_orderbook_filter=True,
        )

        if not args.summary_only:
            print("  [Baseline] 原策略")
            BacktestReport(baseline).print_report()
            print(f"  [{selected_orderbook_profile}] 加入 filter")
            BacktestReport(filtered).print_report()
        _print_comparison_summary(selected_orderbook_profile, baseline, filtered)
    else:
        result = engine.run(data, strategy, risk_profile)
        BacktestReport(result).print_report()


if __name__ == "__main__":
    main()
