const LABELS = { 0: "NOW", 3: "+3H", 6: "+6H", 12: "+12H", 24: "+24H" };

export default function ForecastSlider({ horizons, value, onChange, loading, disabled = false }) {
  return (
    <section className="console-module forecast-module">
      <div className="module-heading"><span>FORECAST HORIZON</span><span>{loading ? "SYNC" : "READY"}</span></div>
      <div className="forecast-steps">
        {horizons.map((hour) => <button key={hour} className={hour === value ? "active" : ""} onClick={() => onChange(hour)} disabled={loading || disabled} aria-pressed={hour === value}>{LABELS[hour] || `+${hour}H`}</button>)}
      </div>
      {disabled && <small>FORECASTS ARE AVAILABLE FOR THE SYNTHETIC SCENARIO ONLY.</small>}
    </section>
  );
}
