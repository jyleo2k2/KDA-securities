import { StrictMode } from "react";
import { createRoot } from "react-dom/client";

import App from "./App";
import { FirstUseGuide } from "./components/FirstUseGuide";
import "./index.css";

const container = document.getElementById("root");
if (!container) {
  throw new Error("#root element is missing in index.html");
}

createRoot(container).render(
  <StrictMode>
    <>
      <App />
      <FirstUseGuide />
    </>
  </StrictMode>,
);
