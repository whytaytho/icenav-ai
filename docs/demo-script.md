# ICE-NAV AI — Demo Script

**SIH26059 — Ministry of Earth Sciences**

Three minutes, timed. Every figure quoted here is produced by the committed
scenario. Verify before presenting:

```bash
python scripts/demo_check.py
```

If that exits non-zero, **do not present until it passes** — the numbers below
will not match what the screen shows.

---

## Before you start

**Setup (do this 10 minutes early, not on stage):**

1. Backend running: `python -m uvicorn backend.main:app --host 127.0.0.1 --port 8000`
2. Frontend running on **port 5173** (CORS names that origin explicitly)
3. Open <http://localhost:8000/health> — confirm `"status": "ok"`
4. Open the dashboard, confirm the status bar reads **ONLINE**
5. Browser zoom at 100%, window maximised, single tab
6. **Run the full sequence once** end to end, then reload the page to reset

**Reset between runs:** reload the browser page. All state is client-side.

**Demo from localhost.** Deployment exists but free tiers sleep and take tens of
seconds to wake. Do not demo from the deployed URL.

---

## 0:00–0:20 — The problem

> "Antarctic navigation is not a shortest-path problem. Sea ice evolves,
> icebergs drift, and a route that is safe at departure can be dangerous six
> hours later.
>
> Google Maps solves a different problem: the roads are fixed and only the
> traffic changes. Here the navigable surface itself changes — water that was
> passable becomes forbidden."

*Point at the map: vessel bottom-left, destination top-right, ice grid between.*

---

## 0:20–0:35 — The solution

> "ICE-NAV AI combines sea-ice, iceberg and environmental data into a
> time-dependent risk surface, and generates explainable navigation
> recommendations across it.
>
> The AI forecasts the environment. It never chooses the route — that stays a
> deterministic A\* search, so every recommendation can be audited."

---

## 0:35–1:20 — Three routes

**Click: COMPARE ALL MODES**

Wait for the comparison table. Expected:

| Mode | Distance | ETA | Safety | Fuel index |
|---|---:|---:|---:|---:|
| Fastest | 350.9 km | 15.8 h | 82.5 | 350.9 |
| Balanced | 350.9 km | 15.8 h | 82.5 | 350.9 |
| Safest | 368.4 km | 16.6 h | 90.6 | 368.4 |

Direct reference: 344.4 km.

> "Three strategies over one risk surface. The difference is a single
> risk-aversion coefficient — zero for Fastest, four for Safest.
>
> Safest buys eight points of safety for seventeen extra kilometres by taking a
> wider lead through the ice. Fastest and Balanced pick the same path here,
> because on this scenario the direct lead is already the cheaper option."

**If a judge asks about the fuel column reading the same as distance:**

> "Correct, and deliberate. No route here crosses ice heavy enough for the
> resistance factor to rise above 1.0, so the index equals distance. It exceeds
> distance only where a route is forced through heavier ice. We did not reshape
> the scenario to manufacture a difference."

**Click the BALANCED row, then: COMMIT ACTIVE ROUTE**

> "We commit to the balanced route. Planned safety, 89.8 out of 100."

> **Do not skip the BALANCED click.** `COMPARE ALL MODES` leaves the
> *recommended* mode selected, which on this scenario is Fastest. Committing
> without selecting Balanced first still works and still fires the alert, but
> the reroute then costs **+9.7 km to safety 87.9** instead of the
> **+12.0 km to 87.5** quoted below, because the reroute is planned with the
> active mode's risk-aversion coefficient. Both are correct; only one matches
> this script.

---

## 1:20–2:10 — The forecast turns

**Click: +6H on the forecast horizon strip**

The icebergs move, the ice field advects, the risk surface recomputes, and the
committed route is automatically re-scored against the new world.

Expected on screen:

```
PREDICTED ROUTE CONFLICT                         CRITICAL
Predicted iceberg_exclusion intersects committed
route near waypoint 10.
89.8 → 43.4 SAFETY
FIRST CONFLICT T+10.0H
[ AUTO REROUTE ]
```

> "Six hours out, iceberg IB-04 has drifted into the lead our route depends on.
> The route we committed to is now scored 43 out of 100 — and the conflict is
> ten hours into the voyage, not at the dock. The ship would already be
> committed when the passage closed.
>
> Note the system is not re-planning yet. It is telling the operator what it
> found, and offering a decision."

*Point at the red dashed line — the committed route, now in danger.*

---

## 2:10–2:35 — The reroute

**Click: AUTO REROUTE**

Expected:

```
REROUTE APPLIED                                  CRITICAL
89.8 → 43.4 SAFETY
RECOMMENDED ROUTE SAFETY 87.5
+12.0 KM · +0.5 H · +12.0 ICE-ADJ. KM
```

A green route appears, routing around the closed lead.

> "The alternate route restores safety to 87.5 — for twelve extra kilometres
> and half an hour. That is the trade the captain is being offered, stated in
> the units they actually care about."

---

## 2:35–2:55 — Why

**Scroll to: WHY DID ICE-NAV REROUTE?**

Expected contributions:

```
Iceberg IB-04              +83.02    weighted contribution 4.75 -> 87.77
Sea-ice concentration       +3.37    weighted contribution 5.38 -> 8.75
Wind                        +0.00
Current                     +0.00
COMPONENT SUM: 86.39 RISK POINTS
```

> "And it tells you exactly why. Iceberg IB-04 proximity contributes 83 risk
> points; sea-ice concentration another 3. Wind and current are unchanged,
> because this prototype holds those fields constant across horizons — and it
> says so rather than inventing a contribution.
>
> The components sum arithmetically to the total. This is not a language model
> narrating a guess; it is the risk engine reporting what it computed."

---

## 2:55–3:00 — Close

> "ICE-NAV does not replace the captain. It turns environmental observations
> and forecasts into transparent, continuously updated navigation decision
> support."

---

## 90-second version

If the slot is compressed, cut sections 0:20–0:35 and 0:35–1:20:

1. Problem (15s)
2. Commit the balanced route — 89.8 safety (10s)
3. Slider to +6h — conflict, 89.8 → 43.4 (25s)
4. AUTO REROUTE — 87.5, +12 km (15s)
5. Explainability panel — IB-04 named, components sum (20s)
6. Close (5s)

The reroute and the explanation are the parts that cannot be cut.

---

## Contingencies

| Symptom | Cause | Action |
|---|---|---|
| Status bar reads OFFLINE | Backend not running or on the wrong port | Restart uvicorn on 8000; reload page |
| Status bar reads DEGRADED | Optional ML model missing | Harmless — free-drift baseline is in use. Say so if asked; do not debug on stage |
| Frontend on port 5174 | Port 5173 already occupied | Kill the stale process, restart on 5173 — CORS only allows 5173 |
| No alert after moving to +6h | Route was not committed | Click COMMIT ACTIVE ROUTE first, then move the slider |
| Numbers differ from this script | Scenario or config changed | Run `python scripts/demo_check.py`; do not improvise figures |
| Route request fails | Backend restarted mid-demo | Reload the page and redo from COMPARE ALL MODES |

**If something breaks, say what broke.** The project's credibility rests on
honest reporting; a presenter who bluffs a number undoes that in one sentence.

---

## Things worth showing if there is time

- **`/config/risk` in a browser tab** — answers "did you tune those weights?"
  by showing the live configuration rather than asserting it.
- **`/health`** — shows scenario, forecast cache state, and which drift model
  is actually in force.
- **The drift-model selector** — switch between persistence, free drift and the
  ML model and watch the predicted iceberg positions change. This demonstrates
  the architecture more convincingly than any slide.
- **The VALIDATION page** — historical backtesting against real BYU/NIC
  iceberg tracks, and the honest result that the Random Forest beats
  persistence on one split and loses on the other.
- **Click any grid cell** — full risk breakdown for that cell, showing raw and
  weighted contributions per factor.

## Things not to claim

- Do not say the fuel index is litres or tonnes.
- Do not say the ML model is validated at +6h. It is validated at +24h only.
- Do not say the sea-ice forecast is validated. It is not validated at all.
- Do not say the environment is real data. The demo scenario is synthetic.
- Do not say the risk weights are calibrated. They are prototype values.
