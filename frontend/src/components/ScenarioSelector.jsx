export default function ScenarioSelector({ scenarios, value, onChange, loading }) {
  return (
    <section className="console-module scenario-module">
      <div className="module-heading"><span>DATA SCENARIO</span><span>{scenarios.length} CACHED</span></div>
      <select value={value} onChange={(event) => onChange(event.target.value)} disabled={loading}>
        {scenarios.map((scenario) => (
          <option key={scenario.scenario_id} value={scenario.scenario_id}>
            {scenario.scenario_id} // {scenario.data_source}
          </option>
        ))}
      </select>
    </section>
  );
}
