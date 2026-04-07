"""
從 Shioaji 拉取 TMF 歷史 1 分鐘 K 棒，存為 CSV
用法：python scripts/fetch_historical.py --days 60
"""

import sys
import os
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

import argparse
import pickle
from datetime import datetime, timedelta, timezone
import pandas as pd
from dotenv import load_dotenv

load_dotenv()


CONTRACT_FAMILY_MAP = {
    "TMF": {"family": "TMF", "fallback": "TMFR1"},
    "TGF": {"family": "TGF", "fallback": "TGFR1"},
}


def fetch_kbars(days: int = 60, instrument: str = "TMF"):
    """從 Shioaji 拉取歷史 K 棒"""
    import shioaji as sj

    api = sj.Shioaji()

    # 登入
    api_key = os.environ.get("SHIOAJI_API_KEY")
    secret_key = os.environ.get("SHIOAJI_SECRET_KEY")
    person_id = os.environ.get("SHIOAJI_PERSON_ID")
    ca_password = os.environ.get("SHIOAJI_CA_PASSWORD")

    if not api_key or not secret_key:
        print("缺少 SHIOAJI_API_KEY / SHIOAJI_SECRET_KEY 環境變數")
        return None

    print(f"登入 Shioaji...")
    api.login(
        api_key=api_key,
        secret_key=secret_key,
        fetch_contract=False,
    )

    # 啟用 CA（某些操作需要）
    if person_id and ca_password:
        try:
            api.activate_ca(
                ca_path=os.environ.get("SHIOAJI_CA_PATH", ""),
                ca_passwd=ca_password,
                person_id=person_id,
            )
        except Exception as e:
            print(f"CA 啟用失敗（不影響行情查詢）: {e}")

    # 取得合約
    contracts = _load_local_contracts()
    if contracts is None:
        print("無法讀取本機 contracts 快取，請先確認 Shioaji 合約檔存在")
        api.logout()
        return None

    instrument_key = instrument.upper()
    if instrument_key not in CONTRACT_FAMILY_MAP:
        print(f"不支援的商品: {instrument}")
        api.logout()
        return None

    contract = _resolve_contract(contracts, instrument_key)
    if contract is None:
        print(f"找不到 {instrument_key} 可用合約")
        api.logout()
        return None

    print(f"合約: {contract.code} ({contract.name})")

    # Shioaji kbars API 有日期範圍限制，分批拉取
    all_bars = []
    end_date = datetime.now()

    # 分批拉（每批最多拉 5 天避免 API 限制）
    batch_size = 5
    remaining_days = days
    current_end = end_date

    while remaining_days > 0:
        fetch_days = min(batch_size, remaining_days)
        start = current_end - timedelta(days=fetch_days)

        start_str = start.strftime("%Y-%m-%d")
        end_str = current_end.strftime("%Y-%m-%d")

        print(f"  拉取 {start_str} ~ {end_str}...")

        try:
            kbars = api.kbars(
                contract=contract,
                start=start_str,
                end=end_str,
            )

            if kbars and hasattr(kbars, 'Close') and len(kbars.Close) > 0:
                for i in range(len(kbars.Close)):
                    raw_ts = kbars.ts[i]
                    ts = _normalize_kbar_timestamp(raw_ts)

                    all_bars.append({
                        "datetime": ts,
                        "open": float(kbars.Open[i]),
                        "high": float(kbars.High[i]),
                        "low": float(kbars.Low[i]),
                        "close": float(kbars.Close[i]),
                        "volume": int(kbars.Volume[i]),
                    })
                print(f"    {len(kbars.Close)} 根K棒")
            else:
                print(f"    無資料")
        except Exception as e:
            print(f"    拉取失敗: {e}")

        current_end = start - timedelta(days=1)
        remaining_days -= fetch_days

    if not all_bars:
        print("沒有拉到任何資料")
        api.logout()
        return None

    # 轉 DataFrame，去重排序
    df = pd.DataFrame(all_bars)
    df = df.drop_duplicates(subset=["datetime"]).sort_values("datetime").reset_index(drop=True)

    # 儲存
    data_dir = Path(__file__).parent.parent / "data" / "historical"
    data_dir.mkdir(parents=True, exist_ok=True)

    filename = f"{instrument.lower()}_{end_date.strftime('%Y%m%d')}_1m.csv"
    filepath = data_dir / filename
    df.to_csv(filepath, index=False)

    print(f"\n完成！共 {len(df)} 根K棒")
    print(f"期間: {df['datetime'].iloc[0]} ~ {df['datetime'].iloc[-1]}")
    print(f"儲存: {filepath}")

    # 最近行情摘要
    recent = df.tail(300)  # 最近 300 根（約 1 天日盤）
    if len(recent) > 0:
        print(f"\n最近行情摘要:")
        print(f"   最新價: {recent['close'].iloc[-1]:,.0f}")
        print(f"   最高價: {recent['high'].max():,.0f}")
        print(f"   最低價: {recent['low'].min():,.0f}")
        print(f"   均價:   {recent['close'].mean():,.0f}")
        print(f"   波動:   {recent['high'].max() - recent['low'].min():,.0f} 點")

    api.logout()
    return df


def _load_local_contracts():
    """讀取本機 Shioaji contracts 快取，避開登入時的 lock 問題"""
    cache_dir = Path.home() / ".shioaji"
    candidates = sorted(cache_dir.glob("contracts-*.pkl"), reverse=True)
    for path in candidates:
        try:
            with path.open("rb") as fh:
                return pickle.load(fh)
        except Exception as e:
            print(f"讀取 contracts 快取失敗: {path} | {e}")
    return None


def _resolve_contract(contracts, instrument: str):
    """依專案商品代碼解析對應的 Shioaji 合約族群。"""
    spec = CONTRACT_FAMILY_MAP.get(instrument.upper())
    if spec is None:
        return None

    futures = getattr(contracts, "Futures", None)
    family = getattr(futures, spec["family"], None) if futures is not None else None
    if family is None:
        return None

    contract_list = [
        contract
        for contract in family
        if hasattr(contract, "delivery_month") and contract.delivery_month
    ]
    if contract_list:
        return min(contract_list, key=lambda contract: contract.delivery_month)

    return getattr(family, spec["fallback"], None)


def _normalize_kbar_timestamp(raw_ts) -> datetime:
    """將 Shioaji kbars ts 統一轉成台灣本地時間的 naive datetime。"""
    if isinstance(raw_ts, (int, float)):
        epoch_sec = raw_ts / 1e9 if raw_ts > 1e12 else raw_ts
        # Shioaji kbars.ts 可直接用 UTC epoch 轉回本地盤中時間。
        return datetime.fromtimestamp(epoch_sec, timezone.utc).replace(tzinfo=None)

    if hasattr(raw_ts, "to_pydatetime"):
        ts = raw_ts.to_pydatetime()
        if getattr(ts, "tzinfo", None) is not None:
            return ts.astimezone().replace(tzinfo=None)
        return ts

    return raw_ts


def main():
    parser = argparse.ArgumentParser(description="從 Shioaji 拉取歷史 K 棒")
    parser.add_argument("--days", type=int, default=60, help="拉取天數")
    parser.add_argument("--instrument", type=str, default="TMF", help="商品 (TMF/TGF)")
    args = parser.parse_args()

    print(f"拉取 {args.instrument} 歷史資料（{args.days} 天）")
    fetch_kbars(args.days, args.instrument)


if __name__ == "__main__":
    main()
