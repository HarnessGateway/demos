# The requests the packages were built from

Each was typed into the console's chat with the built-in `harness-package-builder` selected (on the organization's
DeepSeek provider), as a person would. The builder's own guide asks a tailored request to answer its questions up front,
so each does. The packages in this folder are what it wrote, imported from its session's workspace and installed.

## sales-codex

```
Create a harness package named sales-codex: an organization's sales agent on Codex (OpenAI's Codex CLI, @openai/codex, the latest stable version), for a CRM. The answers to your questions, so build it without a round of questions:

1. Purpose and typical request: the agent works for an account executive inside a CRM. A request is one task in plain language plus the account record as JSON in the input (company, website, contacts, open deals, recent notes). Typical tasks: research the company on the public web and write an account brief; draft an outreach email or a follow-up for a contact; prepare a call plan with questions and likely objections; summarize a thread of notes; propose next steps for a deal. It keeps its work as files in the workspace, one folder per account: /workspace/accounts/<slug>/brief.md, outreach/<YYYY-MM-DD>-<topic>.md, call-prep.md, next-steps.md, and it answers in prose too. It never sends anything and never writes to the CRM: the CRM does that after a person approves.
2. Who calls it and in what shape: the CRM's backend over the Responses API, one session per account, prose plus the files. No JSON output format needed.
3. CLI: Codex. The organization's provider for it is named deepseek-openai, OpenAI-compatible, reached at the base URL the platform hands the sandbox (HG_PROVIDER_URL, the door's relay to the gateway) with the turn token (HG_PROVIDER_TOKEN) as the API key; the model is HG_MODEL. The gateway relays both /v1/chat/completions and /v1/responses; configure Codex with a custom model_provider at that base URL, the key from an environment variable, and wire_api = "chat" (DeepSeek-style OpenAI compatibility), unless your research shows this endpoint supports the Responses API. You cannot try it live in this sandbox (this session's provider is the Anthropic shape), so record how to verify it after install.
4. Reach: the public web for research, read-only (GETs), nothing private. No repositories, no internal services, no MCP servers.
5. Never: write outside /workspace, run git push or any git remote operation, install software at run time, run anything destructive. Codex must run non-interactively with its own sandbox and approval policy set so that it never waits for a person.
6. Model: the session's HG_MODEL as the default.
7. Operator settings: SALES_PLAYBOOK (a short text: the company's products, pitch and tone; default: a generic B2B software vendor selling to mid-market operations teams) and REGION (default US). No secrets.
8. Time: run.timeout_s 900.

Deliver the vanilla codex base beside it as its own package. Validate both with the platform's check, record fixtures where you can, and write the READMEs.
```

## journalist-pi

```
Create a harness package named journalist-pi: a commodities-market journalist agent on pi (the pi coding agent CLI, @mariozechner/pi-coding-agent, the latest stable version), for a newsroom market-desk app. The answers to your questions, so build it without a round of questions:

1. Purpose and typical request: given a desk (biofuels or crude-oil) and an assignment, the agent gathers intel from the desk's primary sources, forms impressions (what moved, why it matters, what to watch) and authors a cited report. It writes /workspace/desk/<YYYY-MM-DD>/<desk>-<slug>/draft.md (the story), sources.json (a list of {id, title, url, used_for} for every source used), verify.md (a markdown table of the claims a human must verify: Claim | Source | Status | Note) and PNG charts with matplotlib when numbers warrant them. It cites every number to a source URL, invents no quotes, prices or figures, and never publishes. Task kinds: briefing, data-release, market-wrap, explainer, news-short, research (a research question answered in prose plus the same folder).
2. Who calls it: the desk app's backend over the Responses API; the request's metadata.desk names the desk and metadata.task the task kind; the input is the assignment. Prose plus the files.
3. CLI: pi, on this session's provider (the Anthropic shape through the platform, model HG_MODEL). Try it live here.
4. Reach: only the primary sources: www.eia.gov, www.epa.gov, ww2.arb.ca.gov, www.federalregister.gov, www.ams.usda.gov, www.ers.usda.gov (run.egress), plus whatever install needs for pi, pandas and matplotlib (install.egress, as observed). No MCP servers.
5. Never: reach any other host, write outside /workspace, run anything but python3 and standard Unix tools, modify the desk packs.
6. Model: HG_MODEL as the default.
7. Operator settings: DESK (default biofuels), overridden by metadata.desk. No secrets.
8. Time: run.timeout_s 1200.

Seeds: the desk packs under $HOME/desks/<desk>/ with glossary.md, sources.md, style.md and calendar.md for biofuels (RINs, LCFS credits, SAF, renewable diesel, ethanol, feedstocks; EIA weekly ethanol data) and crude-oil (EIA Weekly Petroleum Status Report: stocks, Cushing, production, refinery runs), plus pi's standing instructions with the newsroom rules (source every number, invent nothing, draft only, end every draft with the claims to verify). Deliver the vanilla pi base beside it as its own package. Validate both with the platform's check, record fixtures, write the READMEs.
```

## social-claude-code

```
Create a harness package named social-claude-code: a social media manager agent on Claude Code (@anthropic-ai/claude-code, the latest stable version), for a social media management app. The answers to your questions, so build it without a round of questions:

1. Purpose and typical request: given a campaign (a piece of content to promote: a URL to read, or pasted text; the goal; the audience; the brand's voice; the platforms to post on), the agent reads the source, then writes an engagement draft for each platform in that platform's own idiom and limits: X (280 characters, a thread when the content warrants it), LinkedIn (a professional post, 1,300 characters at most, the first two lines carry it), Instagram (a caption with a hook, line breaks and hashtags at the end, plus alt text for the image it suggests), Threads, Bluesky (300 characters), Mastodon (500 characters), and a Facebook post. It plans the cross-posting: a sequence and timing over the first days (which platform leads, which follow, which re-share the thread), backlinks from every post to the canonical URL with UTM parameters per platform (utm_source=<platform>&utm_medium=social&utm_campaign=<slug>), and cross-links between the posts (the LinkedIn post points at the X thread, and so on), so engagement on one platform feeds the others. It writes /workspace/campaigns/<slug>/plan.json ({slug, canonical_url, posts: [{platform, when (an ISO 8601 date-time or a relative "day 1 09:00"), text, hashtags, link, alt_text, cross_links, notes}]}), one markdown file per platform (/workspace/campaigns/<slug>/<platform>.md with the post as it would be published), and a short strategy.md (why this sequence, what to watch, how to reply to comments). A follow-up request may revise one platform's draft with a note, or ask for variants (three hooks for the X thread). It answers in prose with a summary. It never posts anywhere: a person approves each draft in the app, which schedules it.
2. Who calls it: the app's backend over the Responses API, one session per campaign; metadata.campaign names the campaign slug and metadata.platforms lists the platforms. Prose plus the files; plan.json is the machine-readable part the app reads.
3. CLI: Claude Code, on this session's provider (the Anthropic shape through the platform, model HG_MODEL). Try it live here on a real public article.
4. Reach: the public web, read-only, to read the source URL and the linked pages (run.egress: the web, no private hosts). No MCP servers.
5. Never: post or call any social platform's API, send anything, write outside /workspace, run git remote operations, install software at run time. Express these in Claude Code's own permission rules (a deny list) and a PreToolUse hook that refuses Bash commands that POST, or that name api.twitter.com, api.x.com, graph.facebook.com, api.linkedin.com, api.threads.net, bsky.social, or any Mastodon instance's /api/.
6. Model: HG_MODEL as the default.
7. Operator settings: BRAND_VOICE (a short text an operator sets: the brand's voice and what it never says; default: a friendly, plain-spoken B2B software company), HASHTAG_MAX (the most hashtags per post; default 5), TIMEZONE (for the schedule; default America/Chicago). No secrets.
8. Time: run.timeout_s 900.

Seeds: Claude Code's standing instructions with the social manager's method (read the source fully before writing, one idea per post, the hook in the first line, no clickbait, every number from the source, accessibility: alt text and no emoji-only lines, hashtags lowercase-camel-cased for screen readers), platform limits and conventions as a reference file, and the permission rules and hook above. Deliver the vanilla claude-code base beside it as its own package. Validate both with the platform's check, record fixtures, write the READMEs.
```
