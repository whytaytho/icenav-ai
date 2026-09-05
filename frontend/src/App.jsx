import { useState } from "react";
import Dashboard from "./pages/Dashboard";
import Validation from "./pages/Validation";

export default function App() {
  const [page, setPage] = useState("dashboard");
  return page === "validation" ? <Validation onBack={() => setPage("dashboard")} /> : <Dashboard onValidation={() => setPage("validation")} />;
}
