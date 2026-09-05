const MODES = ["fastest", "balanced", "safest"];

export default function NavigationPanel({
  mode,
  onModeChange,
  onCalculate,
  onCompare,
  loading,
  disabled,
  routeResult,
  showRaw,
  onShowRawChange,
}) {
  const metrics = routeResult?.success ? routeResult.metrics : null;

  return (
    <section className="console-module navigation-module" aria-label="Route controls">
      <div className="module-heading">
        <span>ROUTE ENGINE</span>
        <span className="module-code">A*</span>
      </div>
      <div className="mode-selector" role="group" aria-label="Route mode">
        {MODES.map((candidate) => (
          <button
            type="button"
            key={candidate}
            className={mode === candidate ? `active ${candidate}` : candidate}
            aria-pressed={mode === candidate}
            onClick={() => onModeChange(candidate)}
          >
            {candidate.toUpperCase()}
          </button>
        ))}
      </div>
      <div className="route-actions">
        <button
          type="button"
          className="primary-console-button"
          disabled={disabled || loading}
          onClick={onCalculate}
        >
          {loading ? "CALCULATING…" : "CALCULATE ROUTE"}
        </button>
        <button
          type="button"
          className="secondary-console-button"
          disabled={disabled || loading}
          onClick={onCompare}
        >
          COMPARE ALL MODES
        </button>
      </div>

      {routeResult && !routeResult.success && (
        <div className="route-failure" role="alert">
          <strong>NO ROUTE</strong>
          <span>{routeResult.message}</span>
        </div>
      )}

      {metrics && (
        <div className="route-metrics">
          <span>DISTANCE</span><strong>{metrics.distance_km.toFixed(1)} km</strong>
          <span>ETA</span><strong>{metrics.eta_hours.toFixed(1)} h</strong>
          <span>SAFETY</span><strong>{metrics.safety_score.toFixed(1)} / 100</strong>
          <span>CELLS</span><strong>{metrics.cells_traversed}</strong>
          <span>EST. FUEL INDEX (ICE-ADJ. KM)</span><strong>{metrics.fuel_index.toFixed(1)}</strong>
        </div>
      )}

      <label className="raw-path-toggle">
        <input
          type="checkbox"
          checked={showRaw}
          disabled={!routeResult?.success}
          onChange={(event) => onShowRawChange(event.target.checked)}
        />
        <span>SHOW RAW GRID PATH</span>
      </label>
    </section>
  );
}
