# Pursuit — Backend

> A **WhatsApp accountability coach** that turns your daily habits into streaks, gamification, and real results.

### [🌐 Try the Live App →](https://pursuit-client.vercel.app)

[![Live API](https://img.shields.io/badge/API-Live-brightgreen)](https://pursuit-t3w1.onrender.com/health)
[![Swagger Docs](https://img.shields.io/badge/Docs-Swagger-blue)](https://pursuit-t3w1.onrender.com/docs)

Built with **FastAPI**, **PostgreSQL (Supabase)**, and **Google Gemini 2.5 Flash**. You define daily habits and goals, and Pursuit keeps you honest — sending AI-personalised morning agendas, running evening check-ins via interactive WhatsApp buttons, and turning your consistency into streaks and personal rewards.

---

## How It Works

1. **Sign up** on the web dashboard with your phone number. Receive an OTP on WhatsApp and log in.
2. **Create schedules** — habits like "DSA practice" Mon–Fri at 9 AM, or "Reading" every day.
3. **Every morning** WhatsApp sends an AI-generated motivation message with your day's agenda.
4. **Every evening** WhatsApp sends a consolidated check-in card: *Done ✅ | Halfway ⏳ | Skip Day 🛋️*
5. **Tap a button or reply in text** — the AI agent parses your message, logs your progress, and replies in your chosen personality.

### Streak & Gamification Rules

| Outcome | Streak effect |
|---|---|
| ≥ 80% completion on all goals | Streak +1 |
| < 80% on any goal | Streak resets to 0 |
| Skip Day used | Streak frozen, Skip Day balance −1 |
| Every 7-day streak milestone | +1 Skip Day earned |

Users start with **3 Skip Days**. Set personal milestone rewards (e.g. "Buy headphones at a 30-day streak") and Pursuit unlocks them automatically.

---

## Features

| Feature | Details |
|---|---|
| **Conversational AI Agent** | Full WhatsApp chat powered by Google ADK + Gemini 2.5 Flash. Logs check-ins, answers questions, and applies Skip Days through natural conversation. |
| **Free-text Check-ins** | Reply anything — "done", "only did DSA", "half done 🔥" — and Gemini parses it into per-goal completion percentages automatically. |
| **Conversation Memory** | Last 20 messages per user persisted in Supabase and re-injected into every session, so the agent remembers context across restarts. |
| **Scheduled Messaging** | Morning agendas, evening check-ins, and weekly summaries sent automatically via APScheduler — exact-minute delivery per user timezone. |
| **Bot Personalities** | Three coaching styles: Cheerleader, Drill Sergeant, Analyst. |
| **Streak & Gamification** | Streaks, all-time highs, Skip Days, and milestone rewards tracked per user. |
| **Custom Reminder Times** | Per-user morning and evening reminder times, stored in their local timezone. |
| **WhatsApp OTP Auth** | Passwordless login — OTP delivered via WhatsApp, JWT (HS256) issued on success. |
| **Weekly Summaries** | AI-generated weekly recap with wins, patterns to watch, and a tip for next week. |

---

## Tech Stack

| Layer | Technology |
|---|---|
| Framework | FastAPI (async, Python 3.12+) |
| Database | PostgreSQL via Supabase |
| Migrations | Alembic |
| AI Agent | Google ADK + Gemini 2.5 Flash |
| Scheduling | APScheduler (in-process, no external cron) |
| Auth | JWT (HS256, 7-day tokens) |
| Messaging | Meta WhatsApp Cloud API |
| Logging | structlog |
| Deployment | Render (Python runtime) |

---

## Pursuit AI Agent

The conversational agent is built on **Google ADK** with **Gemini 2.5 Flash**. Every request is seeded with a fresh system context: current streak, active goals with their IDs, last 7 days of activity, pending rewards, and Skip Day balance. Conversation history (last 10 turns) is loaded from Supabase so the agent remembers context across server restarts.

### Agent Tools

| Tool | When it's called |
|---|---|
| `log_daily_checkin` | User reports task completion in any phrasing — "done", "only did gym", "partial 🔥" |
| `apply_skip_day` | User wants to skip today and protect their streak |
| `get_my_status` | User asks about their streak, progress, or whether they already checked in |

### Scheduling (APScheduler)

Cron jobs run **inside the FastAPI process** via APScheduler — no external scheduler or GitHub Actions required. GitHub Actions is used solely for a keep-alive ping every 14 minutes to prevent the Render free tier from sleeping.

| Job | Endpoint | Timing |
|---|---|---|
| Morning ping | `POST /cron/morning-ping` | Per user's `morning_time` in their timezone |
| Evening ping | `POST /cron/evening-ping` | Per user's `evening_time` in their timezone |
| Weekly summary | `POST /cron/weekly-summary` | Once a week |

---

## Architecture

```
Client (React — Vercel)
    │  Bearer token (JWT)
    ▼
FastAPI (Render)
    │
    ├── PostgreSQL (Supabase)   ← users, schedules, logs, streaks, rewards, conversations
    │
    ├── Meta WhatsApp Cloud API ← inbound webhook + outbound messages
    │
    ├── APScheduler             ← morning / evening / weekly jobs (in-process)
    │
    └── Pursuit AI Agent (Google ADK)
            └── Gemini 2.5 Flash
                    ├── log_daily_checkin  → gamification → DB write
                    ├── apply_skip_day     → DB write
                    └── get_my_status      → DB read
```

---

## Local Development

### Prerequisites

- Python 3.12+
- A [Supabase](https://supabase.com/) project (free tier works)
- A [Meta WhatsApp Cloud API](https://developers.facebook.com/docs/whatsapp/cloud-api/get-started) app with:
  - A connected phone number
  - An approved message template named `pursuit_otp` (or your `META_OTP_TEMPLATE_NAME`)
  - A webhook configured to point at `/webhook`
- A [Google AI Studio](https://aistudio.google.com/) API key for Gemini

### Setup

```bash
git clone <repo-url>
cd Pursuit/backend

python -m venv .venv

# macOS / Linux
source .venv/bin/activate
# Windows
.venv\Scripts\Activate.ps1

pip install -r requirements.txt

cp .env.example .env   # fill in your values

alembic upgrade head

python run.py
```

The API will be available at `http://localhost:8000`.

- Swagger UI: `http://localhost:8000/docs`
- ReDoc: `http://localhost:8000/redoc`

> Docs are disabled automatically in production (`APP_ENV=production`).

### Exposing the Webhook Locally

The Meta WhatsApp webhook requires a public HTTPS URL. Use [ngrok](https://ngrok.com/):

```bash
ngrok http 8000
```

Set the webhook URL in the Meta App Dashboard to:

```
https://<your-ngrok-id>.ngrok-free.app/webhook
```

Set the **Verify Token** to match `META_WEBHOOK_VERIFY_TOKEN` in your `.env`.

---

## Deployment

Deploys to [Render](https://render.com) via the `render.yaml` blueprint in this repo.

```
Push to main
    ↓
Render detects render.yaml
    ↓
pip install -r requirements.txt
    ↓
alembic upgrade head  (pre-deploy)
    ↓
uvicorn main:app  →  live at pursuit-t3w1.onrender.com
```

**First-time setup:** Go to Render Dashboard → New → Blueprint, connect the GitHub repo, then fill in every env var marked `sync: false` (Supabase keys, JWT secret, Meta API tokens, Gemini API key, etc.).

---

## Bot Personalities

| Value | Tone |
|---|---|
| `cheerleader` | Warm, encouraging, celebratory |
| `drill_sergeant` | Direct, tough, no excuses |
| `analyst` | Data-driven, neutral, progress-focused |

Set via `PATCH /users/me` with `{ "personality": "drill_sergeant" }`.

---

## License

[MIT](./LICENSE)

