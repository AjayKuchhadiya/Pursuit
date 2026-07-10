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
conversational_reply   – full conversational agent with tool-calling
"""

from __future__ import annotations

import json
from collections import defaultdict
from datetime import date, timedelta

from google import genai
from google.genai import types
from supabase._async.client import AsyncClient
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
- End with the numbered task list formatted as:
  1. Task name
  2. Task name
Use WhatsApp formatting: *bold* for key words, _italic_ sparingly. Use line breaks generously between sections.
No hashtags. No # headers. No double asterisks (**). Emojis welcome."""

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
- List each task as a bullet: • Task name
- Ask how it went
- Mention they can also reply in plain text for a more detailed response
Use WhatsApp formatting: *bold* for task names or key phrases. Use line breaks between sections.
No hashtags. No # headers. No double asterisks (**). Emojis welcome."""

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
- If there are completed/partial/missed tasks, list them with bullets (✅ done, 🔄 partial, ❌ missed).
{"Acknowledge the Skip Day." if streak_saved else ""}
{"Celebrate the bonus Skip Day!" if cl_earned else ""}
Use WhatsApp formatting: *bold* for the streak count and task names. Use line breaks between sections.
No hashtags. No # headers. No double asterisks (**). Emojis welcome."""

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

Write a weekly summary structured as:
- 1 opening sentence with overall vibe
- *This week's wins:* followed by bullet points (• ...)
- *Watch out for:* one pattern to improve
- *Tip for next week:* one concrete actionable tip

Use WhatsApp formatting: *bold* for section labels and key numbers, • for bullets. Use line breaks between each section.
No hashtags. No # headers. No double asterisks (**). Emojis welcome."""

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

Answer helpfully in 2-3 sentences. If they ask about tasks, list them as:
  1. *Task name*
  2. *Task name*
If they ask about streak or stats, *bold* the numbers.
Use WhatsApp formatting: *bold* for emphasis, • for bullet lists. Use line breaks between sections.
No hashtags. No # headers. No double asterisks (**). Emojis welcome."""

    client = _get_client()
    try:
        response = await client.aio.models.generate_content(model=_MODEL_NAME, contents=prompt)
        return response.text.strip()
    except Exception as exc:
        logger.error("ai_agent.query_reply_failed", error=str(exc))
        return f"📋 {user_name}'s tasks:\n{items}\n\nStreak: {streak} days 🔥"


# ═══════════════════════════════════════════════════════════════════════════════
# Conversational Agent with Tool-Calling
# ═══════════════════════════════════════════════════════════════════════════════

# ── Tool declarations ──────────────────────────────────────────────────────────

_AGENT_TOOLS = types.Tool(
    function_declarations=[
        types.FunctionDeclaration(
            name="log_daily_checkin",
            description=(
                "Log today's task completion for one or more active goals. "
                "Call this whenever the user reports how much they completed — "
                "e.g. 'done', 'finished everything', 'half done', 'only did DSA', etc. "
                "Use the schedule_ids provided in the system context."
            ),
            parameters={
                "type": "object",
                "properties": {
                    "completions": {
                        "type": "array",
                        "description": "One entry per active goal",
                        "items": {
                            "type": "object",
                            "properties": {
                                "schedule_id": {
                                    "type": "string",
                                    "description": "The goal's UUID from the system context",
                                },
                                "completion_pct": {
                                    "type": "integer",
                                    "description": "0 = missed, 50 = partial / halfway, 100 = fully done",
                                },
                            },
                            "required": ["schedule_id", "completion_pct"],
                        },
                    },
                },
                "required": ["completions"],
            },
        ),
        types.FunctionDeclaration(
            name="apply_skip_day",
            description=(
                "Use one Skip Day token to protect today's streak. "
                "Call when the user says they are skipping today, taking a day off, "
                "or using their casual leave."
            ),
        ),
        types.FunctionDeclaration(
            name="get_my_status",
            description=(
                "Retrieve the user's live streak, Skip Day balance, and today's logged activity. "
                "Call when the user asks about their progress, streak, or whether they already checked in."
            ),
        ),
    ]
)


# ── Context builder ────────────────────────────────────────────────────────────

async def _build_agent_context(
    db: AsyncClient,
    user_id: str,
    user: dict,
    schedules: list[dict],
) -> str:
    """Build a rich system prompt with fresh user data for every request."""
    today = date.today()

    # Streak & Skip Day balance
    streak_res = (
        await db.table("streaks")
        .select("current_streak, all_time_high")
        .eq("user_id", user_id)
        .limit(1)
        .execute()
    )
    streak_row = (streak_res.data or [{}])[0] or {}
    current_streak = int(streak_row.get("current_streak", 0))
    all_time_high = int(streak_row.get("all_time_high", 0))

    bal_res = (
        await db.table("leave_balance")
        .select("balance")
        .eq("user_id", user_id)
        .limit(1)
        .execute()
    )
    cl_balance = float(((bal_res.data or [{}])[0] or {}).get("balance", 0))

    # Last 7 days activity (compact summary)
    week_ago = (today - timedelta(days=6)).isoformat()
    logs_res = (
        await db.table("daily_logs")
        .select("log_date, completion_pct, is_casual_leave")
        .eq("user_id", user_id)
        .gte("log_date", week_ago)
        .order("log_date", desc=True)
        .execute()
    )
    by_date: dict = defaultdict(list)
    for log in logs_res.data or []:
        by_date[log["log_date"]].append(log)

    activity_lines = []
    for d in sorted(by_date.keys(), reverse=True):
        day_logs = by_date[d]
        if any(l["is_casual_leave"] for l in day_logs):
            activity_lines.append(f"  {d}: Skip Day 🛋️")
        else:
            min_pct = min(l["completion_pct"] for l in day_logs)
            icon = "✅" if min_pct >= 80 else ("🔄" if min_pct > 0 else "❌")
            activity_lines.append(f"  {d}: {icon} {min_pct}%")
    activity_str = "\n".join(activity_lines) if activity_lines else "  No activity yet this week."

    # Pending rewards (top 3 — motivational context)
    rewards_res = (
        await db.table("rewards")
        .select("title, condition_type, condition_value")
        .eq("user_id", user_id)
        .eq("is_unlocked", False)
        .limit(3)
        .execute()
    )
    pending = rewards_res.data or []
    rewards_block = ""
    if pending:
        r_lines = "\n".join(
            f'  🎯 "{r["title"]}": reach {int(r["condition_value"])} '
            f'{r["condition_type"].replace("_", " ")}'
            for r in pending
        )
        rewards_block = f"\n## What {user.get('name', 'you')} Is Working Towards\n{r_lines}"

    # Active goals with IDs (agent needs these for log_daily_checkin)
    goals_str = "\n".join(
        f'  - "{s["title"]}" (schedule_id: {s["id"]})' for s in schedules
    ) or "  (no active goals yet)"

    personality = _personality_desc(user.get("personality", "analyst"))
    name = user.get("name", "there")
    today_str = today.strftime("%A, %B %d, %Y")

    return f"""You are Pursuit, a WhatsApp accountability coach having a real conversation with {name}.

Today: {today_str}

## {name}'s Stats
- Current streak: *{current_streak} days* (all-time high: {all_time_high} days)
- Skip Days available: {cl_balance:.1f}

## Active Goals
{goals_str}

## Last 7 Days
{activity_str}
{rewards_block}

## Behaviour Guidelines
Personality style: {personality}

- Have natural conversations. You are a coach AND a friend.
- When {name} reports completing tasks in ANY phrasing, call log_daily_checkin.
  Examples: "done", "finished everything", "half done", "only did DSA", "partial 🔥", "completed both"
- When they want to skip today, call apply_skip_day.
- When they ask about streak/progress/status, call get_my_status for live data.
- A day counts toward the streak only if EVERY active goal is ≥80%. Partial (50%) resets the streak.
- After a successful log, always tell {name} their new streak and give honest, encouraging feedback.
- Keep replies concise and WhatsApp-friendly.
- Use *bold* for key numbers/names. Emojis welcome. No # headers. No hashtags."""


# ── Tool executor ──────────────────────────────────────────────────────────────

async def _execute_tool(
    db: AsyncClient,
    user_id: str,
    schedules: list[dict],
    function_call: object,
) -> dict:
    """Run the requested tool and return a result dict for the model."""
    from services import gamification  # local import avoids circular dependency

    name: str = function_call.name  # type: ignore[attr-defined]
    args: dict = dict(function_call.args or {})  # type: ignore[attr-defined]

    # ── log_daily_checkin ──────────────────────────────────────────────────────
    if name == "log_daily_checkin":
        completions: list[dict] = args.get("completions", [])
        results = []
        last_game = None
        for c in completions:
            try:
                game = await gamification.process_log(
                    db=db,
                    user_id=user_id,
                    schedule_id=c["schedule_id"],
                    log_date=date.today(),
                    completion_pct=int(c["completion_pct"]),
                    is_casual_leave=False,
                )
                last_game = game
                results.append({"schedule_id": c["schedule_id"], "completion_pct": c["completion_pct"], "logged": True})
            except Exception as exc:
                logger.error("ai_agent.tool.log_failed", schedule_id=c.get("schedule_id"), error=str(exc))
                results.append({"schedule_id": c.get("schedule_id"), "logged": False, "error": str(exc)})

        out: dict = {"date": date.today().isoformat(), "results": results}
        if last_game:
            out.update({
                "new_streak": last_game.current_streak,
                "all_time_high": last_game.all_time_high,
                "skip_day_balance": last_game.cl_balance,
                "streak_saved_by_skip_day": last_game.streak_saved_by_cl,
                "skip_day_bonus_earned": last_game.cl_earned,
            })
        return out

    # ── apply_skip_day ─────────────────────────────────────────────────────────
    elif name == "apply_skip_day":
        bal_res = await db.table("leave_balance").select("balance").eq("user_id", user_id).limit(1).execute()
        balance = float(((bal_res.data or [{}])[0] or {}).get("balance", 0))
        if balance < 1.0:
            return {"success": False, "reason": "No Skip Days remaining", "balance": 0}

        covered: list[str] = []
        for sched in schedules:
            try:
                await gamification.process_log(
                    db=db, user_id=user_id, schedule_id=sched["id"],
                    log_date=date.today(), completion_pct=0, is_casual_leave=True,
                )
                covered.append(sched["title"])
            except Exception as exc:
                logger.error("ai_agent.tool.cl_failed", schedule_id=sched["id"], error=str(exc))

        return {
            "success": bool(covered),
            "covered_goals": covered,
            "remaining_balance": balance - 1.0,
        }

    # ── get_my_status ──────────────────────────────────────────────────────────
    elif name == "get_my_status":
        streak_res = (
            await db.table("streaks")
            .select("current_streak, all_time_high")
            .eq("user_id", user_id)
            .limit(1)
            .execute()
        )
        streak_row = (streak_res.data or [{}])[0] or {}
        bal_res = await db.table("leave_balance").select("balance").eq("user_id", user_id).limit(1).execute()
        balance = float(((bal_res.data or [{}])[0] or {}).get("balance", 0))

        today_logs_res = (
            await db.table("daily_logs")
            .select("schedule_id, completion_pct, is_casual_leave")
            .eq("user_id", user_id)
            .eq("log_date", date.today().isoformat())
            .execute()
        )
        sched_map = {s["id"]: s["title"] for s in schedules}
        today_logs = [
            {
                "goal": sched_map.get(l["schedule_id"], l["schedule_id"]),
                "completion_pct": l["completion_pct"],
                "is_skip_day": l["is_casual_leave"],
            }
            for l in (today_logs_res.data or [])
        ]

        return {
            "current_streak": streak_row.get("current_streak", 0),
            "all_time_high": streak_row.get("all_time_high", 0),
            "skip_days_balance": balance,
            "today_logs": today_logs,
            "checked_in_today": len(today_logs) > 0,
        }

    else:
        logger.warning("ai_agent.tool.unknown", name=name)
        return {"error": f"Unknown tool: {name}"}


# ── Main entry point ───────────────────────────────────────────────────────────

async def conversational_reply(
    db: AsyncClient,
    user_id: str,
    user: dict,
    text: str,
    schedules: list[dict],
) -> str:
    """Full conversational agent with tool-calling and persistent memory.

    Builds a rich system context, retrieves recent conversation history,
    and runs a Gemini agent loop that can call tools (log check-ins, apply
    skip days, query status) before generating the final WhatsApp reply.
    """
    from services import conversation as conv_svc

    system_ctx = await _build_agent_context(db, user_id, user, schedules)
    history = await conv_svc.get_history(db, user_id)
    history.append({"role": "user", "parts": [{"text": text}]})

    client = _get_client()
    config = types.GenerateContentConfig(
        system_instruction=system_ctx,
        tools=[_AGENT_TOOLS],
    )

    final_text: str | None = None

    # Agent loop: up to 3 tool-call rounds before a final text response
    for _ in range(4):
        try:
            response = await client.aio.models.generate_content(
                model=_MODEL_NAME,
                contents=history,
                config=config,
            )
        except Exception as exc:
            logger.error("ai_agent.conversational_generate_failed", error=str(exc))
            break

        candidate = response.candidates[0]
        parts = candidate.content.parts or []

        # Separate text parts from function-call parts
        func_calls = [p for p in parts if getattr(p, "function_call", None)]
        text_parts = [p for p in parts if getattr(p, "text", None)]

        if func_calls:
            # Add model's function-call response to history (as dict for consistency)
            model_parts_dict = []
            for p in parts:
                if getattr(p, "function_call", None):
                    model_parts_dict.append({
                        "function_call": {
                            "name": p.function_call.name,
                            "args": dict(p.function_call.args or {}),
                        }
                    })
                elif getattr(p, "text", None):
                    model_parts_dict.append({"text": p.text})
            history.append({"role": "model", "parts": model_parts_dict})

            # Execute each tool and collect results
            tool_parts = []
            for fc_part in func_calls:
                result = await _execute_tool(db, user_id, schedules, fc_part.function_call)
                tool_parts.append({
                    "function_response": {
                        "name": fc_part.function_call.name,
                        "response": result,
                    }
                })
            history.append({"role": "tool", "parts": tool_parts})

        else:
            # No tool calls — this is the final text response
            final_text = "".join(p.text for p in text_parts).strip()
            break

    if not final_text:
        name = user.get("name", "there")
        final_text = f"Hey {name}! 👋 Got your message. Something went wrong on my end — please try again in a moment."

    # Persist both sides of the turn (fire-and-forget errors are OK)
    try:
        from services import conversation as conv_svc
        await conv_svc.save_turn(db, user_id, text, final_text)
    except Exception as exc:
        logger.warning("ai_agent.save_turn_failed", error=str(exc))

    return final_text

