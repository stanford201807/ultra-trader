"""
Orderbook 參數組合與風險等級固定映射
"""

from __future__ import annotations


ORDERBOOK_PROFILES = {
    "A1": {
        "spread_threshold_normal": 1.0,
        "spread_threshold_open": 2.0,
        "spread_threshold_crisis": 4.0,
        "pressure_min_score": 1,
    },
    "A2": {
        "spread_threshold_normal": 2.0,
        "spread_threshold_open": 4.0,
        "spread_threshold_crisis": 6.0,
        "pressure_min_score": 1,
    },
    "A3": {
        "spread_threshold_normal": 2.0,
        "spread_threshold_open": 4.0,
        "spread_threshold_crisis": 6.0,
        "pressure_min_score": 2,
    },
    "A4": {
        "spread_threshold_normal": 3.0,
        "spread_threshold_open": 4.0,
        "spread_threshold_crisis": 6.0,
        "pressure_min_score": 2,
    },
    "A5": {
        "spread_threshold_normal": 3.0,
        "spread_threshold_open": 6.0,
        "spread_threshold_crisis": 8.0,
        "pressure_min_score": 3,
    },
}

