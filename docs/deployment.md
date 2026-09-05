# ICE-NAV AI — Deployment

**SIH26059 — Ministry of Earth Sciences**

---

## Read this first

**Demo from localhost.** Deployment is proof of deployability, not the demo
path.

Free hosting tiers sleep after roughly 15 minutes of inactivity and take tens
of seconds to wake. A cold start in front of a judging panel looks like a
broken product, and there is no way to recover gracefully while people watch.

The local stack starts in about 1.3 seconds, needs no network, and cannot be
affected by venue wifi. Use it.

---

## Architecture

```text
Browser
   |
   |  static assets
   v
Vercel (frontend, Vite build output)
   |
   |  HTTPS, JSON
   v
Render or equivalent (FastAPI backend)
   |
   v
committed scenario + cached forecasts + model
(no external service calls at request time)
```

The backend holds all state in memory, loaded at startup. There is no database
and no runtime external dependency, so a single instance is sufficient and
restarts are cheap.

---

## Backend

### Start command

```bash
uvicorn backend.main:app --host 0.0.0.0 --port $PORT
```

Render and most PaaS providers inject `$PORT`. Do not hardcode 8000 in
production.

### Build command

```bash
pip install -r backend/requirements.txt
```

Dependencies are pinned exactly. `scikit-learn` in particular must stay at the
version recorded in `backend/models/iceberg_model_meta.json`, or the committed
model unpickles with a version warning that scikit-learn documents as
potentially producing invalid results.

### Python version

Pin the runtime to **Python 3.12**. The pinned scikit-learn wheel targets it.
On Render, add a `runtime.txt` at the repository root:

```text
python-3.12
```

### Committed artefacts

`backend/data/demo_scenario.json` and `backend/models/iceberg_model.pkl` are
committed, so no build-time data acquisition is required. The historical
iceberg CSV is **not** committed (redistribution permission was not located);
its absence only disables case-level historical validation, and the application
starts and reports `degraded` rather than failing.

---

## CORS

`backend/main.py` allows explicit origins, not a wildcard:

```python
allow_origins=["http://localhost:5173", "http://127.0.0.1:5173"]
```

**Before deploying, add the production frontend origin** to that list:

```python
allow_origins=[
    "http://localhost:5173",
    "http://127.0.0.1:5173",
    "https://<your-app>.vercel.app",
]
```

Do not replace it with `["*"]`. A wildcard is unnecessary here — the set of
legitimate origins is small and known — and it is the kind of detail a
technical judge notices.

Vercel preview deployments get generated subdomains, which will not match. If
you need previews to work, either add each preview origin or accept that only
the production domain talks to the backend.

---

## Frontend

### Build

```bash
cd frontend
npm ci
npm run build
```

Output is `frontend/dist`. On Vercel set the root directory to `frontend`; the
framework preset is Vite.

### Environment

Set in the Vercel project settings:

```dotenv
VITE_API_BASE=https://<your-backend>.onrender.com
```

Vite inlines `VITE_*` variables at **build time**, not runtime. Changing this
value requires a rebuild, not just a restart.

With no value set, the frontend falls back to `http://localhost:8000`, which is
correct for local use and wrong in production — so verify it is set before
announcing a URL.

---

## Post-deployment verification

Run through all of these before relying on a deployed URL:

```bash
BASE=https://<your-backend>.onrender.com

curl -s $BASE/health | jq .status
curl -s $BASE/environment/current | jq '.meta.scenario_id, (.cells | length)'
curl -s $BASE/config/risk | jq '.weights'
curl -s "$BASE/forecast?hour=6" | jq '.meta.forecast_hour'
curl -s -X POST $BASE/route \
  -H 'Content-Type: application/json' \
  -d '{"start":{"lat":-69.02,"lon":72.10},"destination":{"lat":-66.92,"lon":78.18},"mode":"balanced"}' \
  | jq '.success, .metrics.safety_score'
```

Expected: `"ok"`, `"prydz-bay-demo-v1"` and `900`, the four weights,
`6`, then `true` and a safety score near 89.8.

Then open the deployed frontend and confirm the status bar reads **ONLINE**. If
it reads OFFLINE, the cause is almost always CORS or an unset `VITE_API_BASE`.

---

## Cold-start mitigation

If a deployed URL must be shown live:

- Open it and let it wake **at least two minutes** before you need it.
- Keep a browser tab on `/health` so the instance stays warm.
- Have the local stack running as a fallback, already loaded, on a second tab.

Do not use an external uptime pinger to keep a free instance awake — it
violates most providers' terms and is not necessary for a demonstration.

---

## The offline fallback, which is the actual demo

```powershell
# Terminal 1
.\.venv\Scripts\Activate.ps1
python -m uvicorn backend.main:app --reload --host 127.0.0.1 --port 8000

# Terminal 2
cd frontend
npm run dev
```

The frontend dev server **must** be on port 5173, because that is what the CORS
allowlist names. If 5173 is occupied, Vite silently falls back to 5174 and
every API call fails — kill the stale process rather than accepting the
fallback port.

Verify before presenting:

```bash
python scripts/demo_check.py
```

Then disconnect the network entirely and run the demo once. It must work.
