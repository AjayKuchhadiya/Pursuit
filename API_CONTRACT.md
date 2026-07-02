# Pursuit — API Contract

> **For the frontend team.** This document covers everything you need to build the Pursuit web dashboard against the backend API.

---

## Table of Contents

1. [What is Pursuit?](#1-what-is-pursuit)
2. [Intended User Experience](#2-intended-user-experience)
3. [Base URL & Auth](#3-base-url--auth)
4. [Authentication](#4-authentication)
5. [Users](#5-users)
6. [Schedules](#6-schedules)
7. [Logs](#7-logs)
8. [Leaves](#8-leaves)
9. [Rewards](#9-rewards)
10. [Error Responses](#10-error-responses)
11. [Types Reference](#11-types-reference)

---

## 1. What is Pursuit?

Pursuit is a **gamified accountability partner delivered through WhatsApp**. Users define daily habits and goals (called *schedules*), and the system keeps them on track through automated WhatsApp reminders and an interactive check-in flow.

At its core, Pursuit answers one question every evening: *"Did you do the thing you said you'd do today?"* — and turns the answer into a streak, a score, and eventually a reward.

The web dashboard (what the FE team is building) is the **setup and visibility layer**:
- Users sign up and configure their schedules here
- They see their progress, streaks, and history here
- WhatsApp handles all the real-time interaction (reminders, check-ins, replies)

---

## 2. Intended User Experience

### Onboarding

1. User lands on the web app and enters their **phone number** (with country code, e.g. `+917457878864`).
2. They tap **"Send OTP"** — the backend sends a WhatsApp message with a 6-digit code.
   - ⚠️ **Important for new users:** If the user has never texted the bot before, they may not receive the OTP due to WhatsApp's 24-hour conversation window. The API response includes an `onboarding` block with a `whatsapp_url` — display a banner: *"Didn't receive the OTP? [Open WhatsApp & say Hi →]"* (link opens `whatsapp_url`). Once they send any message, they tap Resend and it works.
3. User enters the OTP → receives a **JWT token** → is authenticated.
4. First time: user chooses their **bot personality** (Cheerleader / Drill Sergeant / Analyst) — this controls the tone of WhatsApp replies.

### Core Loop (Daily)

```
Morning
  └─ WhatsApp message: "Here's what you planned today: 1. DSA 2. Python"

Evening
  └─ WhatsApp interactive card per schedule:
       "How much progress on DSA today?"
       [Done (100%) ✅]  [Halfway (50%) 🔄]  [Casual Leave 🛋️]

User taps a button
  └─ Streak updates
  └─ WhatsApp reply with personality-matched encouragement
```

### Streak & Gamification Rules

| Completion | Streak effect |
|---|---|
| ≥ 80% | Streak +1 |
| < 80% | Streak resets to 0 |
| Casual Leave | Streak frozen (not reset), CL balance −1 |
| Every 7-day streak | +1 Casual Leave earned |

### Dashboard Pages (suggested)

| Page | Purpose |
|---|---|
| **Home / Stats** | Streak count, all-time high, CL balance, today's schedules |
| **Schedules** | Create / edit / delete habit schedules with days and times |
| **History** | Log list with date filter; GitHub-style heatmap |
| **Rewards** | Set milestone rewards, see which are unlocked |
| **Settings** | Change bot personality, timezone |

---

## 3. Base URL & Auth

| Environment | Base URL |
|---|---|
| Local dev | `http://localhost:8000` |
| Via ngrok | `https://<your-ngrok-id>.ngrok-free.app` |
| Production | TBD |

Interactive docs (dev only): `http://localhost:8000/docs`

### Authentication header

All endpoints except `/auth/*` require a Bearer token:

```
Authorization: Bearer <jwt_token>
```

Tokens are valid for **7 days**. On expiry, send the user back to the OTP flow.

---

## 4. Authentication

### `POST /auth/otp/request`

Request a one-time password sent to the user's WhatsApp.

**Request body:**
```json
{
  "phone_number": "+917457878864"
}
```

> Phone must be E.164 format: `+` followed by country code and number, no spaces.

**Response `202 Accepted`:**
```json
{
  "detail": "OTP sent to your WhatsApp number.",
  "onboarding": {
    "required_if_new_user": true,
    "instruction": "If you don't receive the OTP within 30 seconds, send any message to +14155238886 on WhatsApp first, then tap 'Resend'.",
    "whatsapp_url": "https://wa.me/14155238886"
  }
}
```

> `onboarding` is only present when the bot number is configured. Always render it if it exists.

**Errors:**
| Status | Meaning |
|---|---|
| `422` | Phone number not in E.164 format |
| `502` | WhatsApp delivery failed (show retry) |

---

### `POST /auth/otp/verify`

Verify the OTP and receive an access token.

**Request body:**
```json
{
  "phone_number": "+917457878864",
  "otp": "483921"
}
```

**Response `200 OK`:**
```json
{
  "access_token": "eyJhbGciOiJIUzI1NiIsInR5cCI6...",
  "token_type": "bearer"
}
```

Store `access_token` in memory or `localStorage`. Attach it as `Authorization: Bearer <token>` on every subsequent request.

**Errors:**
| Status | Meaning |
|---|---|
| `400` | OTP is wrong, expired (10 min TTL), or already used |
| `422` | Validation error |

---

## 5. Users

### `GET /users/me`

Get the current user's profile.

**Response `200 OK`:**
```json
{
  "id": "fc262eda-1148-4718-b7c2-75fb70cebc84",
  "phone_number": "+917457878864",
  "personality": "cheerleader",
  "timezone": "Asia/Kolkata",
  "is_active": true
}
```

---

### `PATCH /users/me`

Update personality or timezone.

**Request body** (all fields optional):
```json
{
  "personality": "drill_sergeant",
  "timezone": "Asia/Kolkata"
}
```

`personality` values: `"cheerleader"` | `"drill_sergeant"` | `"analyst"`

`timezone` must be a valid IANA timezone string (e.g. `"Asia/Kolkata"`, `"America/New_York"`).

**Response `200 OK`:** Updated `UserRead` object (same shape as `GET /users/me`).

---

### `GET /users/me/stats`

Dashboard header data — streak and leave balance.

**Response `200 OK`:**
```json
{
  "current_streak": 12,
  "all_time_high": 21,
  "cl_balance": 2.0
}
```

---

## 6. Schedules

A schedule is one recurring habit/goal. A user can have multiple schedules (e.g. "DSA Practice" Mon–Fri, "Reading" every day). Each gets its own morning mention and evening check-in card.

### `GET /schedules`

List all schedules for the current user (including inactive ones).

**Response `200 OK`:**
```json
[
  {
    "id": "c0d43ffc-33e7-453b-9728-6663772ac152",
    "user_id": "fc262eda-1148-4718-b7c2-75fb70cebc84",
    "title": "DSA + Python",
    "is_active": true,
    "morning_time": "08:00",
    "evening_time": "21:00",
    "days_of_week": [0, 1, 2, 3, 4]
  }
]
```

---

### `POST /schedules`

Create a new schedule.

**Request body:**
```json
{
  "title": "DSA + Python",
  "morning_time": "08:00",
  "evening_time": "21:00",
  "days_of_week": [0, 1, 2, 3, 4]
}
```

| Field | Type | Default | Notes |
|---|---|---|---|
| `title` | string | required | What the habit is called |
| `morning_time` | `"HH:MM"` | `"08:00"` | Time to receive morning reminder |
| `evening_time` | `"HH:MM"` | `"21:00"` | Time to receive evening check-in |
| `days_of_week` | `int[]` | `[0,1,2,3,4,5,6]` | Which days this schedule is active. `0=Mon … 6=Sun` |

**Response `201 Created`:** Created `ScheduleRead` object.

---

### `PATCH /schedules/{schedule_id}`

Update a schedule. All fields optional.

**Request body:**
```json
{
  "title": "DSA Only",
  "morning_time": "09:00",
  "days_of_week": [1, 3, 5]
}
```

**Response `200 OK`:** Updated `ScheduleRead` object.

---

### `DELETE /schedules/{schedule_id}`

Soft-deletes the schedule (`is_active = false`). It stops appearing in reminders but history is preserved.

**Response `204 No Content`**

---

## 7. Logs

Logs are created automatically when the user taps a button in the WhatsApp evening check-in. They are read-only from the frontend.

### `GET /logs`

Get daily log history. Supports optional date range filtering.

**Query params:**
| Param | Type | Example |
|---|---|---|
| `start` | `YYYY-MM-DD` | `2026-06-01` |
| `end` | `YYYY-MM-DD` | `2026-06-23` |

**Response `200 OK`:**
```json
[
  {
    "id": "...",
    "user_id": "...",
    "schedule_id": "...",
    "log_date": "2026-06-23",
    "completion_pct": 100,
    "is_casual_leave": false
  }
]
```

---

### `GET /logs/heatmap`

Returns log data formatted for a GitHub-style contribution heatmap. Supports same `start`/`end` query params.

**Response `200 OK`:**
```json
[
  { "date": "2026-06-01", "value": 100, "entry_type": "done" },
  { "date": "2026-06-02", "value": 50,  "entry_type": "partial" },
  { "date": "2026-06-03", "value": 0,   "entry_type": "casual_leave" },
  { "date": "2026-06-04", "value": 0,   "entry_type": "missed" }
]
```

| `entry_type` | Meaning | Suggested colour |
|---|---|---|
| `done` | ≥ 80% completion | Green `#22c55e` |
| `partial` | > 0% but < 80% | Yellow `#eab308` |
| `casual_leave` | CL used | Blue `#3b82f6` |
| `missed` | 0%, no CL | Red `#ef4444` |

---

## 8. Leaves

Casual Leaves (CLs) let users skip a day without breaking their streak. Users start with 3 CLs and earn 1 more per completed 7-day streak.

### `GET /leaves`

Get current CL balance.

**Response `200 OK`:**
```json
{
  "balance": 2.0
}
```

---

### `POST /leaves/apply`

Apply a Casual Leave for today from the dashboard (alternative to tapping the WhatsApp button). Requires an active schedule with no log for today.

**Request body:** _(empty)_

**Response `200 OK`:**
```json
{
  "streak": 5,
  "cl_balance": 1.0,
  "message": "Casual Leave applied. Streak preserved at 5 days."
}
```

**Errors:**
| Status | Meaning |
|---|---|
| `400` | No active schedule, or CL balance is 0 |
| `409` | Already logged today |

---

## 9. Rewards

Users can set personal milestone rewards — e.g. "Buy new headphones when I hit a 30-day streak". The backend unlocks them automatically when the condition is met.

### `GET /rewards`

List all rewards for the current user.

**Response `200 OK`:**
```json
[
  {
    "id": "...",
    "user_id": "...",
    "title": "New mechanical keyboard",
    "condition_type": "streak_days",
    "condition_value": 30.0,
    "is_unlocked": false
  }
]
```

---

### `POST /rewards`

Create a new reward milestone.

**Request body:**
```json
{
  "title": "New mechanical keyboard",
  "condition_type": "streak_days",
  "condition_value": 30
}
```

| `condition_type` | Meaning |
|---|---|
| `streak_days` | Unlocked when current streak reaches N days |
| `weekly_avg_pct` | Unlocked when weekly average completion ≥ N% |
| `total_days` | Unlocked when total logged days reaches N |

**Response `201 Created`:** Created `RewardRead` object.

---

## 10. Error Responses

All errors return JSON with a `detail` field:

```json
{ "detail": "No valid OTP found. Please request a new one." }
```

| Status | When |
|---|---|
| `400` | Bad request (business logic failure) |
| `401` | Missing or invalid/expired JWT |
| `403` | Forbidden |
| `404` | Resource not found |
| `409` | Conflict (e.g. duplicate log for today) |
| `422` | Validation error — `detail` is an array of field errors |
| `500` | Internal server error |
| `502` | Upstream failure (WhatsApp API unreachable) |

---

## 11. Types Reference

### `days_of_week`
Integer array where `0 = Monday`, `6 = Sunday` (Python `datetime.weekday()` convention).

```
[0, 1, 2, 3, 4]       → Mon–Fri
[5, 6]                 → Sat–Sun
[0, 1, 2, 3, 4, 5, 6] → Every day
```

### `personality`
| Value | Bot tone |
|---|---|
| `cheerleader` | Warm, encouraging, celebratory |
| `drill_sergeant` | Direct, tough, no excuses |
| `analyst` | Data-driven, neutral, progress-focused |

### `timezone`
Any valid IANA timezone string. Common ones:
- `Asia/Kolkata` (IST, UTC+5:30)
- `America/New_York` (ET)
- `Europe/London` (GMT/BST)
- `Asia/Singapore` (SGT, UTC+8)

Full list: https://en.wikipedia.org/wiki/List_of_tz_database_time_zones

### `HH:MM` times
All times are stored and sent in **24-hour format** in the **user's local timezone** (set via `PATCH /users/me`). The backend converts to UTC internally.

---

*Last updated: 2026-06-23*
