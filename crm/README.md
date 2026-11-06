# CRM with a sales agent

[`demo.mp4`](demo.mp4) records the sales-codex package being built in the console and this app in use.

A small CRM, the kind an account executive lives in: accounts with contacts, deals and notes. Beside every account sits
a **sales agent**: the [`sales-codex`](../packages/sales-codex/) harness package on HarnessGateway, OpenAI's Codex CLI
tailored to this job. The rep asks it for an account brief, an outreach draft, a call plan or next steps, or anything
in plain language; it works in its own sandbox, researches on the public web, writes files into the account's folder
and answers. **It never sends anything.** A rep reads the draft and approves it; only then does the CRM record it as
sent (this demo's outbox stands in for a mail server) or as a note.

```bash
python3 server.py            # http://127.0.0.1:8900 ; HG_API, HG_KEY, HG_MODEL from ./.env
```

## What it shows

| In the CRM | On the platform |
|---|---|
| Each account has its agent | one **session** per account: `previous_response_id` on every request, so the workspace (`/workspace/accounts/<slug>/`) and Codex's own memory carry from task to task |
| A task runs while you keep working | a **background** turn; the server polls the response until it ends, then waits for the save and lists the account's folder with the Containers API |
| The rep's name on every request | `user`: the console's Sessions and Usage pages show the app (the key, named `crm`) and the person |
| Files the agent wrote, viewable in place | `GET /v1/containers/{id}/files/{file}/content`, relayed by the server so the browser never holds the key |
| Approve, then it is sent | the human step is the app's, where it belongs; the agent only drafts |

## Files

| File | What it is |
|---|---|
| `server.py` | the CRM: accounts and notes in `data.json`, the tasks it sends the agent, the approval step |
| `index.html` | the page: accounts, Overview, Agent (tasks, replies, files, approve), Notes & outbox |
| `.env` | written by `scripts/setup.py`: `HG_API`, `HG_KEY` (a run-only key labelled `crm`), `HG_MODEL` (`sales-codex/<provider>/<model>`) |

The three sample accounts are fictional. The agent's web research is real: the package allows the public web and
nothing private.
