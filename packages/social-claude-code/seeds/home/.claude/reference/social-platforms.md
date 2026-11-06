# Platform limits and conventions

Read before drafting. Numbers here are the limits to respect; the idioms are how each platform is written. When a
platform's limit differs by surface (bio, media caption), use the post-body limit. The operator's `$HASHTAG_MAX`
(default 5) caps hashtags everywhere; the table says where hashtags are native.

| Platform | Post limit | Idiom and conventions | Hashtags |
|---|---|---|---|
| X | 280 characters | The post is the hook: one sharp sentence, then the link. When the content warrants it, write a **thread** (each post ≤280, numbered or threaded, the first post is the hook). URLs are wrapped by the client; the `link` field carries the UTM URL. | yes |
| LinkedIn | 1,300 characters | Professional, plain, first-person-plural or neutral. **The first two lines carry it** — they are what shows before "…see more". One idea, a short body, a closing question or call to read. | yes, sparingly (3–5) |
| Instagram | caption 2,200 characters (plan for ~125–150 visible before "…more") | Caption opens with a hook, then line breaks for pacing, then hashtags at the end. Suggest an **image** and give its **alt text**. The link goes in the bio/Link in bio, so `link` is the UTM URL to reference, not a tappable in-caption URL. | yes (hashtags at the end) |
| Threads | 500 characters | Conversational, warm, lower-friction than X. No native UTM-hostile URL handling — put the UTM URL in the text. | yes |
| Bluesky | 300 characters | Plain text, no emoji walls, one idea, the link at the end. | no (mention-like tags instead) |
| Mastodon | 500 characters | Community norms: summarize the source, credit it, use **content warnings** when the subject calls for one. Instance culture matters; stay generic and polite. | yes |
| Facebook | 63,206 characters (write ~150–300) | Friendly, slightly longer than X, a clear headline line then two or three sentences. | no |

## Cross-posting rules

- **Backlinks:** every post links to the canonical URL with
  `?utm_source=<platform>&utm_medium=social&utm_campaign=<slug>` (platform in lowercase, e.g. `linkedin`, `bluesky`).
- **Cross-links:** posts point at each other — the LinkedIn post points at the X thread, and so on — so engagement on
  one platform feeds the others. Record the URL of each referenced post in `cross_links`.
- **Sequence:** plan which platform leads and which follow over the first days; re-sharing a thread on a slower
  platform is fine and should be noted.

## Accessibility and voice

- Alt text for every suggested image (Instagram requires it); describe the image's meaning, not "image of".
- No emoji-only lines; never use emoji in place of words. At most a couple of emoji per post, if the brand uses them.
- Hashtags are lowercase and camel-cased where words run together (`#BetterCoffee`), so screen readers read them.
- Every number, quote, price and date comes from the source. Do not invent.
- Stay in `$BRAND_VOICE`; never say what the brand never says.
