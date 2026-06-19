"""Unit tests for the gamification engine (pure logic, no HTTP)."""

from __future__ import annotations

import pytest

from services.gamification import (
    CL_BONUS_AMOUNT,
    COMPLETION_THRESHOLD,
    STREAK_BONUS_INTERVAL,
)
from services.bot_personality import get_response_message
from services.gamification import GameResult


# ── GameResult helper ─────────────────────────────────────────────────────────

def make_result(**kwargs) -> GameResult:  # type: ignore[return]
    defaults = dict(
        current_streak=1,
        all_time_high=1,
        cl_balance=3.0,
        streak_saved_by_cl=False,
        cl_earned=False,
        unlocked_rewards=[],
    )
    defaults.update(kwargs)
    return GameResult(**defaults)


# ── Bot personality tests ─────────────────────────────────────────────────────

def test_cheerleader_response_high_completion():
    result = make_result(current_streak=5)
    msg = get_response_message("cheerleader", 100, result)
    assert "AMAZING" in msg or "streak" in msg.lower()


def test_drill_sergeant_response_below_threshold():
    result = make_result(current_streak=0)
    msg = get_response_message("drill_sergeant", 50, result)
    assert "reset" in msg.lower() or "zero" in msg.lower() or "50" in msg


def test_analyst_response_casual_leave():
    result = make_result(streak_saved_by_cl=True, current_streak=3, cl_balance=2.0)
    msg = get_response_message("analyst", 0, result)
    assert "frozen" in msg.lower() or "casual leave" in msg.lower()


def test_cl_earned_message_included():
    result = make_result(current_streak=7, cl_earned=True, cl_balance=4.0)
    msg = get_response_message("cheerleader", 100, result)
    assert "+1.0 CL" in msg or "earned" in msg.lower()


# ── Threshold constants ───────────────────────────────────────────────────────

def test_completion_threshold_is_80():
    assert COMPLETION_THRESHOLD == 80


def test_streak_bonus_interval_is_7():
    assert STREAK_BONUS_INTERVAL == 7


def test_cl_bonus_amount():
    assert CL_BONUS_AMOUNT == 1.0
