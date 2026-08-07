import { createContext, useCallback, useContext, useEffect, useMemo, useState, type ReactNode } from "react";
import type { LearnerMode } from "../types";

const STORAGE_KEY = "nornyx-academy.mode";

interface ModeContextValue {
  mode: LearnerMode;
  guided: boolean;
  explore: boolean;
  setMode: (mode: LearnerMode) => void;
  toggle: () => void;
}

const ModeContext = createContext<ModeContextValue | null>(null);

function readStoredMode(): LearnerMode {
  // Guided is the default for everyone. A learner who has chosen Explore keeps
  // it, but nobody is dropped into professional density without asking.
  try {
    return window.localStorage.getItem(STORAGE_KEY) === "explore" ? "explore" : "guided";
  } catch {
    return "guided";
  }
}

export function ModeProvider({ children }: { children: ReactNode }) {
  const [mode, setModeState] = useState<LearnerMode>(readStoredMode);

  useEffect(() => {
    try {
      window.localStorage.setItem(STORAGE_KEY, mode);
    } catch {
      // A blocked storage API must not break the lesson; the preference simply
      // does not survive a reload.
    }
    document.documentElement.dataset.mode = mode;
  }, [mode]);

  const setMode = useCallback((next: LearnerMode) => setModeState(next), []);
  const toggle = useCallback(
    () => setModeState((current) => (current === "guided" ? "explore" : "guided")),
    [],
  );

  const value = useMemo<ModeContextValue>(
    () => ({ mode, guided: mode === "guided", explore: mode === "explore", setMode, toggle }),
    [mode, setMode, toggle],
  );
  return <ModeContext.Provider value={value}>{children}</ModeContext.Provider>;
}

export function useMode(): ModeContextValue {
  const value = useContext(ModeContext);
  if (!value) throw new Error("useMode must be used inside ModeProvider");
  return value;
}
