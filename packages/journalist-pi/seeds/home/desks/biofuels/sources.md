# Biofuels desk — primary sources

Only these hosts, only over https. Fetch the exact page you need; do not crawl or follow links off these hosts.

## EIA — the volume numbers

- `https://www.eia.gov/petroleum/supply/weekly/` — **Weekly Petroleum Status Report (WPSR)**. Weekly U.S. fuel
  ethanol production (thousand barrels/day), ethanol ending stocks (million barrels), and the crude-side tables. The
  desk's weekly production number comes from here.
- `https://www.eia.gov/petroleum/ethanol/` — fuel ethanol landing page and weekly ethanol data.
- `https://www.eia.gov/todayinenergy/` — EIA's analysts on anything fuel-related.

## EIA API

- `https://api.eia.gov/` — the EIA API (v2). Prefer it for a clean series when a page is awkward to parse; the desk
  uses the series behind WPSR ethanol production and stocks. (Callers that give an API key pass it through the
  assignment; the desk pack itself holds none.)

## EPA — RINs and the RFS

- `https://www.epa.gov/renewable-fuel-standard-program` — the RFS: annual RVO rulemakings, proposals, final rules.
- `https://www.epa.gov/fuels-registration-reporting-and-compliance-help/rin-trades-and-price-information` — RIN
  trade volume and price information EPA publishes.
- `https://www.epa.gov/fuels-registration-reporting-and-compliance-help/emts-overview` — EMTS, the RIN generation
  and transaction system; monthly RIN generation numbers.

## CARB — LCFS

- `https://ww2.arb.ca.gov/our-work/programs/low-carbon-fuel-standard` — the LCFS program: benchmarks, CI pathways,
  amendments.
- `https://ww2.arb.ca.gov/resources/documents/lcfs-credit-transfer-activity-reports` — **weekly LCFS credit
  transfer activity reports**: credit price ($/metric ton) and volume transferred. The desk's weekly LCFS price.

## Federal Register

- `https://www.federalregister.gov/` — search `renewable fuel standard`, `renewable volume obligation`, `low carbon
  fuel standard`. The authoritative text of EPA RVO rules and CARB-related federal actions.

## USDA — feedstocks and spot ethanol

- `https://www.ams.usda.gov/market-news/bioenergy` — AMS bioenergy market news: national weekly ethanol spot prices
  and feedstock (soybean oil, distillers' corn oil) prices.
- `https://www.ers.usda.gov/topics/crops/soybeans-and-oil-crops/` — ERS oil crops: soybean oil supply, use, and
  price. The desk's feedstock supply-side read.
- `https://www.ers.usda.gov/topics/crops/corn-and-other-feed-grains/` — ERS feed grains: corn supply, use, and
  price.
