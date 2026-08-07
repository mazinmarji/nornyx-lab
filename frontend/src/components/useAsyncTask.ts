import { useCallback, useEffect, useRef, useState } from "react";
import { toErrorMessage } from "../api/client";

export function useAsyncTask<T>() {
  const [data, setData] = useState<T | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const generation = useRef(0);
  const activeController = useRef<AbortController | null>(null);
  const mounted = useRef(true);

  useEffect(() => {
    mounted.current = true;
    return () => {
      mounted.current = false;
      generation.current += 1;
      activeController.current?.abort();
    };
  }, []);

  const run = useCallback(async (task: (signal: AbortSignal) => Promise<T>) => {
    activeController.current?.abort();
    const controller = new AbortController();
    activeController.current = controller;
    const requestGeneration = ++generation.current;
    setLoading(true);
    setError(null);
    // A new request invalidates the previous result. If it fails, keeping old
    // evidence on screen would look like a fallback for the changed inputs.
    setData(null);
    try {
      const result = await task(controller.signal);
      if (!mounted.current || controller.signal.aborted || requestGeneration !== generation.current) {
        return null;
      }
      setData(result);
      return result;
    } catch (caught) {
      if (!mounted.current || controller.signal.aborted || requestGeneration !== generation.current) {
        return null;
      }
      setData(null);
      setError(toErrorMessage(caught));
      return null;
    } finally {
      if (mounted.current && requestGeneration === generation.current) {
        activeController.current = null;
        setLoading(false);
      }
    }
  }, []);

  const clear = useCallback(() => {
    generation.current += 1;
    activeController.current?.abort();
    activeController.current = null;
    setData(null);
    setError(null);
    setLoading(false);
  }, []);

  return { data, loading, error, run, clear, setData };
}
