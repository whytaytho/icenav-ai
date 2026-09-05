export default function AlertPanel({ hazard, onReroute, loading }) {
  if (!hazard?.alert) return null;
  return (
    <section className={`console-module alert-panel severity-${hazard.severity}`} role="alert">
      <div className="module-heading"><span>PREDICTED ROUTE CONFLICT</span><span>{hazard.severity?.toUpperCase()}</span></div>
      <p>{hazard.reason}</p>
      <strong>{hazard.original_safety} → {hazard.forecast_safety} SAFETY</strong>
      <small>FIRST CONFLICT T+{hazard.first_conflict_hour ?? "?"}H</small>
      <button className="reroute-button" onClick={onReroute} disabled={loading}>{loading ? "RECALCULATING…" : "AUTO REROUTE"}</button>
    </section>
  );
}
