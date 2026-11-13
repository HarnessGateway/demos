# journalist-pi

A commodities-market journalist, on pi. It is the agent inside the [Market Desk](../../market-desk/).

- **Each turn** the desk sends an assignment that names the desk (biofuels or crude-oil) and the kind of task.
- **It reads** the desk's pack (`~/desks/<desk>/`: sources, glossary, style, calendar), then the desk's primary
  sources, and files into `desk/<date>/<desk>-<slug>/` in its work folder: `draft.md`, `sources.json`,
  `verify.md` (every claim, with its source and whether it was verified) and PNG charts.
- **It answers** in prose and ends with one fenced `desk-report` block naming the folder and its files, which the
  desk app reads back through the Containers API.
- **It reaches** its model and the hosts in `run.egress`: EIA, EPA, CARB, the Federal Register and USDA.
- **Provider API:** Anthropic Messages, OpenAI Responses or OpenAI Chat Completions, whichever the provider has.

`run` is the `pi` package's, unchanged; `install` is too, plus pandas and matplotlib at pinned versions under
`/harness/tools/charts`. What makes it the journalist is
[`seeds/mind/.pi/agent/AGENTS.md`](seeds/mind/.pi/agent/AGENTS.md) and the desk packs beside it.
