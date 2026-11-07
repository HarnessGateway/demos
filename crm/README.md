# Showroom CRM, with a sales agent in it

A small business's CRM: a home-improvement showroom in Austin and its 75 customers, each with an address on the map,
a pipeline stage, a deal value, a lead source, a follow-up date, notes and an activity log. Inside it sits a **sales
agent**: the [`sales-codex`](../packages/sales-codex/) harness package on HarnessGateway, OpenAI's Codex CLI tailored
to this job. Ask it anything about the customers ("Who should I call today?", "Draft follow-up texts for the five most
overdue follow-ups", "Plan a route for home consults with the six closest leads") and it reads the whole CRM, does the
arithmetic in its sandbox and answers. When the answer means reaching customers, it drafts the emails and texts, and
the CRM puts them in the **Outbox**. Nothing leaves until a person presses Send.

```bash
python3 server.py            # http://127.0.0.1:8900 ; HG_API, HG_KEY, HG_MODEL from ./.env (scripts/setup.py)
```

The first start creates `crm.db` (SQLite) and fills it from `seed.json`: made-up people at real, geocoded Austin
addresses, with their history moved so it reads as if it happened in the last eight months. Delete `crm.db` to start
over.

## How the agent is wired in

| In the CRM | On the platform |
|---|---|
| ✨ Ask, with the question and a snapshot of the CRM | a **background** Responses request from the CRM's server with a run-only key; the snapshot goes with it as an `input_file` named `customers.json` (every customer, distance from the store, every activity) |
| Follow-up questions in the same chat | `previous_response_id`: the same **session**, so the agent's scratch work and Codex's memory carry over; each question still carries a fresh snapshot |
| The agent's steps while it works | the response's `shell_call` items, polled every few seconds |
| Drafts land in the Outbox | the agent ends its answer with one fenced `crm-drafts` block of JSON (`contact_id`, `channel`, `subject`, `body`); the package's standing instructions define it, the CRM parses it |
| Send | the CRM's own step: SMTP or Twilio when configured, otherwise the message is approved and logged on the customer |

The agent never sees a provider key, a mail password or the database: it gets a snapshot and returns text.

## Sending for real (optional)

Add to `crm/.env`:

```bash
CRM_SMTP_HOST=smtp.gmail.com
CRM_SMTP_PORT=587
CRM_SMTP_USER=you@example.com
CRM_SMTP_PASSWORD=an-app-password
CRM_EMAIL_FROM=Showroom <you@example.com>
CRM_TWILIO_SID=AC...
CRM_TWILIO_TOKEN=...
CRM_TWILIO_FROM=+15125550100
CRM_TEST_MODE=1                      # 1: every message goes to the test address below, not the customer
CRM_TEST_EMAIL=you@example.com
CRM_TEST_PHONE=+15125550100
```

## Files

| File | What it is |
|---|---|
| `server.py` | the CRM: SQLite, geocoding (US Census, then OpenStreetMap), distances, the snapshot, the agent, the Outbox |
| `index.html` | the page: pipeline, list and map, a customer drawer with activity, the agent, the Outbox, settings |
| `seed.json` | the 75 demo customers and their 170 activities, with dates relative to the day the database is made |
| `.env` | written by `scripts/setup.py`: `HG_API`, `HG_KEY` (a run-only key labelled `crm`), `HG_MODEL` |
