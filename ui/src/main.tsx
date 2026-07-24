import "./monaco";
import { StrictMode } from "react";
import { createRoot } from "react-dom/client";
import App from "./App";
import "./styles.css";

// Apply the saved theme before first paint (day by default) to avoid a flash.
document.documentElement.setAttribute("data-theme", localStorage.getItem("dc-theme") || "light");

createRoot(document.getElementById("root")!).render(
  <StrictMode>
    <App />
  </StrictMode>,
);
