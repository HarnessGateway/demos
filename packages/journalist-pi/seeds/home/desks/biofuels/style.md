# Biofuels desk — style

## Voice

- Plain market-desk prose: short sentences, active verbs, no hype.
- Lead with the number that moved and its direction ("Ethanol production fell 3% to 1.02 million bbl/day…").
- Always give the unit and the comparison frame (week-over-week, four-week average, year-over-year).

## Numbers

- Every number carries a source URL in parentheses right after it, or in a trailing citation line.
- Round for readability but keep one decimal where the source gives it; never change a source's value.
- If the source does not state something you need, write "not in the published data" — never estimate.

## Files

- Slugs are kebab-case from the assignment, e.g. `ethanol-stocks-fall`.
- Deliver under `/workspace/desk/<YYYY-MM-DD>/biofuels-<slug>/`.

## Charts (only when numbers warrant)

- A data-release or market-wrap with a real series gets a chart; a briefing or news-short usually does not.
- One chart answers one question. Title states the fact; a source line and units appear under the plot.
- Prefer a simple line or bar in matplotlib; label both axes; no 3-D, no pie charts.
- Save as `draft-<slug>-chart.png` next to `draft.md`.

## Draft ending

Every draft ends with `## Claims to verify` and the `Claim | Source | Status | Note` table; `Status` is
`verified` only when you saw the number on the cited page, otherwise `unverified`.
