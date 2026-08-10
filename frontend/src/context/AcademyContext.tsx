import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useState,
  type ReactNode,
} from "react";
import { academyApi, toErrorMessage } from "../api/client";
import { clearDemoStorage } from "../pages/demoStorage";
import type {
  CurriculumCatalog,
  Dashboard,
  PlatformInfo,
  RemediationGuidance,
  RemediationRegistry,
  ScenarioRun,
} from "../types";

interface AcademyContextValue {
  catalog: CurriculumCatalog | null;
  dashboard: Dashboard | null;
  platform: PlatformInfo | null;
  lastRun: ScenarioRun | null;
  booting: boolean;
  serviceError: string | null;
  remediation: RemediationRegistry | null;
  /** Guidance for a diagnostic code, or null when none is registered. */
  remediationFor: (code: string) => RemediationGuidance | null;
  setLastRun: (run: ScenarioRun | null) => void;
  refreshProgress: () => Promise<void>;
  refreshCatalog: () => Promise<void>;
  resetProgress: () => Promise<void>;
}

const AcademyContext = createContext<AcademyContextValue | null>(null);

export function AcademyProvider({ children }: { children: ReactNode }) {
  const [catalog, setCatalog] = useState<CurriculumCatalog | null>(null);
  const [dashboard, setDashboard] = useState<Dashboard | null>(null);
  const [platform, setPlatform] = useState<PlatformInfo | null>(null);
  const [lastRun, setLastRun] = useState<ScenarioRun | null>(null);
  const [booting, setBooting] = useState(true);
  const [serviceError, setServiceError] = useState<string | null>(null);
  const [remediation, setRemediation] = useState<RemediationRegistry | null>(null);

  const refreshProgress = useCallback(async () => {
    setDashboard(await academyApi.progress());
  }, []);

  const refreshCatalog = useCallback(async () => {
    setCatalog(await academyApi.catalog());
  }, []);

  const resetProgress = useCallback(async () => {
    setDashboard(await academyApi.resetProgress());
    // "Reset everything" must also cover the browser-persisted demo state:
    // a reset learner record with resurrected predictions and run results
    // would misrepresent what the learner has actually done.
    clearDemoStorage();
    await refreshCatalog();
  }, [refreshCatalog]);

  useEffect(() => {
    let active = true;
    async function bootstrap() {
      setBooting(true);
      const [healthResult, platformResult, catalogResult, progressResult, remediationResult] =
        await Promise.allSettled([
          academyApi.health(),
          academyApi.platform(),
          academyApi.catalog(),
          academyApi.progress(),
          academyApi.remediation(),
        ]);
      if (!active) return;
      if (platformResult.status === "fulfilled") setPlatform(platformResult.value);
      if (catalogResult.status === "fulfilled") setCatalog(catalogResult.value);
      if (progressResult.status === "fulfilled") setDashboard(progressResult.value);
      if (remediationResult.status === "fulfilled") setRemediation(remediationResult.value);
      const rejection = [healthResult, platformResult, catalogResult, progressResult].find(
        (result) => result.status === "rejected",
      );
      setServiceError(
        rejection?.status === "rejected" ? toErrorMessage(rejection.reason) : null,
      );
      setBooting(false);
    }
    void bootstrap();
    return () => {
      active = false;
    };
  }, []);

  const remediationFor = useCallback(
    (code: string): RemediationGuidance | null =>
      remediation?.entries.find((entry) => entry.code === code) ?? null,
    [remediation],
  );

  const value = useMemo<AcademyContextValue>(
    () => ({
      catalog,
      dashboard,
      platform,
      lastRun,
      booting,
      serviceError,
      remediation,
      remediationFor,
      setLastRun,
      refreshProgress,
      refreshCatalog,
      resetProgress,
    }),
    [
      booting,
      catalog,
      dashboard,
      lastRun,
      platform,
      remediation,
      remediationFor,
      refreshCatalog,
      refreshProgress,
      resetProgress,
      serviceError,
    ],
  );

  return <AcademyContext.Provider value={value}>{children}</AcademyContext.Provider>;
}

export function useAcademy(): AcademyContextValue {
  const value = useContext(AcademyContext);
  if (!value) throw new Error("useAcademy must be used inside AcademyProvider");
  return value;
}

/**
 * Context read that tolerates having no provider.
 *
 * For leaf components whose content is additive. Remediation guidance is the
 * case this exists for: a hint must never be able to take down the display of
 * the diagnostic it annotates, and the diagnostic is the part that matters.
 * Pages keep using `useAcademy`, which still throws, so genuine wiring mistakes
 * are not hidden.
 */
export function useAcademyOptional(): AcademyContextValue | null {
  return useContext(AcademyContext);
}

