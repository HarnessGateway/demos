# social-claude-code

A harness package for a **social media manager agent** on Claude Code (`@anthropic-ai/claude-code`, pinned to
`2.1.318`). Given a campaign — a URL to read or pasted text, the goal, the audience, the brand's voice, and the
platforms — the agent reads the source fully, then writes engagement drafts in each platform's idiom and a
cross-posting plan. It never posts: a person approves each draft in the app, which schedules and publishes it.

This is a tailored copy of the `claude-code` package, delivered beside it. It adds the agent's standing instructions,
the platform reference, a permission deny list, a PreToolUse fence hook, operator settings, and a narrowed purpose.

## Purpose

One session per campaign. The request names a campaign (a URL to read, or pasted text), its goal, audience, brand
voice, and platforms; `metadata.campaign` is the slug and `metadata.platforms` the platform list. The agent:

1. Reads the source fully — WebFetch the URL and the pages it links to that matter — before drafting.
2. Writes drafts in each platform's idiom and limits: **X** (280 characters; a thread when warranted), **LinkedIn**
   (1,300 max, the first two lines carry it), **Instagram** (hook, line breaks, hashtags at the end, plus alt text for
   the image it suggests), **Threads**, **Bluesky** (300), **Mastodon** (500), **Facebook**.
3. Plans cross-posting: which platform leads, which follow and re-share over the first days; UTM backlinks
   `?utm_source=<platform>&utm_medium=social&utm_campaign=<slug>`; cross-links between posts.
4. Writes the machine-readable plan to `/workspace/campaigns/<slug>/plan.json`
   (`{slug, canonical_url, posts: [{platform, when, text, hashtags, link, alt_text, cross_links, notes}]}`), one
   `<platform>.md` per platform, and `strategy.md`.
5. Answers in prose with a summary; `plan.json` is what the app parses.

It never posts, never calls a social platform's API, never sends anything anywhere, and never writes outside
`/workspace`.

## Files

| File | Role |
|---|---|
| `harness.json` | manifest: version `2.1.318-1`, provider `anthropic`, `defaults.model` `deepseek-v4-pro`, install egress `registry.npmjs.org`, run egress `*` (public web, read-only; the door refuses private addresses), `persist` `[".claude/projects"]`, `run.timeout_s` 900, operator settings `BRAND_VOICE` / `HASHTAG_MAX` / `TIMEZONE` |
| `install` | `npm install -g --prefix "$HG_TOOLS" --allow-scripts=@anthropic-ai/claude-code @anthropic-ai/claude-code@<version>` |
| `run` | one turn (Python + hgkit): the same command and stream mapping as the `claude-code` base, plus `metadata` surfaced into the prompt |
| `seeds/home/.claude/CLAUDE.md` | the agent's method and standing rules: read the source fully, one idea per post, hook first line, every number from the source, accessibility (alt text, no emoji-only lines, camel-cased hashtags), cross-posting, and the "never" list |
| `seeds/home/.claude/reference/social-platforms.md` | each platform's limit, idiom and conventions (the drafting reference) |
| `seeds/home/.claude/settings.json` | the inside fence: permission `deny` rules for git remote operations, package managers, `curl`/`wget`, and every write outside `/workspace`; PreToolUse hook on `Bash`, `Write|Edit|MultiEdit` and `WebFetch` |
| `seeds/home/.claude/hooks/pre-tool-use.py` | the hook: refuses any POST/PUT/PATCH, any social-platform API host (`api.twitter.com`, `api.x.com`, `graph.facebook.com`, `api.linkedin.com`, `api.threads.net`, `bsky.social`), any `/api/` endpoint, and any write outside `/workspace` |
| `README.md`, `tests/` | this file; recorded fixtures, `test_run.py`, `test_hook.py` |

## The command

Identical to the `claude-code` base: `claude -p "<input>" --output-format stream-json --verbose
--include-partial-messages --system-prompt-snapshot off --dangerously-skip-permissions --model "$HG_MODEL"
[--append-system-prompt <instructions>] [--effort <level>] [--resume <id>]`, with `ANTHROPIC_BASE_URL`, the API key and
every model alias pinned to the turn's provider and model, and telemetry/update/error-reporting switched off. The
deny list and hook in `seeds/home/.claude` are what make the `--dangerously-skip-permissions` run safe; they are the
real fence, and the agent is told not to fight them.

## Request fields

As the `claude-code` base, plus:

| Request field | Where it goes |
|---|---|
| `metadata` (object) | appended to the prompt as `Request metadata: k=v; …` (lists comma-joined), so `metadata.campaign` and `metadata.platforms` reach the agent |

The same fields are ignored (`temperature`, `top_p`, `max_output_tokens`, `max_tool_calls`, `store: false`), named in
`metadata.hg_ignored_fields`.

## Output mapping

As the `claude-code` base: Claude Code `stream-json` → Responses events (thinking → reasoning, text → message,
`Bash` → `shell_call`/`shell_call_output`, `Write`/`Edit` → `apply_patch_call`, other tools → `function_call`, `result`
→ `response.completed`/`failed`/`incomplete`). Exactly one terminal event, last. The files the agent writes under
`/workspace/campaigns/<slug>/` are the deliverable; `plan.json` is the app's machine-readable part.

## Continuity

Two paths, as the base: the CLI's own session id (saved to `$HG_STATE` the moment the `init` line reports it,
`--resume <id>` next turn), and the history (`req.transcript()` as context when there is no saved id or the CLI
refuses it). A follow-up note — "revise the LinkedIn draft", "three hooks for the X thread" — lands on the same
session and is handled on the existing files, not started over.

## May and may not (as demonstrated)

| Capability | Proven by |
|---|---|
| May read the public web | run egress `*` (door refuses private addresses); the live campaign run WebFetched a real article |
| May run read-only shell commands and write only inside `/workspace` | `test_hook.py` (`bash-read-only`, `write-in-ws`, `multiedit-in-ws` allowed) |
| May write the campaign files under `/workspace/campaigns/<slug>/` | the live campaign run wrote `plan.json`, `<platform>.md` ×7, `strategy.md`; recorded as `tests/fixtures/realistic-run.jsonl` |
| May not POST/PUT/PATCH or upload | `test_hook.py` denies `curl -d`, `curl --request POST`, `requests.post`, `--upload-file`; the hook scans the command before it runs |
| May not reach a social platform's API | `test_hook.py` denies every `SOCIAL_HOSTS` host and any `/api/` URL, for `Bash` and `WebFetch` |
| May not write outside `/workspace` | `test_hook.py` denies `Write`/`Edit`/`MultiEdit` outside the workspace and shell redirects outside it; `settings.json` deny rules are the backstop |
| May not run git remote operations or install software | `settings.json` deny rules (`git push|fetch|pull|clone|remote`, `npm`, `npx`, `pip`, `apt`, `curl`, `wget`, …) |

The forbidden run is recorded: `tests/fixtures/forbidden-run.jsonl` is a mapped `run` output where the model tried to
reach a social API and the hook refused it, and `tests/fixtures/claude-forbidden.jsonl` is the raw `claude` stream
where the model refused outright without attempting the tool.

## Operator settings

| Setting | Default | Effect |
|---|---|---|
| `BRAND_VOICE` | `A friendly, plain-spoken B2B software company. Never hype, never jargon, never promise results the product cannot show.` | the voice every draft stays in |
| `HASHTAG_MAX` | `5` | the most hashtags per post |
| `TIMEZONE` | `America/Chicago` | the timezone for `when` in `plan.json` |

No secrets: the provider key is the platform's per-turn token; nothing here needs a key.

## Known limits

- The `claude-code` base limits apply (raw `--dangerously-skip-permissions`, run egress `*`, the unrecognized-model
  stderr warning).
- The fence is defense in depth, not proof: the hook reads the command text and the deny list matches command
  prefixes. A determined prompt-injection that finds a genuinely novel way to POST could still need the door; the
  egress door remains the outer fence.
- `run.timeout_s` is 900, matched to a full campaign (read the source, draft seven platforms, write nine files).

## Tests

- `python3 tests/test_run.py` — `run` against a stub `claude` replaying recorded fixtures (text, tools, provider
  error, killed turn, resume, history fallback, stale-resume fallback), every mapped line checked with `hgkit.check`.
- `python3 tests/test_hook.py` — the PreToolUse hook fed 15 events (benign reads/writes allowed; every forbidden
  POST, social host, `/api/` URL and outside-workspace write denied).

Recorded fixtures in `tests/fixtures/`: `realistic-run.jsonl` is the mapped, hgkit-checked output of a live campaign
run on a real public article (Wikipedia's "Coffee") — 89 events, 32 output items, ending `response.completed`;
`forbidden-run.jsonl` is the mapped run where the hook refused a POST to a social API; `claude-forbidden.jsonl` is
the raw `claude` stream where the model refused the same command outright.

On the platform: install the package and send a campaign turn; **Observability → Sessions** shows every mapped event,
the CLI's stderr tail, exit code, provider calls and door connections, and the campaign files land under
`/workspace/campaigns/<slug>/`.
