# Fintrix

### AI-Powered Financial Reconciliation & Exception Management

Fintrix is an AI-powered finance controller that automates transaction reconciliation, identifies discrepancies, investigates exceptions, and provides controlled resolution workflows.

Built for the **Razorpay AI Buildathon — Finance Controller Track**.

---

## What Fintrix Does

Fintrix transforms the traditional manual reconciliation workflow into an automated, AI-assisted pipeline.

```text
Payment & Settlement Data
          ↓
     Data Ingestion
          ↓
 Reconciliation Engine
          ↓
 ┌────────┴────────┐
 ↓                 ↓
Matched         Exceptions
                    ↓
            AI Investigation
                    ↓
          ┌─────────┴─────────┐
          ↓                   ↓
       Resolve             Escalate
          └─────────┬─────────┘
                    ↓
               Audit Trail
```

## Key Features

* **Automated Reconciliation** — Match payments, settlements, and financial records.
* **Exception Detection** — Identify mismatches, missing transactions, duplicates, and discrepancies.
* **AI Investigation** — Analyze exceptions, gather context, evaluate evidence, and recommend resolutions.
* **Resolution Guardrails** — Apply confidence and transaction-value thresholds before automated resolution.
* **Human Escalation** — Route high-value or low-confidence cases for manual review.
* **Real-Time Processing** — Process payment and reconciliation events through WebSockets and webhooks.
* **Audit Trail** — Track financial actions, decisions, state changes, and investigation history.
* **Analytics** — Monitor reconciliation performance, exceptions, resolution time, and operational savings.
* **Razorpay Integration** — Support payments, settlements, OAuth, and webhook events.

## Tech Stack

| Layer          | Technologies                          |
| -------------- | ------------------------------------- |
| Frontend       | React, TypeScript, Vite, Tailwind CSS |
| Backend        | Python, FastAPI, SQLAlchemy           |
| Database       | PostgreSQL                            |
| AI             | Google Gemini                         |
| Payments       | Razorpay API, OAuth, Webhooks         |
| Real-Time      | WebSockets                            |
| Security       | JWT, RBAC                             |
| Infrastructure | Docker                                |

## Architecture

```text
                         Razorpay
                            │
                    API / OAuth / Webhooks
                            │
                            ▼
                    ┌───────────────┐
                    │   Ingestion   │
                    └───────┬───────┘
                            │
                            ▼
                 ┌────────────────────┐
                 │ Reconciliation      │
                 │ Engine              │
                 └─────────┬──────────┘
                           │
                    ┌──────┴──────┐
                    │             │
                 Matched       Exception
                                  │
                                  ▼
                         ┌────────────────┐
                         │ AI Investigator│
                         └───────┬────────┘
                                 │
                         ┌───────┴───────┐
                         │               │
                      Resolve         Escalate
                         │               │
                         └───────┬───────┘
                                 ▼
                           Audit Trail
                                 │
                                 ▼
                            PostgreSQL
                                 │
                                 ▼
                           React Dashboard
```

## Project Structure

```text
Fintrix/
├── backend/
│   ├── app/
│   │   ├── routers/
│   │   ├── services/
│   │   ├── utils/
│   │   ├── database.py
│   │   ├── models.py
│   │   ├── schemas.py
│   │   └── main.py
│   ├── requirements.txt
│   └── Dockerfile
│
├── frontend/
│   ├── src/
│   │   ├── components/
│   │   ├── api.ts
│   │   ├── App.tsx
│   │   └── main.tsx
│   ├── package.json
│   └── Dockerfile
│
└── .env.example
```

## Getting Started

### Prerequisites

* Python 3.10+
* Node.js 18+
* PostgreSQL
* npm

### Backend

```bash
cd backend

python -m venv .venv
```

Windows:

```bash
.venv\Scripts\activate
```

Linux/macOS:

```bash
source .venv/bin/activate
```

```bash
pip install -r requirements.txt
uvicorn app.main:app --reload --port 8000
```

### Frontend

```bash
cd frontend
npm install
npm run dev
```

### Environment

Create a `.env` file from `.env.example`:

```env
DATABASE_URL=your-database-url
GEMINI_API_KEY=your-api-key
LLM_PROVIDER=gemini
```

Never commit credentials or API keys.

## Demo Flow

```text
1. Connect / Ingest Financial Data
2. Run Reconciliation
3. Review Matched Transactions
4. Investigate Exceptions with AI
5. Resolve or Escalate
6. Review Audit Trail
7. Analyze Performance & ROI
```

## Hackathon

**Razorpay AI Buildathon**
**Track:** Finance Controller
**Project:** Fintrix
