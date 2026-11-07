# social-claude-code

A **social media manager agent** on Anthropic's Claude Code CLI (`@anthropic-ai/claude-code`), pinned to **2.1.319**.
Given a campaign, it reads the source and writes engagement drafts, a cross-posting plan, and a strategy — and it
**never posts anything**. A person approves each draft in the social media management app, which does the scheduling
and posting.

The package is one harness: the Claude Code CLI headless in the sandbox, plus the organization's layer — the
standing instructions, the permission deny list, the PreToolUse hook, the platform reference, and the operator
settings.

## Purpose

A campaign arrives in the request as either a **URL to read** (the canonical source) or **pasted text**, plus the
**goal**, the **audience**, the **brand voice** (when `BRAND_VOICE` is not set), and the **platforms**. The agent:

1. reads the source fully before writing (WebFetch, falling back to `curl -sL`);
2. writes one engagement draft per platform in that platform's own idiom and limits — X (280 chars, thread when
   warranted), LinkedIn (≤1300 chars, first two lines carry it), Instagram (caption with hook + line breaks +
   hashtags at the end, plus alt text for a suggested image), Threads, Bluesky (300), Mastodon (500), Facebook;
3. plans cross-posting — sequence/timing over the first days, which platform leads/follows/re-shares, a backlink on
   every post to the canonical URL with `utm_source=<platform>&utm_medium=social&utm_campaign=<slug>`, and
   cross-links between posts;
4. writes `/workspace/campaigns/<slug>/plan.json`, one `<platform>.md` per platform, and `strategy.md`;
5. answers in prose and **ends every answer with exactly one fenced `social-plan` block** holding the same JSON as
   `plan.json`.

A follow-up turn (the app sends `previous_response_id`) may revise one platform's draft or write variants (e.g.
three X hooks), then rewrites `plan.json` and the affected files so they stay in agreement.

The method is in `seeds/home/.claude/CLAUDE.md` (workflow, hard limits, `plan.json` schema, the `social-plan` block
contract, the "never" list) and `seeds/home/.claude/reference/platforms.md` (per-platform idioms and the
cross-posting conventions).

## Files

| File | What it is |
|---|---|
| `harness.json` | the manifest: name, version `2.1.319-1`, `anthropic` provider API, default model `deepseek-v4-pro`, install/run egress, timeouts, `persist`, operator `settings` |
| `install` | bash: `npm install -g` of the pinned CLI into `$HG_TOOLS`, 3 retries, `--allow-scripts=@anthropic-ai/claude-code`, version check |
| `run` | Python: one turn — request in, `claude -p --output-format stream-json` run, Responses events out; both continuity paths; the Mapper below |
| `seeds/home/.claude/CLAUDE.md` | standing instructions: the method, limits, schema, block contract, "never" list |
| `seeds/home/.claude/reference/platforms.md` | per-platform idioms/limits, voice rules, cross-posting conventions |
| `seeds/home/.claude/settings.json` | `permissions.deny` (git remote ops, package managers) and the `PreToolUse` hook |
| `seeds/home/.claude/hooks/guard.py` | the PreToolUse guard: refuses sending, social API hosts, Mastodon `/api/`, writes outside the workspace |
| `tests/` | recorded CLI output as fixtures + `test_run.py` (runs `run` on them, checks every line with `hgkit.check`, and unit-tests the guard) |

There is no `seeds/workspace/` starter (the agent creates `campaigns/<slug>/` itself) and no `mcp` catalog, and the
package declares **no secrets** — the provider key is a per-turn token, and the operator settings are plain values,
never keys.

## The command

`run` executes (on the sandbox's `python3`, with `hgkit` on `PYTHONPATH`):

```
claude -p --output-format stream-json --verbose --include-partial-messages \
  --dangerously-skip-permissions --system-prompt-snapshot off \
  --tools Read,Grep,Glob,Write,Edit,WebFetch,WebSearch,Bash \
  --model <HG_MODEL> \
  [--resume <session-id>] \
  [--append-system-prompt-file <tmp>/instructions.md] \
  [--effort <mapped>] [--json-schema <schema>] [--max-turns <n>]
```

with `ANTHROPIC_BASE_URL=$HG_PROVIDER_URL`, `ANTHROPIC_API_KEY=$HG_PROVIDER_TOKEN`, telemetry/autoupdater/reporting
switched off, and every model-alias variable pinned to the request's model. The CLI's own `~/.claude/settings.json`
(deny list + hook) is seeded under `$HOME`, and Claude Code's `--tools` list is fixed to the eight above regardless
of the request.

## Request fields → where they go

| Request field | Where it goes |
|---|---|
| `input` (text) | the CLI's prompt on stdin |
| `instructions` | the appended system-prompt file (together with the operator settings block) |
| `model` | `--model` (the harness default `deepseek-v4-pro` when the request names none) |
| `reasoning.effort` | `--effort` (`minimal`/`low`→low, `medium`, `high`, `xhigh`, `max`; `none` turns thinking off) |
| `text.format` (`json_schema`) | `--json-schema` |
| `max_tool_calls` | `--max-turns` (Claude Code stops; reported `response.incomplete` with reason `max_messages`) |
| `metadata.campaign`, `metadata.platforms` | injected into the prompt ("Campaign slug: …", "Platforms to post on: …") |
| `input_file` / `input_image` | written into the working directory by `req.place_inputs()` and named in the prompt |
| `tools` | ignored — the fixed eight-tool list is always used |
| `mcp_servers` | supported generically by the run script, but this package declares **no MCP servers** |

**Ignored** (named in the terminal event's `metadata.hg_ignored_fields` when set): `tool_choice`,
`parallel_tool_calls`, `temperature`, `top_p`, `top_logprobs`, `max_output_tokens`, `truncation`, `include`,
`prompt_cache_key`, `service_tier`.

## Output mapping

The `Mapper` turns Claude Code's stream-json lines into Responses events; each raw CLI line is also kept in the
turn's log with the `claude-stream ` prefix, never in the events.

| Claude Code | Responses event |
|---|---|
| `system init` / `result` (`session_id`) | saved to `$HG_STATE/session` at once; `result` also carries usage |
| `stream_event` `content_block_delta` text | `response.output_text.delta` → `out.say` |
| `content_block_delta` thinking / a `thinking` block | `out.think` |
| `tool_use` `Bash` | `out.ran` (a `shell_call`); its `tool_result` → `shell_call_output` |
| `tool_use` `Write` / `Edit` / `MultiEdit` | `out.wrote` / `out.edited` (at the result) |
| `tool_use` `mcp__<server>__<tool>` | `out.called`; its result → `call.done` / `call.failed` |
| any other `tool_use` | `out.used`; its result → `call.done` / `call.failed` |
| `result` success | `response.completed` with usage and `metadata` (`claude_session_id`, `claude_num_turns`, `claude_version`) |
| `result` `error_max_turns` | `response.incomplete` (`max_messages`) |
| anything else / API error | `response.failed` (401/403→`authentication_error`, 429→`rate_limit_exceeded`, ≥500→`server_error`, else `provider_error`/`cli_error`) |

Exactly one terminal event, last.

## Continuity

Two paths, both required and both in place:

1. **Native resume.** The CLI's session id is saved to `req.state` the moment the `system init` event reports it
   (so a turn killed mid-way still saves it), and the next turn resumes with `--resume <id>`. The CLI's own session
   store lives under `$HOME/.claude/projects`, named in `harness.json`'s `persist`.
2. **History fallback.** When there is no saved id, or the CLI refuses it ("No conversation found"), `run` starts a
   fresh CLI session and prepends `req.transcript()` (`$HG_HISTORY`) to the prompt, so a continuation from another
   harness — or a lost session — still has the whole conversation.

## Operator settings

Named like environment variables (injected by the platform), with defaults; **no secrets**.

| Setting | Default | What it does |
|---|---|---|
| `BRAND_VOICE` | A friendly, plain-spoken B2B software company. It never boasts, never invents numbers, never disparages competitors or people. | the voice every draft is written in, and what it never says |
| `HASHTAG_MAX` | `5` | the most hashtags allowed on any one post |
| `TIMEZONE` | `America/Chicago` | IANA timezone used to render relative times as ISO 8601 date-times in `plan.json` |

## Egress

- **install** — `registry.npmjs.org` (observed; the npm registry is all the install touches).
- **run** — `*` (the public web, read-only; private addresses are refused by the door regardless), with denials for
  the six social API hosts: `api.twitter.com`, `api.x.com`, `graph.facebook.com`, `api.linkedin.com`,
  `api.threads.net`, `bsky.social`.

`run.egress` is `*` because the agent reads whatever public URL a campaign points at — it cannot be enumerated in
advance. The six hosts the agent must never call are denied at the door; a Mastodon instance's `/api/` cannot be
denied by host (any instance's host is possible), so the PreToolUse hook refuses any URL whose path starts with
`/api/`. This is the same rule the agent honors in intent via its instructions.

## May and may not (as demonstrated)

**May** (all live-validated): read a public URL with WebFetch or `curl -sL`; search the web; write
`plan.json`, the `<platform>.md` files and `strategy.md` under `/workspace/campaigns/<slug>/`; resume its own
session; continue from history.

**May not** (each refused in a recorded run or a guard unit test):

| Action | Enforced by |
|---|---|
| POST / PUT / PATCH / DELETE anything (`curl -X/-d/--data/-F/-T`, `wget --post-*`, `http`, inline `requests`/`httpx`/`aiohttp`, `fetch` method) | PreToolUse guard (Bash) |
| call `api.twitter.com`, `api.x.com`, `graph.facebook.com`, `api.linkedin.com`, `api.threads.net`, `bsky.social` | egress denial + PreToolUse guard (Bash and WebFetch) |
| call any Mastodon instance's `/api/` | PreToolUse guard (Bash and WebFetch) |
| write/edit outside the workspace | PreToolUse guard (Write/Edit/MultiEdit) |
| git push / pull / fetch / remote / clone | `permissions.deny` |
| install software at runtime (npm/yarn/pip/apt/snap/yum/dnf/cargo/go/gem) | `permissions.deny` |

The guard fails closed: any guard error denies the call with the reason in the message. `--tools` further limits the
agent to the eight named tools.

## Tests

`tests/fixtures/*.jsonl` are recorded Claude Code stream-json runs: a completed tool turn, a denied POST, a denied
git push, a provider error, and a stopped-short (`max_turns`) turn. `tests/fake_claude` is a fake `claude` on `PATH`
that logs its argv/stdin and replays the fixture. `tests/test_run.py` runs `run` against each fixture and checks the
whole stdout with `hgkit.check` (the platform's own validator), plus unit-tests the PreToolUse guard directly, and
asserts the session is saved then resumed, history continues when there is no session, campaign metadata reaches the
prompt, and no secret placeholder appears in the output.

```
PYTHONPATH=/opt/hg/lib python3 -m pytest tests/ -q     # 12 passed
```

Every recorded run also passes `python3 -m hgkit check`.

## What could not be tried here

`run.egress` could not be narrowed to an observed host list: `assets/observe-egress.py` returned 407 proxy-auth
errors through the local chaining proxy, so the run egress is `*` narrowed by the six host denials and the hook,
rather than an enumerated list (the install host was confirmed directly). A turn the app actually runs is the real
e2e test; the session page will show any host the door denies, to bring back here.
