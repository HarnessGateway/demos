# Crude-oil desk — primary sources

Only these hosts, only over https. Fetch the exact page you need; do not crawl or follow links off these hosts.

## EIA — the WPSR

- `https://www.eia.gov/petroleum/supply/weekly/` — **Weekly Petroleum Status Report (WPSR)**. The desk's release:
  U.S. commercial crude stocks, **Cushing (Oklahoma) stocks**, U.S. crude oil production, refinery runs/inputs and
  utilization, crude imports, and gasoline/distillate inventories. Tables and a data file.
- `https://www.eia.gov/petroleum/weekly/` — **This Week in Petroleum**: EIA's own analysis of the latest WPSR and the
  market.
- `https://www.eia.gov/outlooks/steo/` — Short-Term Energy Outlook: monthly EIA price and balance projections.
- `https://www.eia.gov/todayinenergy/` — EIA's analysts on anything petroleum.

## EIA API

- `https://api.eia.gov/` — the EIA API (v2). Prefer it for a clean WPSR series (Cushing stocks, crude production,
  refinery runs) when a page is awkward to parse. (Callers that give an API key pass it through the assignment; the
  desk pack itself holds none.)

## EPA — fuels regulation

- `https://www.epa.gov/fuels-registration-reporting-and-compliance-help` — fuels compliance programs (RFS, fuels
  waivers) that affect refinery economics and product balances.

## CARB — state fuel rules

- `https://ww2.arb.ca.gov/our-work/programs/low-carbon-fuel-standard` — the LCFS, which shapes West Coast crude and
  product demand.

## Federal Register

- `https://www.federalregister.gov/` — search `petroleum`, `strategic petroleum reserve`, `fuels regulatory`. The
  authoritative text of federal petroleum and fuels rulemaking.

## USDA — the demand side

- `https://www.ers.usda.gov/topics/crops/soybeans-and-oil-crops/` and
  `https://www.ers.usda.gov/topics/crops/corn-and-other-feed-grains/` — the biofuel and feedstock demand that pulls on
  crude/product balances at the margin (used sparingly; the WPSR is the desk's primary).
