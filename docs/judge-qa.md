# ICE-NAV AI — Prepared Answers

**SIH26059 — Ministry of Earth Sciences**

Every number here is measured and traceable. If you are asked something not
covered, the correct answer is *"we did not measure that"* — never a guess.

---

## The core questions

### "Where is the AI?"

> AI is in the **forecasting layer** — specifically iceberg trajectory
> prediction, where a Random Forest trained on real BYU/NIC tracking data
> predicts displacement over a forecast horizon.
>
> Safety-critical route selection is deliberately **not** AI. It is a weighted
> A\* search over a risk surface, so every route we recommend can be audited
> cell by cell. We separated them on purpose: you can inspect why a route was
> chosen, and the system still works if the model is removed.

*Show it:* delete `backend/models/iceberg_model.pkl`, restart, and the demo
still runs on the free-drift baseline with `/health` reporting `degraded`.

### "Why not just use Google Maps?"

> Road networks are static and only their traffic changes; Dijkstra over a
> fixed graph with changing edge weights solves that.
>
> Here the **navigable surface itself changes**. Cells that were passable
> become forbidden as an iceberg drifts or ice thickens, so the set of feasible
> routes at T+6h is genuinely different from the set at T+0. Our router is
> time-expanded — node identity is (cell, arrival-time bucket) — so a cell is
> costed against the forecast for the hour the vessel actually reaches it, not
> against a single frozen snapshot.

### "How do you know it works?"

> Three different ways, and they answer different things.
>
> **The routing is provably optimal.** The test suite runs A\* and Dijkstra over
> the same cost function and asserts equal total cost. That proves our
> heuristic is admissible.
>
> **The demo is reproducible.** `scripts/demo_check.py` measures every figure we
> quote and fails if any regresses. The end-to-end numbers are also asserted in
> the test suite.
>
> **The ML is validated against real observations** — and we report the split
> where it loses, not just the one where it wins.

### "Is this real data?"

> Two different answers, and the distinction matters.
>
> The **demo environment is synthetic** and we say so on screen — the status bar
> carries a SYNTHETIC badge. It is a deterministic, committed scenario so the
> demonstration is reproducible and does not depend on venue internet.
>
> The **machine learning is trained and validated on real data**: the BYU/NIC
> Consolidated Antarctic Iceberg Tracking Database, 95 icebergs and 45,345
> observations.
>
> We also built the ingestion pipeline for real sea-ice products, but we have
> deliberately **not** claimed an observed sea-ice scenario, because we have not
> approved a specific product with its exact version, citation, licence,
> projection and resolution. We would rather ship an honest gap than an
> unverifiable claim.

### "Why Random Forest and not deep learning?"

> Random Forest gives a strong nonlinear baseline, trains in seconds, and is
> straightforward to validate on this data volume. A sequence model on 45,000
> observations from 95 icebergs would overfit, and we would not be able to
> defend its behaviour.
>
> Sequence models are documented future work, contingent on more data.

### "Does the ML actually beat the baseline?"

> **On one split yes, on the other no**, and we report both.
>
> On the iceberg-disjoint group holdout the Random Forest averages 2.35 km
> position error against persistence at 2.93 km. On the temporal holdout
> persistence wins: 0.58 km against our 0.67 km.
>
> So we present it as experimental, not as an operationally validated
> replacement for persistence. A model that beat only a stationary baseline
> would have demonstrated nothing, which is why persistence is in the table.

---

## Methodology questions

### "Where did those risk weights come from?"

> They are **configurable prototype values chosen to demonstrate the decision
> architecture**, not calibrated operating limits. Operational deployment would
> tune them against vessel ice class, historic voyages and polar navigation
> expertise.
>
> They are not buried in code — every active constant is in one YAML file and
> served live.

*Show it:* open <http://localhost:8000/config/risk> on screen.

### "Isn't a weighted sum too crude for iceberg risk?"

> It would be, which is why iceberg proximity is **not** only a weighted term.
>
> Risk has two tiers. Anything within an iceberg's radius plus its safety
> buffer is a **hard constraint** — those cells are removed from the search
> graph entirely, so no weighting can ever route a vessel through an iceberg.
> The weighted term only shapes preference among cells that are already
> passable.
>
> A collision is not a 25%-bad outcome, so it is not modelled as one.

### "Your fuel index equals the route distance. Is it broken?"

> No — it is binding correctly and simply not biting on this scenario.
>
> The index is `segment_km × resistance_factor(ice)`, and the resistance factor
> is 1.0 below 0.20 ice concentration. No candidate route here crosses ice that
> heavy, so the index equals distance. It exceeds distance the moment a route
> is forced through heavier ice.
>
> We could have reshaped the scenario to manufacture a fuel difference. We
> chose not to, because the reroute demonstration matters more and we would
> rather the number be honest than impressive.

### "Is the demo scenario rigged?"

> The **geography is deliberately designed** — we placed an ice band with two
> leads and put an iceberg where it would drift across one of them. That is
> engineering a test case, and we document it openly.
>
> What is **not** rigged: there is no branch anywhere that says "if this is the
> demo, raise an alert." The alert, the reroute and the explanation all come
> from the same generic engine that would run on any scenario. Move the iceberg
> and everything changes accordingly.

*Show it:* the hazard threshold config in `weights.yaml`, and the fact that the
alert fires at +3h, +6h, +12h and +24h — not at one hand-picked hour.

### "Why is the explanation trustworthy? Couldn't it say anything?"

> It is arithmetic, not narration. We diff the stored per-component risk
> contributions between the T+0 evaluation and the forecast evaluation, sort by
> magnitude, and report them.
>
> The components **sum to the reported total**, and there is a test that fails
> if they ever stop summing. We deliberately did not use a language model here:
> the risk engine already knows exactly what changed, so asking a model to
> guess would be less accurate and less defensible.

### "Your grid is 11 km. Isn't that too coarse for navigation?"

> Yes, for operational navigation it is. It is the same order as the standard
> NSIDC 25 km passive-microwave sea-ice product, so it is a reasonable
> prototype resolution, but it limits exclusion-zone and route resolution and
> we list that as a limitation.
>
> Finer resolution is a data and tiling problem, not a change to the decision
> pipeline.

### "Can this scale to all of Antarctica?"

> The prototype deliberately covers one bounded corridor. Scaling changes three
> things: tiling, data volume, and the projection — we would move from our
> local cos(latitude)-corrected approximation to EPSG:3031, the polar
> stereographic projection the NSIDC sea-ice products already use.
>
> The decision pipeline itself is unchanged.

---

## Hard questions worth inviting

### "What is the biggest weakness of this system?"

> **Growlers and bergy bits.** Small ice fragments are in practice a dominant
> collision hazard for ships in polar water, and they are not resolvable in any
> satellite iceberg database — including the one we train on. They are entirely
> out of scope.
>
> Our system addresses large-berg and sea-ice hazards. A real deployment would
> need onboard radar for the small-ice problem, and that is a different sensor
> and a different system.

### "What if the forecast is wrong?"

> This is decision support, not autonomous control — a human captain decides.
>
> Concretely: our iceberg predictions carry measured error bounds from real
> historical validation, and we display them. The route is recomputed whenever
> conditions materially change. And critically, we are honest about what is
> *not* validated: sea-ice forecasting carries no accuracy claim at all, and
> our iceberg model is validated at +24h while the demo shows +6h.

### "You validate at 24 hours but demo at 6. Isn't that dishonest?"

> It would be if we hid it. We state it in the interface, in the README, and in
> the model metadata file.
>
> The source data is daily, so 24 hours is the shortest horizon that can be
> validated against a real subsequent observation. The shorter horizons are
> interpolations from a model validated at daily resolution, and we label them
> as not independently validated rather than quoting an error figure we did not
> measure.
>
> Fixing it properly requires sub-daily observations, which is in our future
> scope.

### "Why is the model trained on giant icebergs when your demo has small ones?"

> Because satellite scatterometers can only resolve the giant ones — that is
> the only real trajectory data that exists at scale.
>
> So the honest framing is: the model demonstrates that data-driven drift
> prediction works for the size class the data covers. It is not a validated
> claim about 1–4 km bergs. We state that wherever the accuracy is quoted.

### "What did you actually build versus what did AI write?"

> We used AI-assisted development and code-review tools to accelerate
> implementation. The architecture, the algorithms, the validation methodology
> and the integration were designed and verified by us.
>
> Every major file is understood by at least one of us, and we can walk you
> through any of them — the cost function, the admissibility argument, the
> split strategy, or the hazard thresholds.

---

## Quick reference — numbers you must know

| Quantity | Value |
|---|---|
| Grid | 30 × 30, ~11.1 km cells |
| Corridor | 69.5°S–66.5°S, 71°E–79°E |
| Straight-line distance | 344.4 km |
| Planned balanced route | 350.9 km, 15.8 h, safety 89.8 |
| Safety at +6h | 43.4 |
| Alternate route safety | 87.5 |
| Reroute cost | +12.0 km, +0.5 h, +12.0 ice-adj. km |
| Risk weights | 0.50 ice / 0.25 berg / 0.15 wind / 0.10 current |
| Mode alphas | Fastest 0.0, Balanced 0.6, Safest 4.0 |
| Hard block | ice ≥ 0.80, land, berg radius + buffer |
| ML data | BYU/NIC v8.0 — 95 bergs, 45,345 observations, daily |
| ML group holdout | RF 2.35 km vs persistence 2.93 km |
| ML temporal holdout | RF 0.67 km vs persistence 0.58 km (**RF loses**) |
| Tests | 89 |
