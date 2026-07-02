# Pursuit

**Pursuit** is a gamified accountability partner that lives in your WhatsApp. You define daily habits and goals, and Pursuit keeps you honest — sending morning reminders, running evening check-ins via interactive WhatsApp buttons, and turning your consistency into streaks, scores, and personal rewards.

> *"Did you do the thing you said you'd do today?"* — Pursuit asks every evening. Your answer builds a streak.

---

## How It Works

1. **Sign up** on the web dashboard with your phone number. Receive an OTP on WhatsApp and log in.
2. **Create schedules** — habits like "DSA practice" Mon-Fri at 9 AM / 9 PM, or "Reading" every day.
3. **Every morning** WhatsApp sends a summary of what you planned for the day.
4. **Every evening** WhatsApp sends an interactive card per schedule: *Done ✅ | Halfway ⏳ | Casual Leave 💤*
5. **Tap a button** — your streak updates and the bot replies in your chosen personality (Cheerleader / Drill Sergeant / Analyst).

### Streak & Gamification Rules

| Outcome | Streak effect |
|---|---|
| ≥ 80% completion | Streak +1 |
| < 80% completion | Streak resets to 0 |
| Casual Leave used | Streak frozen, CL balance -1 |
| Every 7-day streak completed | +1 Casual Leave earned |

Users start with **3 Casual Leaves**. Set personal milestone rewards (e.g. "Buy headphones at a 30-day streak") and Pursuit unlocks them automatically.

---

## Tech Stack

| Layer | Technology |
|---|---|
| Backend framework | [FastAPI](https://fastapi.tiangolo.com/) (Python 3.12+) |
| Database | [Supabase](https://supabase.com/) (PostgreSQL) |
| Migrations | [Alembic](https://alembic.sqlalchemy.org/) |
| Auth | JWT (HS256, 7-day tokens) |
| Messaging | [Meta WhatsApp Cloud API](https://developers.facebook.com/docs/whatsapp) |
| ASGI server | [Uvicorn](https://www.uvicorn.org/) |
| Logging | [structlog](https://www.structlog.org/) |

---


## Prerequisites

- **Python 3.12+**
- A **[Supabase](https://supabase.com/)** project (free tier works)
- A **[Meta WhatsApp Cloud API](https://developers.facebook.com/docs/whatsapp/cloud-api/get-started)** app with:
  - A connected phone number
  - An approved message template named `pursuit_otp` (or whatever you set `META_OTP_TEMPLATE_NAME` to)
  - A configured webhook pointing to `/webhook`

---

## Setup

### 1. Clone the repository

```bash
git clone <repo-url>
cd pursuit/backend

```

### 2. Create and activate a virtual environment

```bash
python -m venv .venv

# macOS / Linux
source .venv/bin/activate

# Windows
.venv\Scripts\activate
```

### 3. Install dependencies

```bash
# Runtime only
pip install -r requirements.txt
```

### 4. Configure environment variables

Create a `.env` file in the `backend/` directory:

For reference, please check `.env.example`

### 5. Run database migrations

Migrations run automatically on server startup. To run them manually:

```bash
cd backend
alembic upgrade head

```

### 6. Start the development server

```bash
python run.py

```

The API will be available at `http://localhost:8000`.

Interactive docs (Swagger UI): `http://localhost:8000/docs`

Alternative docs (ReDoc): `http://localhost:8000/redoc`

> Docs are disabled automatically when `APP_ENV=production`.

---

## Exposing the Webhook Locally

The Meta WhatsApp webhook requires a public HTTPS URL. Use [ngrok](https://ngrok.com/) during development:

```bash
ngrok http 8000

```

Set the webhook URL in your Meta App Dashboard to:

```
https://<your-ngrok-id>.ngrok-free.app/webhook

```

And set the **Verify Token** to match `META_WEBHOOK_VERIFY_TOKEN` in your `.env`.

---

## Bot Personalities

| Value | Tone |
| --- | --- |
| `cheerleader` | Warm, encouraging, celebratory |
| `drill_sergeant` | Direct, tough, no excuses |
| `analyst` | Data-driven, neutral, progress-focused |

Set via `PATCH /users/me` with `{ "personality": "drill_sergeant" }`.

---

## Contributing

1. Fork the repository and create a feature branch from `main`.
2. Follow the existing code style — run `ruff format` and `ruff check` before committing.
3. Add or update tests for any changed behaviour.
4. Ensure `mypy src/` passes with no new errors.
5. Open a pull request with a clear description of what changed and why.

---

## License

[MIT](https://www.google.com/search?q=LICENSE)

