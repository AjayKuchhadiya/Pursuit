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

import contextvars
import json
from collections import defaultdict
from datetime import date, timedelta

from google import genai
from google.genai import types
from google.adk.agents import LlmAgent
from google.adk.agents.callback_context import CallbackContext
from google.adk.events import Event
from google.adk.models.llm_request import LlmRequest
from google.adk.runners import Runner
from google.adk.sessions import InMemorySessionService
from google.adk.tools import FunctionTool
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
# Conversational Agent (Google ADK)
# ═══════════════════════════════════════════════════════════════════════════════

# ── Per-request context vars (safe for concurrent async tasks) ─────────────────

_db_ctx: contextvars.ContextVar = contextvars.ContextVar("db")
_user_id_ctx: contextvars.ContextVar = contextvars.ContextVar("user_id")
_schedules_ctx: contextvars.ContextVar = contextvars.ContextVar("schedules")
_instruction_ctx: contextvars.ContextVar = contextvars.ContextVar("instruction")


# ── ADK tool functions ─────────────────────────────────────────────────────────

async def _tool_log_daily_checkin(completions: list[dict]) -> dict:
    """Log today's task completion for one or more active goals.

    Call whenever the user reports how much they completed — e.g. 'done',
    'finished everything', 'half done', 'only did DSA'.
    Each entry in completions needs:
        - schedule_id (str): the goal UUID from the system context
        - completion_pct (int): 0 = missed, 50 = partial, 100 = fully done

    Returns logged results and the updated streak info.
    """
    from services import gamification  # local import avoids circular dependency

    db = _db_ctx.get()
    user_id = _user_id_ctx.get()

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
            results.append({
                "schedule_id": c["schedule_id"],
                "completion_pct": c["completion_pct"],
                "logged": True,
            })
        except Exception as exc:
            logger.error("adk.tool.log_failed", schedule_id=c.get("schedule_id"), error=str(exc))
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


async def _tool_apply_skip_day() -> dict:
    """Use one Skip Day token to protect today's streak.

    Call when the user says they are skipping today, taking a day off,
    or using their casual leave.
    """
    from services import gamification

    db = _db_ctx.get()
    user_id = _user_id_ctx.get()
    schedules = _schedules_ctx.get()

    bal_res = (
        await db.table("leave_balance")
        .select("balance")
        .eq("user_id", user_id)
        .limit(1)
        .execute()
    )
    balance = float(((bal_res.data or [{}])[0] or {}).get("balance", 0))
    if balance < 1.0:
        return {"success": False, "reason": "No Skip Days remaining", "balance": 0}

    covered: list[str] = []
    for sched in schedules:
        try:
            await gamification.process_log(
                db=db,
                user_id=user_id,
                schedule_id=sched["id"],
                log_date=date.today(),
                completion_pct=0,
                is_casual_leave=True,
            )
            covered.append(sched["title"])
        except Exception as exc:
            logger.error("adk.tool.cl_failed", schedule_id=sched["id"], error=str(exc))

    return {
        "success": bool(covered),
        "covered_goals": covered,
        "remaining_balance": balance - 1.0,
    }


async def _tool_get_my_status() -> dict:
    """Retrieve the user's live streak, Skip Day balance, and today's logged activity.

    Call when the user asks about their progress, streak, or whether they
    already checked in.
    """
    db = _db_ctx.get()
    user_id = _user_id_ctx.get()
    schedules = _schedules_ctx.get()

    streak_res = (
        await db.table("streaks")
        .select("current_streak, all_time_high")
        .eq("user_id", user_id)
        .limit(1)
        .execute()
    )
    streak_row = (streak_res.data or [{}])[0] or {}

    bal_res = (
        await db.table("leave_balance")
        .select("balance")
        .eq("user_id", user_id)
        .limit(1)
        .execute()
    )
    balance = float(((bal_res.data or [{}])[0] or {}).get("balance", 0))

    today_res = (
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
        for l in (today_res.data or [])
    ]

    return {
        "current_streak": streak_row.get("current_streak", 0),
        "all_time_high": streak_row.get("all_time_high", 0),
        "skip_days_balance": balance,
        "today_logs": today_logs,
        "checked_in_today": len(today_logs) > 0,
    }


# ── Dynamic system instruction callback ───────────────────────────────────────

def _inject_instruction(cb_ctx: CallbackContext, llm_request: LlmRequest) -> None:
    """Inject per-request system instruction (user context, streak, goals)."""
    instruction = _instruction_ctx.get(None)
    if instruction and llm_request.config is not None:
        llm_request.config.system_instruction = instruction


# ── Module-level ADK singletons (lazy init) ────────────────────────────────────

_AGENT: LlmAgent | None = None
_RUNNER: Runner | None = None
_SESSION_SVC: InMemorySessionService | None = None
_LOADED_SESSIONS: set[str] = set()  # user_ids whose Supabase history has been loaded
_APP_NAME = "pursuit"


def _get_adk_runner() -> tuple[Runner, InMemorySessionService]:
    global _AGENT, _RUNNER, _SESSION_SVC
    if _RUNNER is None:
        _SESSION_SVC = InMemorySessionService()
        _AGENT = LlmAgent(
            name=_APP_NAME,
            model=_MODEL_NAME,
            instruction="You are Pursuit, a WhatsApp accountability coach.",
            tools=[
                FunctionTool(_tool_log_daily_checkin),
                FunctionTool(_tool_apply_skip_day),
                FunctionTool(_tool_get_my_status),
            ],
            before_model_callback=_inject_instruction,
        )
        _RUNNER = Runner(
            agent=_AGENT,
            session_service=_SESSION_SVC,
            app_name=_APP_NAME,
            auto_create_session=True,
        )
    return _RUNNER, _SESSION_SVC


# ── Main entry point ───────────────────────────────────────────────────────────

async def conversational_reply(
    db: AsyncClient,
    user_id: str,
    user: dict,
    text: str,
    schedules: list[dict],
) -> str:
    """Full conversational agent powered by Google ADK.

    Builds a rich per-request system context (streak, goals, recent activity),
    loads Supabase conversation history into the ADK session on first request,
    runs the ADK agent (which handles the tool-calling loop automatically),
    then persists the new turn back to Supabase.
    """
    from services import conversation as conv_svc

    # Set context vars for this request (each async task gets its own copy)
    _db_ctx.set(db)
    _user_id_ctx.set(user_id)
    _schedules_ctx.set(schedules)

    # Build fresh system context and expose it to the before_model_callback
    instruction = await _build_agent_context(db, user_id, user, schedules)
    _instruction_ctx.set(instruction)

    runner, session_svc = _get_adk_runner()
    session_id = f"whatsapp-{user_id}"

    # On first request after boot, load Supabase history into the ADK session
    if user_id not in _LOADED_SESSIONS:
        existing = await session_svc.get_session(
            app_name=_APP_NAME, user_id=user_id, session_id=session_id
        )
        if existing is None:
            session = await session_svc.create_session(
                app_name=_APP_NAME, user_id=user_id, session_id=session_id
            )
            history = await conv_svc.get_history(db, user_id)
            for i, turn in enumerate(history):
                role = turn["role"]
                author = "user" if role == "user" else _APP_NAME
                event = Event(
                    author=author,
                    content=types.Content(
                        role=role,
                        parts=[types.Part(text=turn["parts"][0]["text"])],
                    ),
                    invocation_id=f"history-{i}",
                    id=Event.new_id(),
                )
                await session_svc.append_event(session=session, event=event)
        _LOADED_SESSIONS.add(user_id)

    # Run the ADK agent and collect the final text response
    new_message = types.Content(role="user", parts=[types.Part(text=text)])
    final_text: str | None = None

    try:
        async for event in runner.run_async(
            user_id=user_id,
            session_id=session_id,
            new_message=new_message,
        ):
            if event.is_final_response() and event.content and event.content.parts:
                final_text = "".join(
                    p.text for p in event.content.parts if p.text
                ).strip()
    except Exception as exc:
        logger.error("adk.conversational_reply_failed", user_id=user_id, error=str(exc))

    if not final_text:
        name = user.get("name", "there")
        final_text = (
            f"Hey {name}! 👋 Got your message. "
            "Something went wrong on my end — please try again in a moment."
        )

    # Persist both sides of the turn to Supabase for cross-restart memory
    try:
        await conv_svc.save_turn(db, user_id, text, final_text)
    except Exception as exc:
        logger.warning("adk.save_turn_failed", error=str(exc))

    return final_text



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

## Available Tools

**log_daily_checkin(completions)**
- What it does: Records today's task completion and updates the streak.
- When to call: Any time {name} reports what they did — "done", "finished", "half done", "only did X", "partial", "completed both", "couldn't do it", "did everything 🔥".
- How to call: Pass a list of all active goal IDs with their completion_pct (0 = missed, 50 = partial, 100 = done). Include every active goal.
- After calling: Always share the new streak and give honest, specific feedback.

**apply_skip_day()**
- What it does: Uses one Skip Day token to protect today's streak despite no activity.
- When to call: {name} says they are skipping today, taking a rest day, need a day off, or explicitly wants to use a Skip Day.
- Do NOT call for partial completions — use log_daily_checkin(50%) instead.
- After calling: Confirm the Skip Day was applied and how many remain.

**get_my_status()**
- What it does: Fetches live streak, Skip Day balance, and today's logged activity from the database.
- When to call: {name} asks about their streak, progress, whether they already checked in, or any live stats. Prefer this over the context data when accuracy matters.

## Behaviour Guidelines
Personality style: {personality}

- Have natural conversations. You are a coach AND a friend.
- A day counts toward the streak only if EVERY active goal is ≥80%. Partial (50%) resets the streak.
- Keep replies concise and WhatsApp-friendly.
- Use *bold* for key numbers/names. Emojis welcome. No # headers. No hashtags."""

