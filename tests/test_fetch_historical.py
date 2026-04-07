"""
歷史資料抓取腳本測試
"""

import sys
from pathlib import Path
from types import SimpleNamespace
from datetime import datetime

sys.path.insert(0, str(Path(__file__).parent.parent))

import unittest

from scripts.fetch_historical import _resolve_contract, _normalize_kbar_timestamp


class FakeFamily(list):
    """模擬 Shioaji 的合約族群容器。"""

    def __init__(self, contracts, **named_contracts):
        super().__init__(contracts)
        for key, value in named_contracts.items():
            setattr(self, key, value)


class TestResolveContract(unittest.TestCase):
    """驗證商品代碼到合約族群的映射。"""

    def test_tmf_uses_tmf_family_instead_of_mxf(self):
        tmf_near = SimpleNamespace(code="TMFR1", name="微型臺指近月", delivery_month="202604")
        tmf_far = SimpleNamespace(code="TMFQ6", name="微型臺指遠月", delivery_month="202606")
        mxf_near = SimpleNamespace(code="MXFR1", name="小型臺指近月", delivery_month="202604")

        contracts = SimpleNamespace(
            Futures=SimpleNamespace(
                TMF=FakeFamily([tmf_far, tmf_near], TMFR1=tmf_near),
                MXF=FakeFamily([mxf_near], MXFR1=mxf_near),
            )
        )

        resolved = _resolve_contract(contracts, "TMF")

        self.assertIs(resolved, tmf_near)
        self.assertEqual(resolved.code, "TMFR1")

    def test_tgf_uses_tgf_family(self):
        tgf_near = SimpleNamespace(code="TGFR1", name="黃金期近月", delivery_month="202604")
        tgf_far = SimpleNamespace(code="TGFQ6", name="黃金期遠月", delivery_month="202606")
        contracts = SimpleNamespace(
            Futures=SimpleNamespace(
                TGF=FakeFamily([tgf_far, tgf_near], TGFR1=tgf_near),
            )
        )

        resolved = _resolve_contract(contracts, "TGF")

        self.assertIs(resolved, tgf_near)

    def test_fallback_named_contract_when_list_is_empty(self):
        tmf_near = SimpleNamespace(code="TMFR1", name="微型臺指近月", delivery_month="202604")
        contracts = SimpleNamespace(
            Futures=SimpleNamespace(
                TMF=FakeFamily([], TMFR1=tmf_near),
            )
        )

        resolved = _resolve_contract(contracts, "TMF")

        self.assertIs(resolved, tmf_near)

    def test_unknown_instrument_returns_none(self):
        contracts = SimpleNamespace(Futures=SimpleNamespace())

        resolved = _resolve_contract(contracts, "UNKNOWN")

        self.assertIsNone(resolved)


class TestNormalizeKbarTimestamp(unittest.TestCase):
    """驗證 Shioaji K 棒時間戳轉換。"""

    def test_nanosecond_epoch_uses_utc_conversion(self):
        raw_ts = 1775551560000000000

        normalized = _normalize_kbar_timestamp(raw_ts)

        self.assertEqual(normalized, datetime(2026, 4, 7, 8, 46))

    def test_second_epoch_uses_utc_conversion(self):
        raw_ts = 1775551560

        normalized = _normalize_kbar_timestamp(raw_ts)

        self.assertEqual(normalized, datetime(2026, 4, 7, 8, 46))


if __name__ == "__main__":
    unittest.main()
