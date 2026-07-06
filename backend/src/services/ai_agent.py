"""AI agent powered by Google Gemini Flash.

Public API
----------
classify_message       – detect if text is a check-in, query, or other
parse_checkin          – free-text → per-schedule completion %s
generate_morning_msg   – personalised morning motivation
generate_evening_prompt – personalised evening check-in card body
generate_checkin_reply – personalised reply after logging
generate_query_reply   – answer a user question about tasks/streak
generate_weekly_summary – weekly insight message
"""

from __future__ import annotations

import json

from google import genai
import structlog

from config import settings

logger = structlog.get_logger(__name__)

_MODEL_NAME = "gemini-2.5-flash"
_client: genai.Client | None = None


def _get_client() -> genai.Client:
    global _client
    if _client is None:
        _client = genai.Client(api_key=settings.gemini_api_key)
    return _client


def _personality_desc(personality: str) -> str:
    return {
        "cheerleader": (
            "warm, enthusiastic, and encouraging. "
            "You celebrate every win loudly and use plenty of positive emojis."
        ),
        "drill_sergeant": (
            "tough, no-nonsense, military-style. "
            "Direct, intense, minimal sympathy — but you genuinely respect hard work."
        ),
        "analyst": (
            "calm, logical, and data-focused. "
            "You reference numbers and trends with minimal emotion."
        ),
    }.get(personality, "friendly and supportive")


def _extract_json(text: str) -> str:
    """Strip markdown code fences if Gemini wraps the response in them."""
    text = text.strip()
    if "```" in text:
        parts = text.split("```")
        # parts[1] is the fenced block; strip a leading 'json' language tag
        inner = parts[1]
        if inner.startswith("json"):
            inner = inner[4:]
        return inner.strip()
    return text


# ── Check-in parser ────────────────────────────────────────────────────────────

async def parse_checkin(
    user_text: str,
    schedules: list[dict],   # [{"id": str, "title": str}]
    user_name: str,
) -> list[dict]:             # [{"schedule_id": str, "schedule_title": str, "completion_pct": int}]
    """Parse a free-text check-in into per-schedule completion percentages."""
    schedule_list = "\n".join(
        f'- "{s["title"]}" (id: {s["id"]})' for s in schedules
    )
    prompt = f"""You are parsing a daily check-in for a productivity app called Pursuit.

User: {user_name}
Today's tasks:
{schedule_list}

User's message: "{user_text}"

Assign a completion percentage (0, 50, or 100) to EVERY task:
- 100 = fully done / completed / finished
- 50  = partially done / halfway / some progress
- 0   = skipped / missed / didn't do it

If a task isn't explicitly mentioned, infer from overall context
("did everything" → 100 all, "bad day skipped all" → 0 all, etc.).

Respond ONLY with a valid JSON array — no markdown, no explanation:
[{{"schedule_id": "...", "schedule_title": "...", "completion_pct": 100}}]"""

    client = _get_client()
    try:
        response = await client.aio.models.generate_content(model=_MODEL_NAME, contents=prompt)
        return json.loads(_extract_json(response.text))
    except Exception as exc:
        logger.error("ai_agent.parse_checkin_failed", error=str(exc))
        # Safe fallback: 50 % for all
        return [
            {"schedule_id": s["id"], "schedule_title": s["title"], "completion_pct": 50}
            for s in schedules
        ]


# ── Message generators ─────────────────────────────────────────────────────────

async def generate_morning_msg(
    user_name: str,
    streak: int,
    schedules: list[str],
    personality: str,
) -> str:
    """Generate a personalised morning motivation message."""
    streak_note = f"{streak}-day streak" if streak > 1 else ("1-day streak — fresh start!" if streak == 1 else "no active streak yet")
    prompt = f"""You are Pursuit, a WhatsApp accountability bot.
Personality: {_personality_desc(personality)}

User: {user_name}
Streak: {streak_note}
Today's tasks: {', '.join(schedules)}

Write a morning check-in message (2-4 sentences).
- Reference their streak and specific tasks naturally.
- End with the numbered task list.
No hashtags. No markdown bold/italic. Plain text + emojis only."""

    client = _get_client()
    try:
        response = await client.aio.models.generate_content(model=_MODEL_NAME, contents=prompt)
        return response.text.strip()
    except Exception as exc:
        logger.error("ai_agent.morning_msg_failed", error=str(exc))
        items = "\n".join(f"  {i + 1}. {t}" for i, t in enumerate(schedules))
        return (
            f"☀️ Good morning, {user_name}! Streak: {streak} days.\n\n"
            f"{items}\n\nYou've got this! 💪"
        )


async def generate_evening_prompt(
    user_name: str,
    streak: int,
    schedules: list[str],
    personality: str,
    cl_balance: float,
) -> str:
    """Generate the body text of the consolidated evening check-in card."""
    prompt = f"""You are Pursuit, a WhatsApp accountability bot.
Personality: {_personality_desc(personality)}

User: {user_name}
Current streak: {streak} days
Skip Days left: {cl_balance:.1f}
Today's tasks: {', '.join(schedules)}

Write the body of an evening check-in card (2-3 sentences).
- List the tasks
- Ask how it went
- Mention they can also reply in plain text for a more detailed response
No hashtags. No markdown. Plain text + emojis."""

    client = _get_client()
    try:
        response = await client.aio.models.generate_content(model=_MODEL_NAME, contents=prompt)
        return response.text.strip()
    except Exception as exc:
        logger.error("ai_agent.evening_prompt_failed", error=str(exc))
        items = "\n".join(f"  • {t}" for t in schedules)
        return (
            f"📅 Evening check-in, {user_name}!\n\n{items}\n\n"
            f"How did it go? Tap a button or reply in text 💬\n"
            f"Skip Days left: {cl_balance:.1f} 🛋️"
        )


async def generate_checkin_reply(
    user_name: str,
    streak: int,
    results: list[dict],     # [{"schedule_title": str, "completion_pct": int}]
    personality: str,
    cl_balance: float,
    streak_saved: bool = False,
    cl_earned: bool = False,
) -> str:
    """Generate a personalised reply after a check-in is logged."""
    done    = [r["schedule_title"] for r in results if r["completion_pct"] == 100]
    partial = [r["schedule_title"] for r in results if r["completion_pct"] == 50]
    missed  = [r["schedule_title"] for r in results if r["completion_pct"] == 0]

    extras: list[str] = []
    if streak_saved:
        extras.append("They used a Skip Day to protect their streak.")
    if cl_earned:
        extras.append(f"They just earned a Skip Day bonus! New balance: {cl_balance:.1f}.")

    prompt = f"""You are Pursuit, a WhatsApp accountability bot.
Personality: {_personality_desc(personality)}

User: {user_name}
Current streak: {streak} days
Completed (100%): {done or 'none'}
Partial (50%): {partial or 'none'}
Missed (0%): {missed or 'none'}
{chr(10).join(extras)}

Write a short reply (2-4 sentences). Be specific about what they did.
{"Acknowledge the Skip Day." if streak_saved else ""}
{"Celebrate the bonus Skip Day!" if cl_earned else ""}
No hashtags. No markdown. Plain text + emojis."""

    client = _get_client()
    try:
        response = await client.aio.models.generate_content(model=_MODEL_NAME, contents=prompt)
        return response.text.strip()
    except Exception as exc:
        logger.error("ai_agent.checkin_reply_failed", error=str(exc))
        return f"✅ Logged! Streak: {streak} days. Keep it up, {user_name}! 🔥"


async def generate_weekly_summary(
    user_name: str,
    streak: int,
    all_time_high: int,
    logs: list[dict],
    personality: str,
) -> str:
    """Generate a weekly insight summary message."""
    if not logs:
        return (
            f"📊 No activity logged this week, {user_name}. "
            "A fresh week starts now — let's make it count! 💪"
        )

    total = len(logs)
    avg = sum(l.get("completion_pct", 0) for l in logs) / total
    full   = sum(1 for l in logs if l.get("completion_pct", 0) == 100)
    partial = sum(1 for l in logs if l.get("completion_pct", 0) == 50)
    missed  = sum(1 for l in logs if l.get("completion_pct", 0) == 0)

    prompt = f"""You are Pursuit, a WhatsApp accountability bot.
Personality: {_personality_desc(personality)}

Weekly report for {user_name}:
- Current streak: {streak} days (all-time high: {all_time_high})
- Check-ins this week: {total}
- Average completion: {avg:.0f}%
- Full (100%): {full}  |  Partial (50%): {partial}  |  Missed (0%): {missed}

Write a weekly summary (4-6 sentences).
- Highlight the biggest win
- Call out one pattern to watch
- Give one concrete tip for next week
No hashtags. No markdown. Plain text + emojis."""

    client = _get_client()
    try:
        response = await client.aio.models.generate_content(model=_MODEL_NAME, contents=prompt)
        return response.text.strip()
    except Exception as exc:
        logger.error("ai_agent.weekly_summary_failed", error=str(exc))
        return (
            f"📊 Week recap for {user_name}: {full}/7 full days, {avg:.0f}% avg. "
            f"Streak: {streak} days. Keep building! 💪"
        )


# ── Intent classification ──────────────────────────────────────────────────────

async def classify_message(user_text: str) -> str:
    """Return 'checkin', 'query', or 'other'."""
    prompt = f"""You are classifying a WhatsApp message sent to a productivity tracking bot called Pursuit.

Message: "{user_text}"

Classify this message as exactly one of:
- checkin: user is reporting what they did/didn't do today (e.g. "done", "couldn't finish", "90% done", "skipped gym")
- query: user is asking a question (e.g. "what are my tasks", "what's my streak", "remind me my goals")
- other: greetings, unrelated messages, unclear content

Reply with ONLY one word: checkin, query, or other."""

    client = _get_client()
    try:
        response = await client.aio.models.generate_content(model=_MODEL_NAME, contents=prompt)
        label = response.text.strip().lower()
        if label in ("checkin", "query", "other"):
            return label
        # If Gemini returns a verbose answer, check if it contains a keyword
        for keyword in ("checkin", "query", "other"):
            if keyword in label:
                return keyword
        return "other"
    except Exception as exc:
        logger.error("ai_agent.classify_failed", error=str(exc))
        return "checkin"  # safe fallback


async def generate_query_reply(
    user_text: str,
    user_name: str,
    streak: int,
    schedules: list[str],
    personality: str,
) -> str:
    """Generate a helpful reply to a user's question about tasks/streak."""
    items = "\n".join(f"  {i + 1}. {t}" for i, t in enumerate(schedules))
    prompt = f"""You are Pursuit, a WhatsApp accountability bot.
Personality: {_personality_desc(personality)}

User: {user_name}
Current streak: {streak} days
Active tasks:
{items}

User's question: "{user_text}"

Answer helpfully in 2-3 sentences. If they ask about tasks, list them clearly.
No hashtags. No markdown. Plain text + emojis."""

    client = _get_client()
    try:
        response = await client.aio.models.generate_content(model=_MODEL_NAME, contents=prompt)
        return response.text.strip()
    except Exception as exc:
        logger.error("ai_agent.query_reply_failed", error=str(exc))
        return f"📋 {user_name}'s tasks:\n{items}\n\nStreak: {streak} days 🔥"
