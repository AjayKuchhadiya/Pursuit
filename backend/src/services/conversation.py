"""Conversation history store for the WhatsApp conversational agent.

Strategy
--------
* Store the most recent STORE_LIMIT messages per user in the `conversations`
  table (alternating role=user / role=model).
* On every request the agent receives the last CONTEXT_LIMIT messages so
  Gemini has recent context without blowing up the token budget.
* Tool-call intermediates are NOT stored — only the final visible replies.
* After each save we prune messages beyond STORE_LIMIT (trim oldest first).
"""

from __future__ import annotations

from supabase._async.client import AsyncClient

# Messages handed to the LLM on each request (5 back-and-forth turns)
CONTEXT_LIMIT = 10

# Messages kept in the DB per user before pruning
STORE_LIMIT = 20


async def get_history(db: AsyncClient, user_id: str) -> list[dict]:
    """Return the last CONTEXT_LIMIT messages as Gemini-compatible content dicts.

    Returned list is ordered oldest-first (as Gemini requires for multi-turn).
    """
    res = (
        await db.table("conversations")
        .select("role, content")
        .eq("user_id", user_id)
        .order("created_at", desc=True)
        .limit(CONTEXT_LIMIT)
        .execute()
    )
    rows = list(reversed(res.data or []))
    return [{"role": row["role"], "parts": [{"text": row["content"]}]} for row in rows]


async def save_turn(
    db: AsyncClient,
    user_id: str,
    user_text: str,
    model_text: str,
) -> None:
    """Persist both sides of a conversation turn, then prune old messages."""
    await db.table("conversations").insert(
        [
            {"user_id": user_id, "role": "user", "content": user_text},
            {"user_id": user_id, "role": "model", "content": model_text},
        ]
    ).execute()
    await _prune(db, user_id)


async def _prune(db: AsyncClient, user_id: str) -> None:
    """Keep only the STORE_LIMIT most recent messages for this user."""
    res = (
        await db.table("conversations")
        .select("id")
        .eq("user_id", user_id)
        .order("created_at", desc=True)
        .execute()
    )
    rows = res.data or []
    if len(rows) > STORE_LIMIT:
        ids_to_delete = [r["id"] for r in rows[STORE_LIMIT:]]
        await db.table("conversations").delete().in_("id", ids_to_delete).execute()
