import { StrictMode } from "react";
import { createRoot } from "react-dom/client";
import { BrowserRouter } from "react-router-dom";
import { App } from "./App";
import { AcademyProvider } from "./context/AcademyContext";
import { ModeProvider } from "./context/ModeContext";
import "./styles.css";

createRoot(document.getElementById("root")!).render(
  <StrictMode>
    <BrowserRouter>
      <ModeProvider>
        <AcademyProvider>
          <App />
        </AcademyProvider>
      </ModeProvider>
    </BrowserRouter>
  </StrictMode>,
);
