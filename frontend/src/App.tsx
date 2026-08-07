import { Route, Routes } from "react-router-dom";
import { Shell } from "./components/Shell";
import { AboutPage } from "./pages/AboutPage";
import { ApprovalPage } from "./pages/ApprovalPage";
import { BuilderPage } from "./pages/BuilderPage";
import { CapstonePage } from "./pages/CapstonePage";
import { ContractsPage } from "./pages/ContractsPage";
import { CurriculumPage } from "./pages/CurriculumPage";
import { DashboardPage } from "./pages/DashboardPage";
import { DemoPage } from "./pages/DemoPage";
import { DiagnosticsPage } from "./pages/DiagnosticsPage";
import { EvidencePage } from "./pages/EvidencePage";
import { GraphPage } from "./pages/GraphPage";
import { HomePage } from "./pages/HomePage";
import { LessonPage } from "./pages/LessonPage";
import { NotFoundPage } from "./pages/NotFoundPage";
import { OrientationPage } from "./pages/OrientationPage";
import { GlossaryPage } from "./pages/GlossaryPage";
import { PathsPage } from "./pages/PathsPage";
import { SettingsPage } from "./pages/SettingsPage";
import { WorkbenchPage } from "./pages/WorkbenchPage";

export function App() {
  return (
    <Routes>
      <Route element={<Shell />}>
        <Route index element={<HomePage />} />
        <Route path="orientation" element={<OrientationPage />} />
        <Route path="demo" element={<DemoPage />} />
        <Route path="glossary" element={<GlossaryPage />} />
        <Route path="paths" element={<PathsPage />} />
        <Route path="curriculum" element={<CurriculumPage />} />
        <Route path="dashboard" element={<DashboardPage />} />
        <Route path="lessons/:moduleId" element={<LessonPage />} />
        <Route path="workbench" element={<WorkbenchPage />} />
        <Route path="contracts" element={<ContractsPage />} />
        <Route path="contracts/:contractId" element={<ContractsPage />} />
        <Route path="builder" element={<BuilderPage />} />
        <Route path="graph" element={<GraphPage />} />
        <Route path="approvals" element={<ApprovalPage />} />
        <Route path="evidence" element={<EvidencePage />} />
        <Route path="diagnostics" element={<DiagnosticsPage />} />
        <Route path="capstone" element={<CapstonePage />} />
        <Route path="settings" element={<SettingsPage />} />
        <Route path="about" element={<AboutPage />} />
        <Route path="*" element={<NotFoundPage />} />
      </Route>
    </Routes>
  );
}

