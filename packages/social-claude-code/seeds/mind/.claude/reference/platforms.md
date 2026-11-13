# Platform idioms and limits

One engagement draft per platform, in that platform's own idiom. Lengths count characters, not words; hashtags
count toward the limit. The hard limits are repeated in `~/.claude/CLAUDE.md`; this file has the conventions.

## X (x.md)

- 280 characters per post. When one post cannot hold the idea, a thread: the first post is the hook and the one
  idea; each following post is one beat; end with a call to action or the link. Number the posts in `notes`, not
  in the published text.
- Idiom: short, plain, specific. Lead with the hook. A link counts ~23 characters (t.co). One or two hashtags,
  never a hashtag wall.

## LinkedIn (linkedin.md)

- 1,300 characters at most; the first two lines carry it — they are all that shows before "…see more", so put the
  hook and the one idea there.
- Idiom: professional, first-person plural (or a named author's voice), one clear idea, short paragraphs with
  line breaks, a question or call to action at the end. No more than three hashtags, at the end.

## Instagram (instagram.md)

- A caption with a hook in the first line, line breaks, and hashtags at the end (after a blank line); plus alt
  text for the image the post suggests — a concrete description of the suggested visual, not the caption repeated.
- Idiom: visual-first; the caption sets the scene; the hook is the first line before the fold. At most
  `HASHTAG_MAX` hashtags.
- The suggested image goes in `alt_text`; `notes` says what image to source or shoot.

## Threads (threads.md)

- Short, conversational, threaded. One thought per post; the first post is the hook. No hard limit, but keep each
  post tight; the thread is the point.

## Bluesky (bluesky.md)

- 300 characters. Idiom: casual, direct, community-minded; a single idea; the link in the post; one or two
  camel-cased hashtags.

## Mastodon (mastodon.md)

- 500 characters. Idiom: earnest, no growth-hacking; hashtags camel-cased, up to `HASHTAG_MAX`, at the end; add a
  content warning (CW) when the subject is sensitive; describe any image in the post itself or as alt text.

## Facebook (facebook.md)

- No formal limit; keep it under ~600 characters. Idiom: warmer and more narrative than X; the hook in the first
  sentence; the link preview carries the image; one or two hashtags.

## Voice (all platforms)

- Write in `BRAND_VOICE` (the operator setting; default: a friendly, plain-spoken B2B software company that never
  boasts, never invents numbers, never disparages competitors or people).
- One idea per post. The hook is in the first line. No clickbait. Every number, date, name and claim comes from
  the source. No emoji-only lines. Hashtags lowercase-camel-cased (e.g. `#socialMediaManager`), at most
  `HASHTAG_MAX`.

## The cross-posting plan (strategy.md and plan.json)

- Sequence: pick a leader (usually LinkedIn for B2B, X or Threads for consumer) that posts first; followers post a
  beat later the same day or the next morning, each linking back to the canonical URL with its own UTM parameters
  and cross-linking to the leader's post, so engagement on one platform feeds the others.
- Every post's `link` is the canonical URL with `utm_source=<platform>&utm_medium=social&utm_campaign=<slug>`.
- `cross_links` on each post names the other platforms' posts (by platform and their `link`), so the LinkedIn post
  points at the X thread and vice versa.
- `strategy.md`: why this sequence (the leader and the beat), what to watch in the first days (which post earns
  the engagement, which platform drives the clicks), and how to reply to comments (in voice, on-message, one idea,
  no new claims).
