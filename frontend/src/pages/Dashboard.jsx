import { useEffect, useState } from "react";
import AntarcticMap from "../components/AntarcticMap";
import StatusBar from "../components/StatusBar";
import { getEnvironment, getHealth } from "../services/api";

function validateEnvironment(environment) {
  if (!environment || typeof environment !== "object") {
    throw new Error("Backend returned an empty environment");
  }

  const requiredObjects = [
    ["metadata", environment.meta],
    ["bounds", environment.meta?.bounds],
    ["grid metadata", environment.meta?.grid],
    ["vessel", environment.vessel],
    ["destination", environment.destination],
  ];
  const missingObject = requiredObjects.find(([, value]) => !value);
  if (missingObject) {
    throw new Error(`Environment is missing ${missingObject[0]}`);
  }
  if (!Array.isArray(environment.cells) || !Array.isArray(environment.icebergs)) {
    throw new Error("Environment cells or icebergs are malformed");
  }

  const expectedCells = environment.meta.grid.rows * environment.meta.grid.cols;
  if (environment.cells.length !== expectedCells) {
    throw new Error(
      `Environment grid expected ${expectedCells} cells but received ${environment.cells.length}`,
    );
  }
  return environment;
}

export default function Dashboard() {
  const [environment, setEnvironment] = useState(null);
  const [backendOnline, setBackendOnline] = useState(false);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");

  useEffect(() => {
    let active = true;

    async function loadDashboard() {
      setLoading(true);
      setError("");

      const [healthResult, environmentResult] = await Promise.allSettled([
        getHealth(),
        getEnvironment(),
      ]);
      if (!active) return;

      setBackendOnline(
        healthResult.status === "fulfilled" && healthResult.value?.status === "ok",
      );

      if (environmentResult.status === "rejected") {
        setError(
          `Unable to load the Antarctic environment. ${environmentResult.reason.message}`,
        );
      } else {
        try {
          setEnvironment(validateEnvironment(environmentResult.value));
        } catch (validationError) {
          setError(`Invalid environment data. ${validationError.message}`);
        }
      }
      setLoading(false);
    }

    loadDashboard();
    return () => {
      active = false;
    };
  }, []);

  return (
    <main className="dashboard-shell">
      <header className="hero">
        <div>
          <p className="eyebrow">SIH26059 · Ministry of Earth Sciences</p>
          <h1>Antarctic navigation environment</h1>
          <p className="hero-copy">
            A deterministic engineering scenario for the Prydz Bay / Bharati-approach corridor.
          </p>
        </div>
        <div className="milestone-badge">Milestone 1</div>
      </header>

      <StatusBar backendOnline={backendOnline} meta={environment?.meta} />

      <section className="map-panel" aria-label="Antarctic environment map">
        {loading && (
          <div className="message-state" role="status">
            <span className="loading-pulse" />
            Loading environment from FastAPI…
          </div>
        )}

        {!loading && error && (
          <div className="message-state error-state" role="alert">
            <strong>Environment unavailable</strong>
            <span>{error}</span>
            <small>Confirm FastAPI is running at the configured API base URL.</small>
          </div>
        )}

        {!loading && environment && (
          <AntarcticMap
            vessel={environment.vessel}
            destination={environment.destination}
            icebergs={environment.icebergs}
            cells={environment.cells}
            route={null}
            bounds={environment.meta.bounds}
          />
        )}
      </section>

      <footer className="map-note">
        Synthetic demonstration only · Local projected canvas · No external map or data service
      </footer>
    </main>
  );
}
