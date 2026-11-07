# The requests the packages were built from

Each package here is what the platform's built-in `harness-package-builder` wrote from one request, sent as a turn on
the organization's DeepSeek provider over the Anthropic API shape (`harness-package-builder/deepseek-anthropic/deepseek-v4-pro`),
imported from that session's workspace and installed. The builder's guide asks a tailored request to answer its questions
up front, so each does.

Each request asks for **one package**: the CLI, headless in the sandbox, with the organization's layer on it (standing
instructions, permission rules, hooks, settings, the output contract the app parses). There is no separate "vanilla"
package of the CLI beside it; the tailored package installs the CLI itself.

## sales-codex

```
Create a harness package named sales-codex: a small business's sales agent on Codex (OpenAI's Codex CLI, @openai/codex, the latest stable version), embedded in a CRM. The answers to your questions, so build it without a round of questions:

1. Purpose and typical request: the agent is the assistant inside a small business's CRM (a home-improvement showroom with a few hundred customers, but the CRM decides that; the agent reads what it is given). Every request carries the CRM's whole state as a file, so the agent reasons over the actual customer base: who is overdue for a follow-up, which proposals are stalling, who lives near the store, what the pipeline is worth by stage, which won customers to ask for referrals, what to say to each of them. Typical questions: "Who should I call today and why?", "Draft a follow-up email to everyone in Proposal older than two weeks", "Which leads from Google Ads converted?", "Text the three customers nearest the store about Saturday's open house". It answers in prose (short, concrete, names and numbers from the data, no invented facts) and, when the answer involves reaching customers, it proposes drafts the CRM stores in an outbox for a person to review and send. It never sends anything, never writes to the CRM and never changes a record: the drafts block is the only machine-readable thing it produces.
2. Who calls it and in what shape: the CRM's backend over the Responses API. Each request's input is one user message with two parts: an input_text (a short briefing from the CRM: today's date and time, the store's name and address, the user's question) and an input_file named customers.json (the CRM's snapshot: {"generated_at", "store": {name, address, lat, lon}, "stages": [...], "customers": [{id, name, company, email, phone, address, lat, lon, miles_from_store, stage, value, source, tags, next_follow_up, notes, created_at, updated_at, activities: [{kind, body, created_at}]}]}). A follow-up question comes with previous_response_id, so the session continues and the file may be sent again with fresh data. The agent must find the file where the platform puts a turn's input files and read it; it may use python3 to filter, sort, sum and compute (distances are precomputed as miles_from_store). Drafts go in ONE fenced block tagged crm-drafts at the end of the answer, holding a JSON array of {"contact_id": <id from the file>, "channel": "email" | "sms", "subject": "<email only>", "body": "<the message, plain text, ready to send, signed by the store>"}; no block when there is nothing to send. SMS bodies stay under 300 characters. Put this contract in the agent's standing instructions so the CRM does not have to repeat it.
3. CLI: Codex. The organization's provider for it is named deepseek-openai, OpenAI-compatible, reached at the base URL the platform hands the sandbox (HG_PROVIDER_URL, the door's relay) with the turn token (HG_PROVIDER_TOKEN) as the API key; the model is HG_MODEL. The relay serves /v1/responses, so configure Codex with a custom model_provider at that base URL, the key from an environment variable and wire_api = "responses"; verify in Codex's current documentation and release notes which wire_api values this version accepts. You cannot try Codex live in this sandbox (this session's provider is the Anthropic shape), so record in the README how to verify after install, and test the run script against a fake Codex that replays recorded JSONL.
4. Reach: nothing at run time but the model through the platform: run.egress is empty. Install needs the npm registry only.
5. Never: write outside /workspace, run any git remote operation, install software at run time, run anything destructive, contact anything on the network. Codex must run non-interactively, with its own sandbox and approval policy set so it never waits for a person, and with a hook or wrapper that refuses the forbidden commands.
6. Model: the session's HG_MODEL as the default.
7. Operator settings: STORE_PROFILE (a short text: what the business sells and how it talks to customers; default: a family-owned home-improvement showroom selling kitchen and bath remodels, flooring, cabinets and countertops; warm, plain-spoken, no pressure) and SIGNATURE (how messages are signed; default: "— The Showroom team"). No secrets.
8. Time: run.timeout_s 600.

Validate with the platform's check, record fixtures where you can, write the README.
```

## journalist-pi

```
Create a harness package named journalist-pi: a commodities-market journalist agent on pi (the pi coding agent CLI, @mariozechner/pi-coding-agent, the latest stable version), for a newsroom's market-desk app. The answers to your questions, so build it without a round of questions:

1. Purpose and typical request: given a desk (biofuels or crude-oil) and an assignment, the agent gathers intel from the desk's primary sources, forms impressions (what moved, why it matters, what to watch) and authors a cited report. It writes /workspace/desk/<YYYY-MM-DD>/<desk>-<slug>/draft.md (the story), sources.json (a list of {id, title, url, used_for} for every source used), verify.md (a markdown table of the claims a person must verify: Claim | Source | Status | Note) and PNG charts with matplotlib when numbers warrant them. It cites every number to a source URL, invents no quotes, prices or figures, and never publishes. Task kinds: briefing, data-release, market-wrap, explainer, news-short, research (a research question answered in prose plus the same folder). It ends every answer with ONE fenced block tagged desk-report holding JSON: {"folder": "<the folder it wrote, relative to /workspace>", "headline": "...", "summary": "<two sentences>", "files": ["draft.md", "sources.json", "verify.md", "<chart>.png", ...]} so the app knows what to fetch; put this contract in pi's standing instructions.
2. Who calls it: the desk app's backend over the Responses API; the request's metadata.desk names the desk and metadata.task the task kind; the input is the assignment, sometimes with a previous_response_id for a revision ("shorten the lede", "add the Cushing number"). Prose plus the files.
3. CLI: pi, on this session's provider (the Anthropic shape through the platform, model HG_MODEL). Try it live here with a real assignment on each desk.
4. Reach: only the primary sources: www.eia.gov, api.eia.gov, www.epa.gov, ww2.arb.ca.gov, www.federalregister.gov, www.ams.usda.gov, www.ers.usda.gov (run.egress), plus whatever install needs for pi, pandas and matplotlib (install.egress, as observed). No MCP servers.
5. Never: reach any other host, write outside /workspace, run anything but python3 and standard Unix tools, modify the desk packs, publish or send anything.
6. Model: HG_MODEL as the default.
7. Operator settings: DESK (default biofuels), overridden by metadata.desk. No secrets.
8. Time: run.timeout_s 1200.

Seeds: the desk packs under $HOME/desks/<desk>/ with glossary.md, sources.md, style.md and calendar.md for biofuels (RINs, LCFS credits, SAF, renewable diesel, ethanol, feedstocks; EIA weekly ethanol data) and crude-oil (EIA Weekly Petroleum Status Report: stocks, Cushing, production, refinery runs), plus pi's standing instructions with the newsroom rules (source every number, invent nothing, draft only, end every draft with the claims to verify, end every answer with the desk-report block). Validate with the platform's check, record fixtures, write the README.
```

## social-claude-code

```
Create a harness package named social-claude-code: a social media manager agent on Claude Code (@anthropic-ai/claude-code, the latest stable version), for a social media management app. The answers to your questions, so build it without a round of questions:

1. Purpose and typical request: given a campaign (a piece of content to promote: a URL to read, or pasted text; the goal; the audience; the brand's voice; the platforms to post on), the agent reads the source, then writes an engagement draft for each platform in that platform's own idiom and limits: X (280 characters, a thread when the content warrants it), LinkedIn (a professional post, 1,300 characters at most, the first two lines carry it), Instagram (a caption with a hook, line breaks and hashtags at the end, plus alt text for the image it suggests), Threads, Bluesky (300 characters), Mastodon (500 characters), and a Facebook post. It plans the cross-posting: a sequence and timing over the first days (which platform leads, which follow, which re-share the thread), backlinks from every post to the canonical URL with UTM parameters per platform (utm_source=<platform>&utm_medium=social&utm_campaign=<slug>), and cross-links between the posts (the LinkedIn post points at the X thread, and so on), so engagement on one platform feeds the others. It writes /workspace/campaigns/<slug>/plan.json ({slug, canonical_url, posts: [{platform, when (an ISO 8601 date-time or a relative "day 1 09:00"), text, hashtags, link, alt_text, cross_links, notes}]}), one markdown file per platform (/workspace/campaigns/<slug>/<platform>.md with the post as it would be published), and a short strategy.md (why this sequence, what to watch, how to reply to comments). A follow-up request (with previous_response_id) may revise one platform's draft with a note, or ask for variants (three hooks for the X thread); then it rewrites plan.json. It answers in prose with a summary and ends every answer with ONE fenced block tagged social-plan holding the same JSON as plan.json, so the app can read it without fetching the file; put this contract in the agent's standing instructions. It never posts anywhere: a person approves each draft in the app, which schedules it.
2. Who calls it: the app's backend over the Responses API, one session per campaign; metadata.campaign names the campaign slug and metadata.platforms lists the platforms. Prose plus the files.
3. CLI: Claude Code, on this session's provider (the Anthropic shape through the platform, model HG_MODEL). Try it live here on a real public article.
4. Reach: the public web, read-only, to read the source URL and the linked pages (run.egress: the web, no private hosts). No MCP servers.
5. Never: post or call any social platform's API, send anything, write outside /workspace, run git remote operations, install software at run time. Express these in Claude Code's own permission rules (a deny list) and a PreToolUse hook that refuses Bash commands that POST, or that name api.twitter.com, api.x.com, graph.facebook.com, api.linkedin.com, api.threads.net, bsky.social, or any Mastodon instance's /api/.
6. Model: HG_MODEL as the default.
7. Operator settings: BRAND_VOICE (a short text an operator sets: the brand's voice and what it never says; default: a friendly, plain-spoken B2B software company), HASHTAG_MAX (the most hashtags per post; default 5), TIMEZONE (for the schedule; default America/Chicago). No secrets.
8. Time: run.timeout_s 900.

Seeds: Claude Code's standing instructions with the social manager's method (read the source fully before writing, one idea per post, the hook in the first line, no clickbait, every number from the source, accessibility: alt text and no emoji-only lines, hashtags lowercase-camel-cased for screen readers, end every answer with the social-plan block), platform limits and conventions as a reference file, and the permission rules and hook above. Validate with the platform's check, record fixtures, write the README.
```

