# Social media manager

[`demo.mp4`](demo.mp4) records the social-claude-code package being built in the console and this app in use.

A campaign manager for cross-posting: one piece of content (an article's URL, or pasted text) becomes a post for each
platform in that platform's idiom and limits, with a cross-posting plan: the sequence and timing, a backlink from every
post to the canonical URL tagged per platform (`utm_source=<platform>&utm_medium=social&utm_campaign=<slug>`), and
cross-links between the posts so engagement on one platform feeds the others. The agent is the
[`social-claude-code`](../packages/social-claude-code/) harness package on HarnessGateway, Claude Code tailored to this
job. **It never posts.** A person edits a draft in place, approves it, and the app puts it on the calendar (this demo's
calendar stands in for a scheduler).

```bash
python3 server.py            # http://127.0.0.1:8920 ; HG_API, HG_KEY, HG_MODEL from ./.env
```

## What it shows

| In the app | On the platform |
|---|---|
| A campaign has its agent | one **session** per campaign: `/workspace/campaigns/<slug>/` holds `plan.json`, a file per platform and `strategy.md`, and a revision by note works on the same drafts (`previous_response_id`) |
| Drafts arrive while you keep working | a **background** turn; the server polls the response, waits for the save, and reads `plan.json` through the Containers API |
| The manager's name on every request | `user`: the console's Sessions and Usage show the app (its key, `social`) and the person |
| Reads the web, posts nowhere | the package allows the public web read-only and its own rules refuse every social platform's API; the door refuses private hosts |
| Approve, then it is scheduled | the human step is the app's; the agent drafts and plans |

## Files

| File | What it is |
|---|---|
| `server.py` | campaigns in `data.json`, the drafting and revision turns, edits, approvals, the calendar |
| `index.html` | the page: campaigns, Drafts (edit, revise by note, approve and schedule), Strategy, Calendar, Log |
| `.env` | written by `scripts/setup.py`: `HG_API`, `HG_KEY` (a run-only key labelled `social`), `HG_MODEL` (`social-claude-code/<provider>/<model>`) |
