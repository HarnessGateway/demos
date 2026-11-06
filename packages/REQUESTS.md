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
