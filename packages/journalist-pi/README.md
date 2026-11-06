# journalist-pi

A commodities-market journalist agent on the [pi coding agent](https://github.com/badlogic/pi-mono)
(`@mariozechner/pi-coding-agent`). Given a desk (biofuels or crude-oil) and an assignment, it gathers intel
from the desk's primary sources, forms its impressions (what moved, why it matters, what to watch), and authors
a cited report into the workspace. It drafts; it never publishes.

- Pinned CLI: **0.73.1** (`npm: @mariozechner/pi-coding-agent`)
- Provider shape: **anthropic** (pi's `anthropic-messages` API, proxied by the gateway)
- Default model: **deepseek-v4-pro** (`HG_MODEL`)
- Built on the vanilla `pi` package delivered beside it.

## Purpose

The caller is a newsroom market-desk backend: `metadata.desk` names the desk, `metadata.task` the task kind,
and the input is the assignment. The agent reads that desk's pack (below), gathers from its primary sources, and
writes, under `/workspace/desk/<YYYY-MM-DD>/<desk>-<slug>/`:

- `draft.md` — the story, every number cited to a source URL, ending with a **Claims to verify** table
  (`Claim | Source | Status | Note`).
- `sources.json` — `[{"id", "title", "url", "used_for"}]` for every source actually used.
- `verify.md` — the editor's verification table, one row per claim.
- PNG charts (matplotlib) when the numbers warrant, saved next to the draft.

Task kinds: `briefing`, `data-release`, `market-wrap`, `explainer`, `news-short`, `research`.

## Files

| File | Purpose |
|---|---|
| `harness.json` | Manifest: provider, default model, egress (primary sources), `DESK` setting, 1200s turn timeout. |
| `install` | `npm install pi@<version>` + a Python venv with matplotlib and pandas into `$HG_TOOLS`. |
| `run` | One turn: desk+task header + assignment → pi (guard extension loaded) → map pi's JSON stream → Responses events. |
| `seeds/home/.pi/agent/AGENTS.md` | The journalist's standing instructions: role, task kinds, deliverables, and the newsroom rules (source every number, invent nothing, draft only, primary sources only, stay inside the workspace). |
| `seeds/home/.pi/agent/extensions/journalist-guard.ts` | A pi tool-call hook that blocks `write`/`edit` to any path resolving outside the workspace. |
| `seeds/home/.pi/agent/settings.json` | Loads the guard extension; telemetry and provider retries off. |
| `seeds/home/.pi/agent/models.json` | The `anthropic` provider (gateway) and `deepseek-v4-pro`; `run` rewrites it each turn. |
| `seeds/home/desks/{biofuels,crude-oil}/` | Each desk's `glossary.md`, `sources.md`, `style.md`, `calendar.md`. |
| `tests/` | Recorded pi output as fixtures + `test_run.py`. |

## The command

`install` (once): npm-installs pi, then `python3 -m venv $HG_TOOLS/venv` and pip-installs `matplotlib pandas`.

`run` (per turn) launches pi with the venv's `bin` prepended to `PATH` (so the agent's `bash` reaches
matplotlib/pandas), `MPLCONFIGDIR` inside the workspace, `DESK` set, and the guard extension loaded:

```
pi --offline --mode json -p \
   --provider anthropic --model <HG_MODEL> --api-key <HG_PROVIDER_TOKEN> \
   [--append-system-prompt <instructions>] [--thinking <effort>] [--session <path>] \
   "Desk: <desk>\nTask kind: <task>\nAssignment: <assignment>"
```

## Request fields

| Field | Where it goes |
|---|---|
| `input` (user text) | the assignment (argument). Input files are written into the workspace and named in the header. |
| `instructions` + system/developer messages | `--append-system-prompt` |
| `reasoning.effort` | `--thinking` |
| `metadata.desk` | the desk (overrides the `DESK` setting); default `biofuels` |
| `metadata.task` | the task kind; default `briefing` |
| `store: false` | `--no-session` (ephemeral turn) |

Ignored (reported in `metadata.hg_ignored_fields`): `temperature`, `top_p`, `max_output_tokens`,
`max_tool_calls`, `text`, `tools`.

## Output mapping

Identical to the vanilla `pi` package: pi's JSON stream → text/reasoning deltas, `shell_call` for `bash`,
`apply_patch_call` for `write`/`edit`, `function_call` for other tools, usage summed from `agent_end`. An
assistant message with `stopReason: "error"` becomes `response.failed` (401→`authentication_error`,
429→`rate_limit_exceeded`). The terminal event carries `metadata.desk` and `metadata.task`.

## Continuity

Same two paths as vanilla pi: the session UUID is saved to `req.state` the moment pi prints it (a SIGTERM-killed
turn still records it), and the next turn resumes with `--session <path>`; when there is no saved id, the turn
starts a fresh pi session with `req.transcript()` of the earlier conversation prepended.

## May and may not

| Rule | Enforced by | Proven |
|---|---|---|
| May reach the desk's primary sources only (`www.eia.gov`, `www.epa.gov`, `ww2.arb.ca.gov`, `www.federalregister.gov`, `www.ams.usda.gov`, `www.ers.usda.gov`) | `run.egress` (allow-list, deny wins) | egress list is exactly these hosts |
| May not write outside `/workspace` | `journalist-guard.ts` blocks `write`/`edit` | recorded fixture `forbidden-write.stdout`: pi's write to `/tmp/outside.md` returns `Blocked: …`, emitted as a failed `apply_patch_call_output` |
| May not publish | standing instructions (draft only) | instructions |
| May not invent quotes/prices/figures | standing instructions (source every number, invent nothing) | instructions |
| May not use MCP servers or secrets | no `mcp`, no `secrets` in the manifest | manifest |
| Runs only `python3` + standard Unix tools | standing instructions; venv provides matplotlib/pandas | instructions |

Bash-side writes outside the workspace are covered by the standing instructions, not the guard hook (the hook
covers the `write`/`edit` tools).

## Operator settings

| Setting | Default | Meaning |
|---|---|---|
| `DESK` | `biofuels` | The desk this package reports for when a request does not set `metadata.desk`. |

No secrets.

## Known limits

- The same mapping limits as vanilla pi (no per-turn sampling knobs; plain old/new edit diffs; non-built-in
  tools reported as `function_call`).
- CARB's site (`ww2.arb.ca.gov`) sometimes refuses automated fetches (HTTP 419); the desk pack tells the agent
  to retry once and otherwise mark the claim unverified.
- The guard blocks `write`/`edit` by path; bash redirection to an outside path is not intercepted by the hook.

## Tests

`python3 tests/test_run.py` runs `run` against the recorded pi fixtures (a stub `pi` replays them; no network)
and checks every line with `hgkit.check`. Covers the same eight cases as vanilla pi plus the forbidden-write
turn. A live end-to-end turn was also run against the gateway: pi wrote
`/workspace/desk/2026-11-06/biofuels-test/draft.md` inside the workspace and the turn completed with valid
events and the session id saved.
