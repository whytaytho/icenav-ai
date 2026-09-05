function formatDataSource(dataSource) {
  if (dataSource === "synthetic") return "Synthetic Demo";
  if (dataSource === "synthetic_forecast") return "Synthetic Forecast";
  return dataSource || "—";
}

export default function StatusBar({ backendOnline, meta, riskMeta }) {
  const synthetic = meta?.data_source?.startsWith("synthetic");
  return (
    <section className="status-bar" aria-label="System status">
      <div className="brand-cell">
        <span className="brand-mark" aria-hidden="true">✦</span>
        <div>
          <span className="status-label">System</span>
          <strong>ICE-NAV AI</strong>
        </div>
      </div>
      <div>
        <span className="status-label">Backend</span>
        <strong className={backendOnline ? "online" : "offline"}>
          <span className="status-dot" aria-hidden="true" />
          {backendOnline ? "ONLINE" : "OFFLINE"}
        </strong>
      </div>
      <div>
        <span className="status-label">Scenario</span>
        <strong>{meta?.scenario_id || "—"}</strong>
      </div>
      <div>
        <span className="status-label">Data source</span>
        <strong className={synthetic ? "source-synthetic" : "source-observed"}><span className={`source-badge ${synthetic ? "synthetic" : "observed"}`}>{synthetic ? "SYNTHETIC" : "OBSERVED"}</span>{formatDataSource(meta?.data_source)}</strong>
      </div>
      <div>
        <span className="status-label">Forecast</span>
        <strong>{meta ? `T+${meta.forecast_hour}h` : "—"}</strong>
      </div>
      <div>
        <span className="status-label">Grid</span>
        <strong>{meta ? `${meta.grid.rows} × ${meta.grid.cols}` : "—"}</strong>
      </div>
      <div>
        <span className="status-label">Risk model</span>
        <strong>{riskMeta?.risk_model_version?.toUpperCase() || "—"}</strong>
      </div>
    </section>
  );
}
