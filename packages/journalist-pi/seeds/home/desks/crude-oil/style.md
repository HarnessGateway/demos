# Crude-oil desk — style

## Voice

- Market-desk prose, dry and specific: lead with the biggest move in the WPSR.
- Always state direction and size against a frame: week-over-week, four-week average, year-over-year.
- Distinguish commercial crude from the SPR; never lump them.

## Numbers

- Every number carries a source URL in parentheses right after it, or in a trailing citation line.
- Give units exactly as EIA does (million barrels, thousand barrels/day, percent utilization).
- If the source does not state something you need, write "not in the published data" — never estimate.

## Files

- Slugs are kebab-case from the assignment, e.g. `cushing-draw-9m`.
- Deliver under `/workspace/desk/<YYYY-MM-DD>/crude-oil-<slug>/`.

## Charts (only when numbers warrant)

- A data-release or market-wrap with a meaningful series (stocks, Cushing, production) gets a chart.
- One chart answers one question. Title states the fact; a source line and units appear under the plot.
- Simple line or bar in matplotlib; label both axes; no 3-D, no pie charts.
- Save as `draft-<slug>-chart.png` next to `draft.md`.

## Draft ending

Every draft ends with `## Claims to verify` and the `Claim | Source | Status | Note` table; `Status` is
`verified` only when you saw the number on the cited page, otherwise `unverified`.
