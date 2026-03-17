# 🔒 WakeLock

> **A Telegram-based prepaid accountability system that enforces waking up on time through automated financial penalties.**

---

## 💡 What is WakeLock?

Most alarm apps fail because they rely purely on self-discipline. WakeLock fixes this by attaching **real financial consequences** to missing your morning alarm.

You lock money upfront. Every morning, a **randomized OTP** drops in a time window. Miss it → money is deducted. No snoozing. No dismissing. No excuses.

---

## ⚙️ How It Works

```
5:00 AM  →  Alarm notification sent via Telegram
5:20 AM  →  Buffer ends (time to freshen up)
5:20–5:30 →  OTP drops at a RANDOM minute in this window
             "WakeLock Code: 482931 — Enter within 2 minutes."
✅ Correct OTP  →  VERIFIED — no penalty
❌ Missed/Wrong →  FAILED   — penalty deducted from locked balance
```

The OTP window is randomized so you **cannot predict the exact drop time** — you have to stay awake and alert.

---

## 🏗️ System Architecture

```
┌─────────────────────────────────────────────────────┐
│                   Telegram Bot UI                    │
│         (User's only interaction layer)              │
└───────────────────┬─────────────────────────────────┘
                    │
┌───────────────────▼─────────────────────────────────┐
│                 FastAPI Backend                      │
│     (Wallet service, Plan management, OTP logic)    │
└──────┬────────────────────────────┬─────────────────┘
       │                            │
┌──────▼──────┐              ┌──────▼──────┐
│  SQLite     │              │    Redis    │
│  (Primary   │              │  (OTP TTL + │
│   Database) │              │Celery Broker│
└─────────────┘              └──────┬──────┘
                                    │
                          ┌─────────▼──────────┐
                          │   Celery + Beat     │
                          │ (Alarm scheduling,  │
                          │  OTP drops,         │
                          │  Penalty execution) │
                          └────────────────────┘
```

---

## 🧠 Key Design Decisions

### 1. Append-Only Financial Ledger
Instead of simple balance updates, every financial movement (Deposit, Lock, Penalty, Withdrawal) is recorded as an **immutable ledger entry**. This ensures:
- Full auditability of funds
- No silent financial bugs
- Mathematical reconciliation at any point

### 2. Randomized OTP Drop
The OTP doesn't drop exactly at the buffer end — it drops at a **random minute within a 10-minute window**. This prevents users from timing their phone checks to the exact second, forcing genuine alertness.

### 3. State Machine for Daily Sessions
Each morning attempt follows a strict, immutable state machine:
```
PENDING → ALARM_SENT → OTP_ACTIVE → VERIFIED
                                  ↘ FAILED
```
Once a state is set, it cannot be reversed — preventing replay attacks and race conditions.

### 4. Idempotent Penalty Execution
Penalty tasks include a `processed_flag` to ensure that even if a Celery worker crashes and retries, **a user is never double-charged.**

### 5. Redis TTL for OTP
OTPs are stored in Redis with a 2-minute TTL. When the window expires, the OTP literally ceases to exist in memory — no database bloat, no manual cleanup needed.

### 6. Decoupled Plans from Preferences
Users can change their alarm time without cancelling their financial plan. `UserPreference` (alarm config) is completely separate from `AccountabilityPlan` (financial commitment).

---

## 💰 Virtual Wallet System

```
User Wallet
├── total_balance
├── locked_balance      ← Held by active plan
└── available_balance   ← Freely withdrawable

Transaction Types:
  DEPOSIT   → available_balance ↑
  LOCK      → locked_balance ↑, available_balance ↓
  PENALTY   → locked_balance ↓, platform_revenue ↑
  UNLOCK    → locked_balance ↓, available_balance ↑
```

> No external payment gateway. No Razorpay. No real payouts. Pure internal ledger simulation.

---

## 📋 Subscription Plan Model

| Field | Details |
|-------|---------|
| Minimum Duration | 7 days |
| Minimum Amount | ₹70 |
| Penalty Formula | `total_locked ÷ number_of_days` |
| Plan Types | Weekly / Monthly / Custom |

**Example:** ₹70 locked for 7 days = ₹10 penalty per missed day.

---

## 🗃️ Domain Models

| Model | Purpose |
|-------|---------|
| `User` | Telegram identity mapping |
| `Wallet` | Live balance cache |
| `WalletTransaction` | Immutable ledger entries |
| `AccountabilityPlan` | Financial commitment schema |
| `WakeSession` | Daily morning attempt state machine |
| `UserPreference` | Alarm time + buffer configuration |
| `OTPToken` | Hashed token with expiry metadata |
| `PlatformRevenue` | Penalty accumulation tracker |

---

## 🔐 Anti-Cheat Mechanisms

| Mechanism | Prevents |
|-----------|---------|
| Randomized OTP drop time | Exact-timing exploit |
| 2-minute expiry window | Lazy verification |
| Server-side scheduling only | Manual trigger bypass |
| Hashed OTP storage | Token interception |
| Single-use tokens | Replay attacks |
| Idempotent deduction | Duplicate penalty charges |

---

## 🛠️ Tech Stack

| Layer | Technology |
|-------|-----------|
| API | FastAPI (async) |
| Database | SQLite + SQLAlchemy 2.0 (async) |
| Cache / OTP Store | Redis |
| Task Queue | Celery + Celery Beat |
| Bot Interface | Python Telegram Bot API |
| Migrations | Alembic |
| Language | Python 3.x |

---

## 🚧 Challenges Solved

**1. Async Event Loop Conflict**
`python-telegram-bot` and FastAPI's `asyncio` loop conflicted when using default `run_polling`. Solved by implementing manual piecemeal polling within FastAPI's `@lifespan` context manager.

**2. SQLite + Alembic Migration Locks**
Alembic's `batch_alter_table` struggled with SQLite's non-transactional DDL during foreign key reflection. Solved by crafting isolated "ghost" tables to bypass schema reflection issues.

**3. Race Conditions in Distributed Scheduling**
Mapping state cleanly across Telegram → Celery → DB without race conditions required strict state machine isolation with processed flags on all financial operations.

---





