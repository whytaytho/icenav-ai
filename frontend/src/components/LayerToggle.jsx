export default function LayerToggle({ layerMode, onChange }) {
  return (
    <section className="console-module layer-module" aria-label="Map layer controls">
      <div className="module-heading">
        <span>DISPLAY MODE</span>
        <span className="module-code">SYS.02</span>
      </div>
      <div className="layer-toggle" role="group" aria-label="Environmental layer">
        <button
          type="button"
          className={layerMode === "ice" ? "active" : ""}
          aria-pressed={layerMode === "ice"}
          onClick={() => onChange("ice")}
        >
          <span>F1</span>
          Ice Concentration
        </button>
        <button
          type="button"
          className={layerMode === "risk" ? "active" : ""}
          aria-pressed={layerMode === "risk"}
          onClick={() => onChange("risk")}
        >
          <span>F2</span>
          Navigation Risk
        </button>
      </div>
    </section>
  );
}
