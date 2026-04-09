"""
風險設定正規化與 orderbook 映射測試
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

import unittest

from risk.profile_config import (
    normalize_risk_profile,
    get_orderbook_profile_for_risk,
)


class TestRiskProfileConfig(unittest.TestCase):
    """測試風險等級別名與固定映射"""

    def test_normalize_accepts_dangerous_alias(self):
        self.assertEqual(normalize_risk_profile("dangerous"), "crisis")

    def test_normalize_is_case_insensitive(self):
        self.assertEqual(normalize_risk_profile("  AGGRESSIVE "), "aggressive")

    def test_normalize_rejects_invalid_value(self):
        with self.assertRaises(ValueError):
            normalize_risk_profile("all-in")

    def test_orderbook_profile_mapping(self):
        self.assertEqual(get_orderbook_profile_for_risk("conservative"), "A1")
        self.assertEqual(get_orderbook_profile_for_risk("balanced"), "A3")
        self.assertEqual(get_orderbook_profile_for_risk("aggressive"), "A4")
        self.assertEqual(get_orderbook_profile_for_risk("dangerous"), "A5")


if __name__ == "__main__":
    unittest.main()
