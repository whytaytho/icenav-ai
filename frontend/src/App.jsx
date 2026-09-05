import { lazy, Suspense, useState } from "react";
import Dashboard from "./pages/Dashboard";

const Validation = lazy(() => import("./pages/Validation"));

export default function App() {
  const [page, setPage] = useState("dashboard");
  return page === "validation"
    ? <Suspense fallback={<div className="message-state">▓▒░ LOADING VALIDATION CONSOLE…</div>}><Validation onBack={() => setPage("dashboard")} /></Suspense>
    : <Dashboard onValidation={() => setPage("validation")} />;
}
