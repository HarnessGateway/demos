# Market Desk

A commodities newsroom desk, run by its editors: a schedule of standing stories (the morning briefing, the EIA
weekly data story, a policy explainer), ad-hoc assignments, a research thread, and a review step every draft goes
through before it is approved. The journalist is the [`journalist-pi`](../packages/journalist-pi/) harness package
on HarnessGateway: the pi coding agent tailored to gather intel from the desk's primary sources, form impressions, and
write a cited draft with a list of the claims a human must verify.

```bash
python3 server.py            # http://127.0.0.1:8910 ; HG_API, HG_KEY, HG_MODEL from ./.env
```

**Today** is the day's schedule and assignments (run one now, or the whole day). **Review** shows each draft with its
chart, its sources and its verify list; the editor ticks every claim, sends the draft back with a note (a follow-up turn
on the same response, so the agent revises in the same workspace) or approves it. **Ask** is the desk's research
thread, one session per desk. **Archive** holds what was approved, with the response and session that produced it.

## What it shows

| In the desk | On the platform |
|---|---|
| A story is one assignment | one background turn with `metadata.desk` and `metadata.task`; the agent writes `/workspace/desk/<date>/<desk>-<slug>/` with `draft.md`, `sources.json`, `verify.md` and charts |
| Send back with a note | `previous_response_id`: the revision runs in the same workspace, on the same files |
| The research thread | a session per desk: each question continues the last answer |
| An editor's name on every request | `user`, so Sessions and Usage show the desk app (its key, `market-desk`) and the editor |
| Sources only | the package's egress is the desk's primary sources and nothing else; the door refuses the rest |

## Files

| File | What it is |
|---|---|
| `server.py` | the desk: jobs in `data.json`, the schedule, revisions and approvals, the agent's folder read back |
| `config.json` | the desks and the schedule (times in `timezone`) |
| `index.html` | the page: Today, Review, Ask, Archive |
| `.env` | written by `scripts/setup.py`: `HG_API`, `HG_KEY` (a run-only key labelled `market-desk`), `HG_MODEL` (`journalist-pi/<provider>/<model>`) |
