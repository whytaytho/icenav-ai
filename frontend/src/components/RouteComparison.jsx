const MODES = ["fastest", "balanced", "safest"];

export default function RouteComparison({
  comparison,
  activeMode,
  onSelectMode,
  showAll,
  onShowAllChange,
}) {
  if (!comparison) return null;

  const recommended = comparison.recommendation?.mode;
  return (
    <section className="comparison-panel" aria-label="Route comparison">
      <div className="comparison-header">
        <div>
          <span>TACTICAL ROUTE COMPARISON</span>
          <strong>DIRECT REFERENCE {comparison.straight_line_km.toFixed(1)} km</strong>
        </div>
        <label className="all-routes-toggle">
          <input
            type="checkbox"
            checked={showAll}
            onChange={(event) => onShowAllChange(event.target.checked)}
          />
          DISPLAY ALL ROUTES
        </label>
      </div>

      <div className="comparison-table" role="table">
        <div className="comparison-row comparison-labels" role="row">
          <span>MODE</span>
          <span>DISTANCE</span>
          <span>ETA</span>
          <span>SAFETY</span>
          <span>EST. FUEL INDEX (ICE-ADJ. KM)</span>
        </div>
        {MODES.map((mode) => {
          const route = comparison.routes[mode];
          const isRecommended = mode === recommended;
          return (
            <button
              type="button"
              role="row"
              key={mode}
              className={`comparison-row ${mode} ${activeMode === mode ? "active" : ""} ${isRecommended ? "recommended" : ""}`}
              disabled={!route?.success}
              onClick={() => onSelectMode(mode)}
            >
              <span>
                <i className="route-color-chip" />
                {mode.toUpperCase()}
                {isRecommended && <em>RECOMMENDED</em>}
              </span>
              {route?.success ? (
                <>
                  <strong>{route.metrics.distance_km.toFixed(1)} km</strong>
                  <strong>{route.metrics.eta_hours.toFixed(1)} h</strong>
                  <strong>{route.metrics.safety_score.toFixed(1)}</strong>
                  <strong>{route.metrics.fuel_index.toFixed(1)} ice-adj. km</strong>
                </>
              ) : (
                <span className="comparison-unavailable">NO ROUTE AVAILABLE</span>
              )}
            </button>
          );
        })}
      </div>

      {comparison.recommendation && (
        <div className="recommendation-copy">
          <strong>{comparison.recommendation.warning ? "SAFETY WARNING" : "SYSTEM RECOMMENDATION"}</strong>
          <span>{comparison.recommendation.reason}</span>
        </div>
      )}
      <p className="fuel-footnote">
        Estimated Fuel Index is a dimensionless ice-adjusted distance proxy, not measured fuel consumption.
      </p>
    </section>
  );
}
