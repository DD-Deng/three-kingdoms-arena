"""Managed AI personality tests — Step 5: 托管AI调整."""

import pytest
from app.engine import MANAGED_DEFAULTS, PERSONALITY_MODIFIERS


# ═══════════════════════════════════════════════════════════════
# Test 1: Personality assigned to each faction
# ═══════════════════════════════════════════════════════════════

def test_managed_personality_assigned():
    """Each faction has a personality field in MANAGED_DEFAULTS."""
    assert MANAGED_DEFAULTS["魏"]["personality"] == "aggressive"
    assert MANAGED_DEFAULTS["蜀"]["personality"] == "conservative"
    assert MANAGED_DEFAULTS["吴"]["personality"] == "balanced"


# ═══════════════════════════════════════════════════════════════
# Test 2: Personality modifiers are valid
# ═══════════════════════════════════════════════════════════════

def test_personality_modifiers_exist():
    """All three personalities have modifier entries."""
    for p in ("aggressive", "balanced", "conservative"):
        assert p in PERSONALITY_MODIFIERS, f"{p} missing from PERSONALITY_MODIFIERS"
        mods = PERSONALITY_MODIFIERS[p]
        for key in ("aggression", "recruit", "attack_ratio"):
            assert key in mods, f"{key} missing from {p} modifiers"


# ═══════════════════════════════════════════════════════════════
# Test 3: Aggressive AI has higher aggression, lower attack threshold
# ═══════════════════════════════════════════════════════════════

def test_aggressive_modifiers():
    """Aggressive: high aggression, low attack threshold."""
    mods = PERSONALITY_MODIFIERS["aggressive"]
    balanced = PERSONALITY_MODIFIERS["balanced"]
    assert mods["aggression"] > balanced["aggression"]
    assert mods["attack_ratio"] < balanced["attack_ratio"]
    assert mods["recruit"] >= balanced["recruit"]


# ═══════════════════════════════════════════════════════════════
# Test 4: Conservative AI has lower aggression, higher attack threshold
# ═══════════════════════════════════════════════════════════════

def test_conservative_modifiers():
    """Conservative: low aggression, high attack threshold, lower recruit."""
    mods = PERSONALITY_MODIFIERS["conservative"]
    balanced = PERSONALITY_MODIFIERS["balanced"]
    assert mods["aggression"] < balanced["aggression"]
    assert mods["attack_ratio"] > balanced["attack_ratio"]
    assert mods["recruit"] < balanced["recruit"]


# ═══════════════════════════════════════════════════════════════
# Test 5: Aggressive attack threshold is 1.5:1
# ═══════════════════════════════════════════════════════════════

def test_aggressive_attack_ratio():
    """Aggressive AI attacks at 1.5:1 advantage."""
    assert PERSONALITY_MODIFIERS["aggressive"]["attack_ratio"] == 1.5


# ═══════════════════════════════════════════════════════════════
# Test 6: Conservative attack threshold is 3:1
# ═══════════════════════════════════════════════════════════════

def test_conservative_attack_ratio():
    """Conservative AI attacks at 3:1 advantage."""
    assert PERSONALITY_MODIFIERS["conservative"]["attack_ratio"] == 3.0


# ═══════════════════════════════════════════════════════════════
# Test 7: MANAGED_AI_RECRUIT_RATIO default is 0.3
# ═══════════════════════════════════════════════════════════════

def test_recruit_ratio_default():
    """Default recruit ratio is 0.3 (was 0.5)."""
    from app.config import MANAGED_AI_RECRUIT_RATIO
    assert MANAGED_AI_RECRUIT_RATIO == 0.3, \
        f"Expected 0.3, got {MANAGED_AI_RECRUIT_RATIO}"


# ═══════════════════════════════════════════════════════════════
# Test 8: Effective recruit ratio for each personality
# ═══════════════════════════════════════════════════════════════

def test_effective_recruit_ratios():
    """Effective recruit ratio = base * personality modifier."""
    base = 0.3  # MANAGED_AI_RECRUIT_RATIO default
    agg = base * PERSONALITY_MODIFIERS["aggressive"]["recruit"]
    bal = base * PERSONALITY_MODIFIERS["balanced"]["recruit"]
    con = base * PERSONALITY_MODIFIERS["conservative"]["recruit"]
    assert agg == pytest.approx(0.33)
    assert bal == 0.3
    assert con == pytest.approx(0.24)


# ═══════════════════════════════════════════════════════════════
# Test 9: Effective aggression for each personality
# ═══════════════════════════════════════════════════════════════

def test_effective_aggression():
    """Effective aggression = base * personality modifier."""
    base = 0.3  # MANAGED_AI_AGGRESSION default
    agg = base * PERSONALITY_MODIFIERS["aggressive"]["aggression"]
    bal = base * PERSONALITY_MODIFIERS["balanced"]["aggression"]
    con = base * PERSONALITY_MODIFIERS["conservative"]["aggression"]
    assert agg == pytest.approx(0.48)
    assert bal == 0.3
    assert con == pytest.approx(0.15)
