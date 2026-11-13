# social-claude-code

A social media manager, on Claude Code. It is the agent inside the [Social Studio](../../social/).

- **Each turn** the studio sends a campaign: a page to read or pasted text, the goal, the audience, the brand's
  voice, the platforms, and the campaign's slug.
- **It writes** a post per platform in that platform's idiom and limits, a plan for the order and timing, and
  the links between them, into `campaigns/<slug>/` in its work folder: `plan.json`, one file per platform, and
  `strategy.md`.
- **It answers** in prose and ends with one fenced `social-plan` block holding the plan, which the studio parses.
- **It reaches** what its environment allows. The demo runs it in an environment named `web`: the public web,
  with the social platforms' APIs refused. It drafts; it never posts.
- **Settings:** `BRAND_VOICE`, `HASHTAG_MAX`, `TIMEZONE`.
- **Provider API:** Anthropic Messages.

`install` and `run` are the `claude-code` package's, unchanged. What makes it the social media manager is
[`seeds/mind/.claude/CLAUDE.md`](seeds/mind/.claude/CLAUDE.md) and the reference on each platform beside it.
