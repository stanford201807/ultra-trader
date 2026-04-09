"""
風險等級正規化與固定策略映射
"""

from __future__ import annotations


VALID_RISK_PROFILES = ("conservative", "balanced", "aggressive", "crisis")
RISK_PROFILE_ALIASES = {
    "dangerous": "crisis",
}

RISK_TO_ORDERBOOK_PROFILE = {
    "conservative": "A1",
    "balanced": "A3",
    "aggressive": "A4",
    "crisis": "A5",
}


def normalize_risk_profile(profile: str) -> str:
    """將輸入風險等級正規化為 canonical 值，非法值拋出 ValueError。"""
    if not isinstance(profile, str):
        raise ValueError("風險等級必須是字串")

    normalized = profile.strip().lower()
    if not normalized:
        raise ValueError("風險等級不可為空")

    canonical = RISK_PROFILE_ALIASES.get(normalized, normalized)
    if canonical not in VALID_RISK_PROFILES:
        allowed = ", ".join([*VALID_RISK_PROFILES, *RISK_PROFILE_ALIASES.keys()])
        raise ValueError(f"無效風險等級: {profile}，允許值: {allowed}")
    return canonical


def get_orderbook_profile_for_risk(profile: str) -> str:
    """依風險等級回傳固定 orderbook profile 名稱（A1~A5）。"""
    canonical = normalize_risk_profile(profile)
    return RISK_TO_ORDERBOOK_PROFILE[canonical]

