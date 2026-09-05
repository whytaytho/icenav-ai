import { useEffect, useMemo, useState } from "react";
import { CartesianGrid, Legend, Line, LineChart, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";
import ValidationTrackMap from "../components/ValidationTrackMap";
import { getBacktest, getValidationOptions, getValidationTimes } from "../services/api";

const MODELS = ["persistence", "ml", "free_drift"];
const METRIC_LABELS = [
  ["mean_position_error_km", "MEAN KM"],
  ["median_position_error_km", "MEDIAN KM"],
  ["p90_position_error_km", "P90 KM"],
  ["rmse_km", "RMSE KM"],
];

function value(metric, key) {
  const number = metric?.[key];
  return typeof number === "number" ? number.toFixed(2) : "—";
}

function MetricsTable({ title, metrics }) {
  if (!metrics) return null;
  return (
    <section className="console-module validation-card metrics-block">
      <div className="module-heading"><span>{title}</span><span>GREAT-CIRCLE ERROR</span></div>
      <div className="metrics-table">
        <div className="metrics-row metrics-head"><span>MODEL</span>{METRIC_LABELS.map(([, label]) => <span key={label}>{label}</span>)}<span>N</span></div>
        {Object.entries(metrics).map(([model, result]) => (
          <div className="metrics-row" key={model}>
            <strong>{model.toUpperCase()}</strong>
            {result.available === false ? <span className="metric-unavailable">UNAVAILABLE — NO COLLOCATED HISTORICAL WIND/CURRENT</span> : <>{METRIC_LABELS.map(([key]) => <span key={key}>{value(result, key)}</span>)}<span>{result.sample_size ?? "—"}</span></>}
          </div>
        ))}
      </div>
    </section>
  );
}

export default function Validation({ onBack }) {
  const [options, setOptions] = useState(null);
  const [berg, setBerg] = useState("");
  const [times, setTimes] = useState([]);
  const [t0, setT0] = useState("");
  const [results, setResults] = useState({});
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");

  useEffect(() => {
    getValidationOptions().then((data) => {
      setOptions(data);
      setBerg(data.suggested_case?.berg_id || data.berg_ids[0] || "");
    }).catch((reason) => setError(reason.message)).finally(() => setLoading(false));
  }, []);

  useEffect(() => {
    if (!berg) return;
    setLoading(true); setResults({}); setT0("");
    getValidationTimes(berg).then((data) => {
      setTimes(data.t0_values);
      const suggested = options?.suggested_case?.berg_id === berg ? options.suggested_case.t0 : "";
      setT0(data.t0_values.includes(suggested) ? suggested : data.t0_values[Math.floor(data.t0_values.length / 2)] || "");
    }).catch((reason) => setError(reason.message)).finally(() => setLoading(false));
  }, [berg, options]);

  useEffect(() => {
    if (!berg || !t0) return;
    let active = true;
    setLoading(true); setError("");
    Promise.all(MODELS.map(async (model) => [model, await getBacktest(berg, model, t0)]))
      .then((entries) => { if (active) setResults(Object.fromEntries(entries)); })
      .catch((reason) => { if (active) setError(reason.message); })
      .finally(() => { if (active) setLoading(false); });
    return () => { active = false; };
  }, [berg, t0]);

  const aggregate = options?.summary?.group_holdout;
  const temporal = options?.summary?.temporal_holdout;
  const chartData = useMemo(() => [{
    horizon: 24,
    persistence: aggregate?.persistence?.mean_position_error_km,
    ml: aggregate?.ml?.mean_position_error_km,
    zero: aggregate?.zero?.mean_position_error_km,
  }], [aggregate]);

  return (
    <main className="dashboard-shell validation-page">
      <header className="console-header validation-header"><div><p>ICEBERG TRAJECTORY EVIDENCE CONSOLE</p><h1>HISTORICAL VALIDATION</h1></div><button onClick={onBack}>RETURN TO CONSOLE</button></header>
      <section className="console-module validation-card validation-intro">
        <div className="module-heading"><span>BYU/NIC CONSOLIDATED TRACK BACKTEST</span><span>DAILY / +24H</span></div>
        <p><strong>{options?.iceberg_count ?? "—"} ICEBERGS / {(options?.observation_count ?? 0).toLocaleString()} OBSERVATIONS.</strong> This page validates trajectory prediction for giant tabular icebergs only. It does not validate sub-daily predictions, small-berg behaviour, sea-ice forecasts, route risk, or operational suitability.</p>
        <small>{options?.citation}</small>
      </section>
      <section className="validation-controls console-module">
        <label>ICEBERG<select value={berg} onChange={(event) => setBerg(event.target.value)} disabled={loading}>{options?.berg_ids.map((id) => <option key={id}>{id}</option>)}</select></label>
        <label>PREDICTION TIME T0<select value={t0} onChange={(event) => setT0(event.target.value)} disabled={loading || !times.length}>{times.map((timestamp) => <option key={timestamp}>{timestamp}</option>)}</select></label>
        <div className="validation-state"><span>{loading ? "▓▒░ RUNNING BACKTEST" : "● CASE READY"}</span><strong>FEATURE CUTOFF: {t0 || "—"}</strong></div>
      </section>
      {error && <p className="route-request-error validation-error">VALIDATION ERROR // {error}</p>}
      <div className="validation-grid">
        <section className="console-module validation-panel"><div className="module-heading"><span>OBSERVED VS PREDICTED</span><span>{berg || "—"}</span></div><ValidationTrackMap results={results} /></section>
        <section className="console-module validation-panel"><div className="module-heading"><span>CASE ERRORS</span><span>GREAT-CIRCLE KM</span></div><div className="validation-bars">{MODELS.map((model) => {
          const result = results[model];
          return <div key={model} className={result?.available === false ? "unavailable" : ""}><strong>{model.toUpperCase()}</strong>{result?.available === false ? <span>UNAVAILABLE — {result.reason}</span> : <><i style={{ width: `${Math.min(100, (result?.statistics?.mean_error_km || 0) * 8)}%` }} /><span>{result?.statistics?.mean_error_km?.toFixed(2) ?? "—"} KM / N={result?.statistics?.sample_size ?? 0}</span></>}</div>;
        })}</div></section>
      </div>
      <section className="console-module validation-card"><div className="module-heading"><span>HOLDOUT MEAN POSITION ERROR</span><span>ONE INDEPENDENTLY VALIDATED HORIZON</span></div><div className="validation-chart"><ResponsiveContainer><LineChart data={chartData} margin={{ top: 20, right: 35, left: 10, bottom: 25 }}><CartesianGrid stroke="#263b78" /><XAxis dataKey="horizon" type="number" domain={[0, 48]} ticks={[24]} stroke="#aab8df" label={{ value: "HORIZON HOURS", fill: "#aab8df", position: "insideBottom", offset: -12 }} /><YAxis stroke="#aab8df" label={{ value: "ERROR KM", fill: "#aab8df", angle: -90, position: "insideLeft" }} /><Tooltip /><Legend verticalAlign="top" /><Line dataKey="persistence" stroke="#ffcf4a" strokeWidth={4} dot={{ r: 7 }} /><Line dataKey="ml" stroke="#69e6ff" strokeWidth={4} dot={{ r: 7 }} /><Line dataKey="zero" stroke="#ff5fcf" strokeWidth={3} dot={{ r: 6 }} /></LineChart></ResponsiveContainer></div><p>Only +24h aligns with the source’s daily observations, so no unsupported +3h/+6h/+12h accuracy points are drawn.</p></section>
      <MetricsTable title="GROUP HOLDOUT — ICEBERG IDS DISJOINT" metrics={aggregate} />
      <MetricsTable title="TEMPORAL HOLDOUT — EARLIER TRAIN / LATER TEST" metrics={temporal} />
      <section className="console-module validation-card validation-boundary"><div className="module-heading"><span>CLAIM BOUNDARY</span><span>MANDATORY</span></div><p>ML improves mean +24h error over persistence on group holdout, but not on temporal holdout. The Random Forest therefore remains experimental. Free-drift historical accuracy is unavailable because no collocated wind/current dataset was confirmed.</p><small>{options?.data_source}</small></section>
    </main>
  );
}
