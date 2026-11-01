# BestQoute — Insurance Quote Optimizer (v0.5.0)

A web app that compares real, user-entered auto insurance quotes, checks eligible **legitimate savings levers**, and prioritizes exact requested coverage before price. The default target is $200/month with a configurable API fallback allowance of $50/month (so the default fallback ceiling is $250). It ends with a **buy-ready packet** the shopper takes to the insurer for the official quote.

It is not an automatic live-quote aggregator. Quotes are entered by the user or imported from CSV.

## What it does
- Ranks verified same-coverage quotes by actual all-in price (premium + monthly fees); estimated discount projections never outrank a lower real quote.
- **Lever engine:** discount stacking (bundle, multi-car, telematics, pay in full, autopay, paperless, good student, low mileage, defensive course, homeowner, group/employer, military, early shopper, claim-free, continuous coverage, safety features).
- Shows **coverage tradeoffs** (higher deductible, dropping collision on an old car, state options in PA, NJ, MI) as a separate scenario, never mixed into the same-coverage numbers.
- Lists **state programs** to check eligibility for (CA, NJ).
- **$200 tracker:** progress bar per quote and a plain verdict (under target, reachable, possible, tradeoffs only, or gap).
- **Strict comparability:** missing or different limits, deductibles, vehicle counts, or driver counts prevent a quote from being marked as a match.
- **Buy-ready packet:** coverage to request, discounts to ask for by name, steps, and what to check before paying.
- API: `POST /api/compare`, `GET /api/levers`, `POST /api/import-csv`, `GET /api/search/status`, `GET /api/health`.

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

Set a local password before starting the server (PowerShell: `$env:BESTQOUTE_PASSWORD="your-long-password"`; macOS/Linux: `export BESTQOUTE_PASSWORD="your-long-password"`). Then open http://127.0.0.1:8000.

## Test the browser engine
Run `python -m compileall -q app` and `node --check app/static/browser-search.js` locally. Playwright's Chromium binary is installed during the Docker image build. Provider-specific end-to-end tests should use a local fixture page and must not submit data to a real carrier.

## Deploy on Render
1. Create a GitHub repository and upload all of these files (keep the `app/` folder structure).
2. In Render, choose **New + → Blueprint** and connect the repository.
3. Review the service, then deploy. Render reads `render.yaml`.
4. Open the service URL. Health check: `/api/health`.

Quote comparison requests are processed by the server; this release does not persist a quote database. The frontend keeps names, ZIP codes, VINs, and driver/vehicle identifiers in the browser, while selected profile facts and quote details are sent to the protected API for comparison.

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

## Browser automation on Render
This release includes a Playwright Chromium browser engine, asynchronous in-process search jobs, provider adapter interface, job status endpoints, and manual-intervention detection. Render uses the Dockerfile so Chromium and its system dependencies are installed. Uptime monitoring can ping `/api/health` to keep the free web service warm, but it does not make the service immune to Render restarts. Browser jobs are in memory and are lost if the process restarts.

Endpoints:
- `GET /api/browser/providers` — list explicitly configured carrier adapters.
- `POST /api/browser/search` — start an authorized quote-search job.
- `GET /api/browser/jobs/{job_id}` — poll a job.

To enable a carrier, implement a provider-specific adapter based on `app/browser_provider_template.py`, verify that the carrier permits automated use of its quote flow, and register the adapter in `app/browser_jobs.py`. Adapters must use the carrier's quote-only flow; no purchase/bind action is exposed. Security challenges, CAPTCHA, access denials, and rate limits stop the job for human handling.

The browser engine is not the same as having carrier integrations: no carrier adapters are enabled in this release, so it cannot yet return live insurance prices. It does not fabricate results. Submitted form values are held in process memory only and are not written to logs or a database. Avoid sending Social Security numbers, passwords, payment-card details, or driver's-license numbers through the API.

## Live quote search status
- This release does **not** yet connect to live insurer quote APIs. `GET /api/search/status` reports this honestly; no simulated prices are presented as real offers.
- `app/search_engine.py` establishes the provider integration boundary. `app/browser_agent.py` provides the Playwright UI automation engine and `app/browser_jobs.py` coordinates jobs. A real approved provider adapter, API credentials, and any required licensing/contract approvals must be added before automated carrier searches can run.

## Important limitations
- No live insurer rates or quote APIs are connected. Live pricing needs a paid quote API or licensed partner.
- The estimate is never the final price. The insurer's official quote, run with truthful information, is what counts.
- Compare only quotes with equivalent coverage, limits, deductibles, fees, and eligibility.
- Never falsify or omit material information in an insurance application (for example a false garaging address or a hidden driver). That is rate evasion and can void claims or get a policy canceled.
- A $200/month full-coverage target is not realistic for every profile or state, and the app will say so.
- This prototype is not legal, financial, or insurance advice.
