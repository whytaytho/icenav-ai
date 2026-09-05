import { useEffect, useState } from "react";
import AlertPanel from "../components/AlertPanel";
import AntarcticMap from "../components/AntarcticMap";
import ExplainabilityPanel from "../components/ExplainabilityPanel";
import ForecastSlider from "../components/ForecastSlider";
import LayerToggle from "../components/LayerToggle";
import Legend from "../components/Legend";
import NavigationPanel from "../components/NavigationPanel";
import RouteComparison from "../components/RouteComparison";
import ScenarioSelector from "../components/ScenarioSelector";
import StatusBar from "../components/StatusBar";
import { compareRoutes, getEnvironment, getForecastHorizons, getHealth, getRiskGrid, getScenarios, postRoute, rebuildForecast, reroute } from "../services/api";

const MODE_COLORS = { fastest: "#ffcf4a", balanced: "#6dff88", safest: "#ff5fcf" };

function validateEnvironment(environment) {
  if (!environment?.meta?.bounds || !environment?.meta?.grid || !environment.vessel || !environment.destination || !Array.isArray(environment.cells) || !Array.isArray(environment.icebergs)) throw new Error("Environment payload is malformed");
  if (environment.cells.length !== environment.meta.grid.rows * environment.meta.grid.cols) throw new Error("Environment cell count does not match grid metadata");
  return environment;
}

export default function Dashboard({ onValidation }) {
  const [environment, setEnvironment] = useState(null);
  const [originEnvironment, setOriginEnvironment] = useState(null);
  const [riskGrid, setRiskGrid] = useState(null);
  const [scenarios, setScenarios] = useState([]);
  const [scenarioId, setScenarioId] = useState("prydz-bay-demo-v1");
  const [horizons, setHorizons] = useState([0, 3, 6, 12, 24]);
  const [forecastHour, setForecastHour] = useState(0);
  const [driftModel, setDriftModel] = useState("free_drift");
  const [layerMode, setLayerMode] = useState("risk");
  const [routeMode, setRouteMode] = useState("balanced");
  const [routesByMode, setRoutesByMode] = useState({});
  const [comparison, setComparison] = useState(null);
  const [committedRoute, setCommittedRoute] = useState(null);
  const [hazardResult, setHazardResult] = useState(null);
  // The alternate route is computed as soon as a hazard is detected, but it
  // is only drawn once the operator accepts it. Showing it automatically
  // would make the AUTO REROUTE control look inert.
  const [rerouteAccepted, setRerouteAccepted] = useState(false);
  const [showRaw, setShowRaw] = useState(false);
  const [showAllRoutes, setShowAllRoutes] = useState(false);
  const [routeLoading, setRouteLoading] = useState(false);
  const [backendOnline, setBackendOnline] = useState(false);
  const [backendHealth, setBackendHealth] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");

  useEffect(() => {
    Promise.all([getHealth(), getEnvironment(0), getRiskGrid(0), getForecastHorizons(), getScenarios()]).then(([health, env, risk, forecast, availableScenarios]) => {
      const checked = validateEnvironment(env);
      // "degraded" means every endpoint still works but something optional is
      // missing (typically the ML model, which falls back to free drift).
      // Treating that as OFFLINE would misreport a fully working backend.
      setBackendOnline(health.status === "ok" || health.status === "degraded");
      setBackendHealth(health);
      setEnvironment(checked); setOriginEnvironment(checked); setRiskGrid(risk); setHorizons(forecast.horizons_hours); setScenarios(availableScenarios); setScenarioId(checked.meta.scenario_id); setLoading(false);
    }).catch((reason) => { setError(`Unable to load Antarctic console. ${reason.message}`); setLoading(false); });
  }, []);

  const activeRoute = routesByMode[routeMode] || null;
  const isSynthetic = environment?.meta?.data_source?.startsWith("synthetic") ?? true;
  const routeRequest = environment ? { start: { lat: environment.vessel.lat, lon: environment.vessel.lon }, destination: { lat: environment.destination.lat, lon: environment.destination.lon }, forecastHour, departureHour: null } : null;

  async function changeScenario(nextScenarioId) {
    setLoading(true); setError("");
    try {
      const [env, risk] = await Promise.all([getEnvironment(0, nextScenarioId), getRiskGrid(0, nextScenarioId)]);
      const checked = validateEnvironment(env);
      setScenarioId(checked.meta.scenario_id); setEnvironment(checked); setOriginEnvironment(checked); setRiskGrid(risk); setForecastHour(0); setRoutesByMode({}); setComparison(null); setCommittedRoute(null); setHazardResult(null);
    } catch (reason) { setError(`Scenario update failed. ${reason.message}`); }
    finally { setLoading(false); }
  }

  async function evaluateCommitted(hour, routeToEvaluate = committedRoute) {
    if (!routeToEvaluate?.route || !originEnvironment) return;
    const auditPath = routeToEvaluate.route_raw || routeToEvaluate.route;
    const result = await reroute({ current_route: auditPath.map(({ lat, lon, arrival_hour }) => ({ lat, lon, arrival_hour })), current_position: { lat: originEnvironment.vessel.lat, lon: originEnvironment.vessel.lon }, destination: { lat: originEnvironment.destination.lat, lon: originEnvironment.destination.lon }, mode: routeMode, departure_hour: 0, evaluate_at_hour: hour });
    setHazardResult(result);
    setRerouteAccepted(false);
  }

  async function changeForecast(hour) {
    setLoading(true); setError("");
    try {
      const [env, risk] = await Promise.all([getEnvironment(hour, scenarioId), getRiskGrid(hour, scenarioId)]);
      setEnvironment(validateEnvironment(env)); setRiskGrid(risk); setForecastHour(hour);
      await evaluateCommitted(hour);
    } catch (reason) { setError(`Forecast update failed. ${reason.message}`); }
    finally { setLoading(false); }
  }

  async function calculateRoute() {
    if (!routeRequest) return;
    setRouteLoading(true); setError("");
    try { const result = await postRoute({ ...routeRequest, mode: routeMode }); setRoutesByMode({ [routeMode]: result }); setComparison(null); setShowAllRoutes(false); setLayerMode("risk"); setHazardResult(null); }
    catch (reason) { setError(`Route request failed. ${reason.message}`); }
    finally { setRouteLoading(false); }
  }

  async function calculateComparison() {
    if (!routeRequest) return;
    setRouteLoading(true);
    try { const result = await compareRoutes(routeRequest); setComparison(result); setRoutesByMode(result.routes || {}); const selected = result.recommendation?.mode || "balanced"; setRouteMode(selected); setShowAllRoutes(true); setLayerMode("risk"); }
    catch (reason) { setError(`Route comparison failed. ${reason.message}`); }
    finally { setRouteLoading(false); }
  }

  async function changeModel(model) {
    setLoading(true);
    try { const result = await rebuildForecast(model); setDriftModel(result.drift_model_used); await changeForecast(forecastHour); }
    catch (reason) { setError(`Model switch failed. ${reason.message}`); setLoading(false); }
  }

  const mapRoutes = Object.entries(routesByMode).filter(([mode, result]) => result?.success && (showAllRoutes || mode === routeMode)).map(([mode, result]) => ({ mode, points: result.route, color: MODE_COLORS[mode], active: mode === routeMode }));

  return <main className="dashboard-shell">
    <header className="console-header"><div className="header-brand"><span className="tiny-ship">▰</span><div><p>SIH26059 // MINISTRY OF EARTH SCIENCES</p><h1>ICE-NAV AI</h1></div></div><div className="header-center">FORECAST • HAZARD • ML DECISION CONSOLE</div><button className="milestone-badge" onClick={onValidation}>VALIDATION</button></header>
    <StatusBar backendOnline={backendOnline} health={backendHealth} meta={environment?.meta} riskMeta={riskGrid?.meta} />
    <div className="console-grid"><section className="map-panel"><div className="screen-corners" />{loading && <div className="message-state">▓▒░ UPDATING FORECAST…</div>}{!loading && error && <div className="message-state error-state"><strong>CONNECTION FAULT</strong><span>{error}</span></div>}{!loading && environment && riskGrid && <AntarcticMap vessel={environment.vessel} destination={environment.destination} icebergs={environment.icebergs} originIcebergs={originEnvironment?.icebergs || []} cells={environment.cells} riskCells={riskGrid.cells} layerMode={layerMode} route={activeRoute?.success ? activeRoute.route : null} routeRaw={showRaw && activeRoute?.success ? activeRoute.route_raw : null} routes={mapRoutes} bounds={environment.meta.bounds} forecastHour={forecastHour} committedRoute={committedRoute?.route} hazard={hazardResult} showAlternate={rerouteAccepted} />}</section>
      <aside className="command-sidebar"><ScenarioSelector scenarios={scenarios} value={scenarioId} onChange={changeScenario} loading={loading} /><ForecastSlider horizons={horizons} value={forecastHour} onChange={changeForecast} loading={loading} disabled={!isSynthetic} /><section className="console-module"><div className="module-heading"><span>DRIFT MODEL</span><span>{driftModel.toUpperCase()}</span></div><select value={driftModel} onChange={(event) => changeModel(event.target.value)} disabled={!isSynthetic || loading}><option value="free_drift">FREE DRIFT</option><option value="persistence">PERSISTENCE</option><option value="ml">ML RANDOM FOREST</option></select><small>{environment?.meta?.trajectory_validation?.validated ? `ML +${forecastHour}H VALIDATION — GROUP ${environment.meta.trajectory_validation.group_holdout.mean_position_error_km.toFixed(2)} KM / TEMPORAL ${environment.meta.trajectory_validation.temporal_holdout.mean_position_error_km.toFixed(2)} KM.` : "ML IS VALIDATED ONLY AT +24H ON GIANT TABULAR BERGS; SUB-DAILY OUTPUTS ARE NOT INDEPENDENTLY VALIDATED."}</small></section><LayerToggle layerMode={layerMode} onChange={setLayerMode} /><NavigationPanel mode={routeMode} onModeChange={setRouteMode} onCalculate={calculateRoute} onCompare={calculateComparison} loading={routeLoading} disabled={!environment || Boolean(error) || !isSynthetic} routeResult={activeRoute} showRaw={showRaw} onShowRawChange={setShowRaw} />{!isSynthetic && <div className="route-request-error">OBSERVED SCENARIO VIEW IS INSPECTION-ONLY UNTIL ITS FORECAST SERIES IS CACHED.</div>}{activeRoute?.success && <button className="commit-button" onClick={() => { setCommittedRoute(activeRoute); setHazardResult(null); setRerouteAccepted(false); if (forecastHour > 0) evaluateCommitted(forecastHour, activeRoute); }}>COMMIT ACTIVE ROUTE</button>}<AlertPanel hazard={hazardResult} accepted={rerouteAccepted} onReroute={() => { if (hazardResult?.alternate_route?.success) { setRerouteAccepted(true); setRoutesByMode((current) => ({ ...current, [routeMode]: hazardResult.alternate_route })); setShowAllRoutes(false); } }} loading={routeLoading} /><Legend layerMode={layerMode} /></aside>
    </div>
    <ExplainabilityPanel explanation={hazardResult?.explanation} />
    <RouteComparison comparison={comparison} activeMode={routeMode} onSelectMode={setRouteMode} showAll={showAllRoutes} onShowAllChange={setShowAllRoutes} />
    <footer className="console-footer"><span>OFFLINE CACHED ENVIRONMENT</span><span>{forecastHour ? `PREDICTED CONDITIONS — ${environment?.meta?.drift_model_used || driftModel} MODEL` : "CURRENT CONDITIONS"}</span><span>ICE-NAV M8 / BUILD 0.8</span></footer>
  </main>;
}
