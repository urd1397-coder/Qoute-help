# BestQoute (v0.3)

A free web app that takes real, user-entered auto insurance quotes, checks every **legitimate savings lever** against the shopper's truthful profile, and shows how close they can get to a monthly target (default $200). It ends with a **buy-ready packet** the shopper takes to the insurer for the official quote.

It is not an automatic live-quote aggregator. Quotes are entered by the user or imported from CSV.

## What it does
- Ranks quotes by projected cost using the same coverage (fees included).
- **Lever engine:** discount stacking (bundle, multi-car, telematics, pay in full, autopay, paperless, good student, low mileage, defensive course, homeowner, group/employer, military, early shopper, claim-free, continuous coverage, safety features).
- Shows **coverage tradeoffs** (higher deductible, dropping collision on an old car, state options in PA, NJ, MI) as a separate scenario, never mixed into the same-coverage numbers.
- Lists **state programs** to check eligibility for (CA, NJ).
- **$200 tracker:** progress bar per quote and a plain verdict (under target, reachable, possible, tradeoffs only, or gap).
- **Comparability warnings** when limits, deductibles, vehicles or drivers don't match.
- **Buy-ready packet:** coverage to request, discounts to ask for by name, steps, and what to check before paying.
- API: `POST /api/compare`, `GET /api/levers`, `POST /api/import-csv`, `GET /api/health`.

## Run locally
Python 3.10+ recommended.

```bash
python -m venv .venv
# macOS/Linux:
source .venv/bin/activate
# Windows PowerShell:
# .venv\Scripts\Activate.ps1
pip install -r requirements.txt
uvicorn app.main:app --reload
```

Open http://127.0.0.1:8000

## Deploy on Render
1. Create a GitHub repository and upload all of these files (keep the `app/` folder structure).
2. In Render, choose **New + → Blueprint** and connect the repository.
3. Review the service, then deploy. Render reads `render.yaml`.
4. Open the service URL. Health check: `/api/health`.

Nothing is stored on the server, so restarts and spin-downs lose nothing.

### Keeping the free service awake
Render Free web services spin down after 15 minutes with no inbound traffic, and waking takes about a minute. To avoid that, point a free uptime monitor (for example UptimeRobot) at the health check:

- URL: `https://YOUR-SERVICE.onrender.com/api/health`
- Check interval: anything under 15 minutes (5 minutes is typical)

Notes:
- The app already runs continuously; no loop is needed. A manual infinite loop would block the server and waste hours.
- `render.yaml` sets uvicorn `--timeout-keep-alive 75` (keeps connections open longer than typical proxy idle timers) and `--timeout-graceful-shutdown 10` (lets in-flight requests finish when Render restarts the service).
- Render gives each workspace 750 free instance hours per month. One always-on service uses about 744 hours in a 31-day month, so keep this as the only Free web service in the workspace, or all of them are suspended when the hours run out.
- Render may restart a Free service at any time, so the first request after a restart can be slow.

## CSV format
Required columns: `company,state,monthly_premium`
Optional: `fees_monthly,bodily_injury_limit,property_damage_limit,comp_deductible,collision_deductible,vehicles,drivers,applied_discounts,quote_date,source,notes`

`applied_discounts` is a semicolon-separated list of lever ids (for example `autopay;paperless;multi_car`). See `GET /api/levers` for ids.

## How the estimates work
Each lever has a rough low and high savings range. Eligible levers that are not already in a quote are stacked (capped at 35% for discounts, 50% with tradeoffs) to give conservative and expected projections. These ranges are illustrative industry-style figures, **not guarantees**. Tune them in `app/levers.py` as you collect real data.

## Important limitations
- No live insurer rates or quote APIs are connected. Live pricing needs a paid quote API or licensed partner.
- The estimate is never the final price. The insurer's official quote, run with truthful information, is what counts.
- Compare only quotes with equivalent coverage, limits, deductibles, fees, and eligibility.
- Never falsify or omit material information in an insurance application (for example a false garaging address or a hidden driver). That is rate evasion and can void claims or get a policy canceled.
- A $200/month full-coverage target is not realistic for every profile or state, and the app will say so.
- This prototype is not legal, financial, or insurance advice.
