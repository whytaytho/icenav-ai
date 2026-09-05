import { Bar, BarChart, CartesianGrid, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";

export default function ExplainabilityPanel({ explanation }) {
  const change = explanation?.route_change;
  if (!change) return null;
  const maximum = Math.max(1, ...change.contributors.map((item) => Math.abs(item.impact)));
  return (
    <section className="console-module explanation-panel">
      <div className="module-heading"><span>WHY DID ICE-NAV REROUTE?</span><span>AUDIT</span></div>
      <h3>{change.summary}</h3>
      <div style={{ width: "100%", height: 260 }}><ResponsiveContainer><BarChart data={change.contributors} layout="vertical" margin={{ left: 30, right: 30 }}><CartesianGrid stroke="#263b78" strokeDasharray="3 3" /><XAxis type="number" stroke="#aab8df" /><YAxis dataKey="factor" type="category" width={150} stroke="#aab8df" /><Tooltip contentStyle={{ background: "#07102d", border: "2px solid #69e6ff" }} /><Bar dataKey="impact" fill="#69e6ff" /></BarChart></ResponsiveContainer></div>
      {change.contributors.map((item) => <div className="factor-row" key={item.key}><span>{item.factor}</span><div><i style={{ width: `${Math.abs(item.impact) / maximum * 100}%` }} /></div><strong>{item.impact >= 0 ? "+" : ""}{item.impact.toFixed(2)}</strong><small>{item.detail}</small></div>)}
      <p>COMPONENT SUM: {change.total_risk_delta.toFixed(2)} RISK POINTS</p>
    </section>
  );
}
