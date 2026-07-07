"""Bot personality message templates.

Three personalities: CHEERLEADER, DRILL_SERGEANT, ANALYST.
All public functions are pure (no I/O) so they are trivially unit-testable.
"""

from __future__ import annotations

from services.gamification import GameResult

# Map the raw personality string stored in the DB to the message builders below.
_VALID = {"cheerleader", "drill_sergeant", "analyst"}


def get_checkin_message(personality: str, schedule_title: str, cl_balance: float) -> str:
    """Return the opening check-in body text for the WhatsApp interactive card."""
    p = personality.lower()
    if p == "cheerleader":
        return (
            f"Hey superstar! 🌟 Time for your daily check-in on *{schedule_title}*!\n"
            f"Remember, every tiny step counts. You've got this! 💪\n\n"
            f"Skip Days remaining: *{cl_balance:.1f}* 🛋️"
        )
    if p == "drill_sergeant":
        return (
            f"ATTENTION! \ud83e\ude96 Daily check-in for *{schedule_title}*.\n"
            f"No excuses. No delays. LOG. YOUR. PROGRESS. NOW.\n\n"
            f"Skip Days remaining: *{cl_balance:.1f}* \ud83d\udecb\ufe0f"
        )
    # Default: analyst
    return (
        f"Good evening. Daily check-in for schedule: *{schedule_title}*.\n"
        f"Please log your completion percentage below.\n\n"
        f"Skip Days remaining: *{cl_balance:.1f}* \ud83d\udecb\ufe0f"
    )


def get_response_message(personality: str, completion_pct: int, result: GameResult) -> str:
    """Return a reply message after a check-in button tap is processed."""
    p = personality.lower()

    if result.streak_saved_by_cl:
        if p == "cheerleader":
            return (
                "Taking a well-deserved break! 🛋️ Your streak is SAFE and sound. "
                f"Skip Day balance: *{result.cl_balance:.1f}*. Rest up, you're back tomorrow! 💛"
            )
        if p == "drill_sergeant":
            return (
                f"🛋️ Skip Day used. Streak frozen at *{result.current_streak}*. "
                "Don't make this a habit. Back in full force tomorrow. 🪖"
            )
        return (
            f"Skip Day applied. Streak frozen at *{result.current_streak}*. "
            f"Remaining balance: *{result.cl_balance:.1f}*."
        )

    if completion_pct >= 80:
        cl_msg = " 🎉 You earned *+1.0 CL* for completing a 7-day streak!" if result.cl_earned else ""
        reward_msg = (
            ("\n\n🏆 Reward unlocked: *" + result.unlocked_rewards[0]["title"] + "*!")
            if result.unlocked_rewards
            else ""
        )
        if p == "cheerleader":
            return (
                f"AMAZING WORK! 🎉🥳 You did *{completion_pct}%* today!\n"
                f"Streak: *{result.current_streak} days* 🔥{cl_msg}{reward_msg}"
            )
        if p == "drill_sergeant":
            return (
                f"GOOD. *{completion_pct}%* — acceptable. Streak: *{result.current_streak}*.{cl_msg}"
                f" Don't get comfortable.{reward_msg}"
            )
        return (
            f"Logged: *{completion_pct}%* completion. "
            f"Current streak: *{result.current_streak} days*.{cl_msg}{reward_msg}"
        )

    # Below threshold, no CL
    if p == "cheerleader":
        return (
            f"Hey, *{completion_pct}%* is still progress! 🌱 Don't be hard on yourself. "
            f"Streak reset to 0 — but tomorrow is a fresh start! You've got this! 💪"
        )
    if p == "drill_sergeant":
        return (
            f"*{completion_pct}%*?! THE NOTEBOOK GRAVEYARD IS LAUGHING AT YOU. "
            "Streak reset to ZERO. No excuses tomorrow. 🪖🎖️"
        )
    return (
        f"Logged: *{completion_pct}%*. Below the 80% threshold. "
        f"Streak has been reset to 0. Aim for ≥ 80% tomorrow."
    )
