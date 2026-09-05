const ICE_BANDS = [
  ["ice-low", "0–20", "LOW"],
  ["ice-moderate", "20–40", "MOD"],
  ["ice-high", "40–60", "HIGH"],
  ["ice-very-high", "60–80", "V.HIGH"],
  ["ice-extreme", "80–100", "EXTREME"],
];

const RISK_BANDS = [
  ["risk-low", "0–20", "LOW"],
  ["risk-moderate", "20–40", "MOD"],
  ["risk-elevated", "40–60", "ELEV"],
  ["risk-high", "60–80", "HIGH"],
  ["risk-severe", "80–100", "SEVERE"],
];

export default function Legend({ layerMode }) {
  const isRisk = layerMode === "risk";
  const bands = isRisk ? RISK_BANDS : ICE_BANDS;

  return (
    <section className="console-module legend-module" aria-label={`${isRisk ? "Risk" : "Sea ice"} legend`}>
      <div className="module-heading">
        <span>{isRisk ? "RISK INDEX" : "ICE CONCENTRATION"}</span>
        <span>{isRisk ? "0–100" : "0–100%"}</span>
      </div>
      <div className="legend-stack">
        {bands.map(([className, range, label]) => (
          <div className="legend-row" key={className}>
            <span className={`legend-chip ${className}`} />
            <span>{range}</span>
            <strong>{label}</strong>
          </div>
        ))}
        <div className="legend-row blocked-row">
          <span className="legend-chip blocked" />
          <span>BLOCK</span>
          <strong>{isRisk ? "LAND / ICE / BERG" : "LAND"}</strong>
        </div>
      </div>
    </section>
  );
}
