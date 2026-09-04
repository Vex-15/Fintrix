# Fintrix

### AI-Powered Financial Reconciliation & Exception Management

Fintrix automates the reconciliation of **settlements against bank credits**, replacing manual spreadsheet-based checks with a combination of deterministic financial rules and targeted AI investigation.

> **Rules handle what can be calculated. AI handles what needs reasoning.**

## What It Does

* **Automated Reconciliation** — Matches transactions, settlements, and bank credits using IDs, amounts, timing, fees, GST, and fuzzy matching.
* **Exception Detection** — Identifies missing settlements, duplicates, timing issues, fee/GST discrepancies, and amount mismatches.
* **AI Investigation** — Investigates genuinely ambiguous exceptions, generates possible causes, cites financial evidence, and assigns confidence.
* **Resolution Guardrails** — Uses confidence and amount thresholds to determine whether an exception can be safely resolved or requires human review.
* **Analytics & Forecasting** — Tracks reconciliation performance, financial discrepancies, tax/fee differences, and short-term cash flow.
* **Q&A Agent** — Lets finance teams ask questions about their reconciliation data in natural language instead of SQL.
* **Audit Trail** — Records reconciliation, investigation, and resolution activity for traceability.

## How It Works

```text
Transactions + Settlements + Bank Credits
                  ↓
          Deterministic Rules
                  ↓
             Reconciliation
             ↙           ↘
         Matched       Exception
                          ↓
                    AI Investigation
                          ↓
                   Risk Guardrails
                    ↙           ↘
                Resolve       Escalate
                          ↓
                     Audit Trail
```

## Why AI Isn't Used Everywhere

Most reconciliation problems are deterministic. Sending every exception to an LLM would add unnecessary cost, latency, and uncertainty.

Fintrix therefore uses AI **only when the rules cannot confidently explain an exception**.

AI decisions are grounded in actual transaction/settlement evidence and constrained by resolution guardrails.

## Demo Mode

This repository currently runs primarily in **Demo Mode** using deterministic synthetic financial data.

### Available in Demo Mode

* Full reconciliation pipeline
* Exception detection
* AI investigation
* Evidence & confidence scoring
* Resolution recommendations
* Guardrails & human review
* Analytics
* Tax/fee reconciliation
* Cash forecasting
* Natural-language Q&A
* Audit trail

### Intentionally Held Back

To keep the demo safe, reproducible, and independent of external systems:

* Live Razorpay financial data
* Production Razorpay OAuth/API operations
* Live production webhooks
* Real financial transactions or irreversible actions
* External Slack/email notification workflows

The **core reconciliation and AI investigation pipeline runs end-to-end**; Demo Mode mainly replaces live inputs and external actions with controlled data.

## Tech Stack

**Frontend:** React, TypeScript, Vite, Tailwind CSS
**Backend:** Python, FastAPI, SQLAlchemy
**Database:** PostgreSQL / SQLite
**AI:** Google Gemini
**Integration:** Razorpay API architecture
**Realtime:** Server-Sent Events
**Deployment:** Docker

## Built For

**Razorpay AI Buildathon**

Fintrix explores how AI can make financial reconciliation faster and more intelligent **without giving an LLM unrestricted control over financial decisions.**

---

**Author:** Vedant Kowdiki · [GitHub](https://github.com/Vex-15)
