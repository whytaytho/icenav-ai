const API_BASE = (import.meta.env.VITE_API_BASE || "http://localhost:8000").replace(
  /\/$/,
  "",
);

async function requestJson(path, options = {}) {
  const controller = new AbortController();
  const timeoutId = window.setTimeout(() => controller.abort(), 8000);

  try {
    const response = await fetch(`${API_BASE}${path}`, {
      ...options,
      headers: {
        Accept: "application/json",
        ...options.headers,
      },
      signal: controller.signal,
    });
    if (!response.ok) {
      throw new Error(`API request failed (${response.status})`);
    }
    return await response.json();
  } catch (error) {
    if (error.name === "AbortError") {
      throw new Error("API request timed out");
    }
    throw error;
  } finally {
    window.clearTimeout(timeoutId);
  }
}

export function getHealth() {
  return requestJson("/health");
}

export function getEnvironment(forecastHour = 0, scenario = "") {
  if (forecastHour) return requestJson(`/forecast?hour=${encodeURIComponent(forecastHour)}`);
  return requestJson(`/environment/current${scenario ? `?scenario=${encodeURIComponent(scenario)}` : ""}`);
}

export function getRiskGrid(forecastHour = 0, scenario = "") {
  const query = new URLSearchParams({ forecast_hour: String(forecastHour) });
  if (scenario) query.set("scenario", scenario);
  return requestJson(`/environment/risk?${query.toString()}`);
}

export function getRiskConfig() {
  return requestJson("/config/risk");
}

export function postRoute({ start, destination, mode, forecastHour = 0, departureHour = null }) {
  return requestJson("/route", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      start,
      destination,
      mode,
      forecast_hour: forecastHour,
      ...(departureHour === null ? {} : { departure_hour: departureHour }),
    }),
  });
}

export function getForecastHorizons() { return requestJson("/forecast/horizons"); }
export function getTrajectory(id) { return requestJson(`/icebergs/trajectory?id=${encodeURIComponent(id)}`); }
export function rebuildForecast(driftModel) { return requestJson(`/forecast/rebuild?drift_model=${encodeURIComponent(driftModel)}`, { method: "POST" }); }
export function reroute(payload) { return requestJson("/route/reroute", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(payload) }); }
export function getScenarios() { return requestJson("/scenarios"); }
export function getValidationOptions() { return requestJson("/validation/options"); }
export function getValidationTimes(bergId) { return requestJson(`/validation/times?berg_id=${encodeURIComponent(bergId)}`); }
export function getBacktest(bergId, model = "persistence", t0 = "") { return requestJson(`/validation/backtest?berg_id=${encodeURIComponent(bergId)}&model=${encodeURIComponent(model)}${t0 ? `&t0=${encodeURIComponent(t0)}` : ""}`); }

export function compareRoutes({ start, destination, forecastHour = 0 }) {
  return requestJson("/routes/compare", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ start, destination, forecast_hour: forecastHour }),
  });
}
