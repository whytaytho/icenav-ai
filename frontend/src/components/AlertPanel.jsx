export default function AlertPanel({ hazard, onReroute, loading, accepted = false }) {
  if (!hazard?.alert) return null;

  const alternate = hazard.alternate_route;
  const recovered = alternate?.forecast_evaluation?.safety_score;
  const comparison = hazard.comparison;
  const noSaferRoute = !alternate?.success;

  return (
    <section className={`console-module alert-panel severity-${hazard.severity}`} role="alert">
      <div className="module-heading">
        <span>{accepted ? "REROUTE APPLIED" : "PREDICTED ROUTE CONFLICT"}</span>
        <span>{hazard.severity?.toUpperCase()}</span>
      </div>
      <p>{hazard.reason}</p>
      <strong>{hazard.original_safety} → {hazard.forecast_safety} SAFETY</strong>
      <small>FIRST CONFLICT T+{hazard.first_conflict_hour ?? "?"}H</small>

      {noSaferRoute ? (
        <p className="reroute-unavailable">
          {hazard.message || "No safer route meeting the configured constraints was found; human decision required."}
        </p>
      ) : accepted ? (
        <div className="reroute-outcome">
          <strong>
            RECOMMENDED ROUTE SAFETY {recovered !== undefined ? recovered.toFixed(1) : "—"}
          </strong>
          {comparison && (
            <small>
              {comparison.distance_km?.delta !== null && comparison.distance_km?.delta !== undefined
                ? `+${comparison.distance_km.delta.toFixed(1)} KM`
                : ""}
              {comparison.eta_hours?.delta !== null && comparison.eta_hours?.delta !== undefined
                ? ` · +${comparison.eta_hours.delta.toFixed(1)} H`
                : ""}
              {comparison.fuel_index?.delta !== null && comparison.fuel_index?.delta !== undefined
                ? ` · +${comparison.fuel_index.delta.toFixed(1)} ICE-ADJ. KM`
                : ""}
            </small>
          )}
        </div>
      ) : (
        <button className="reroute-button" onClick={onReroute} disabled={loading}>
          {loading ? "RECALCULATING…" : "AUTO REROUTE"}
        </button>
      )}
    </section>
  );
}
