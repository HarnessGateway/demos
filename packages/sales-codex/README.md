# sales-codex

A showroom's sales assistant, on the Codex CLI. It is the agent inside the [Showroom CRM](../../crm/).

- **Each turn** the CRM sends a question and its whole state as a file, `customers.json`. The agent finds it at
  `inputs/customers.json` in its work folder, replaced with the fresh one every turn.
- **It answers** in short prose with names and numbers from the data and, when reaching customers is called for,
  ends with one fenced `crm-drafts` block: a JSON array of `{contact_id, channel, subject, body}`. The CRM puts
  those in its Outbox; a person sends them.
- **It reaches** nothing but its model.
- **Settings:** `STORE_PROFILE` (what the store sells and the voice it writes in) and `SIGNATURE`.
- **Provider API:** OpenAI Responses.

`install` and `run` are the `codex` package's, unchanged. What makes it the sales assistant is
[`seeds/mind/.codex/AGENTS.md`](seeds/mind/.codex/AGENTS.md), which Codex reads on its own.
