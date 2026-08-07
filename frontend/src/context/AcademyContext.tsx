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
import type { CurriculumCatalog, Dashboard, PlatformInfo, ScenarioRun } from "../types";

interface AcademyContextValue {
  catalog: CurriculumCatalog | null;
  dashboard: Dashboard | null;
  platform: PlatformInfo | null;
  lastRun: ScenarioRun | null;
  booting: boolean;
  serviceError: string | null;
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

  const refreshProgress = useCallback(async () => {
    setDashboard(await academyApi.progress());
  }, []);

  const refreshCatalog = useCallback(async () => {
    setCatalog(await academyApi.catalog());
  }, []);

  const resetProgress = useCallback(async () => {
    setDashboard(await academyApi.resetProgress());
    await refreshCatalog();
  }, [refreshCatalog]);

  useEffect(() => {
    let active = true;
    async function bootstrap() {
      setBooting(true);
      const [healthResult, platformResult, catalogResult, progressResult] = await Promise.allSettled([
        academyApi.health(),
        academyApi.platform(),
        academyApi.catalog(),
        academyApi.progress(),
      ]);
      if (!active) return;
      if (platformResult.status === "fulfilled") setPlatform(platformResult.value);
      if (catalogResult.status === "fulfilled") setCatalog(catalogResult.value);
      if (progressResult.status === "fulfilled") setDashboard(progressResult.value);
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

  const value = useMemo<AcademyContextValue>(
    () => ({
      catalog,
      dashboard,
      platform,
      lastRun,
      booting,
      serviceError,
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

