import { useRef, useCallback } from "react";

/**
 * Prevents duplicate submissions by guarding against rapid clicks.
 * Uses a ref (not state) to avoid the race window between click and setState.
 */
export function useSubmitGuard() {
  const submittingRef = useRef(false);

  const guard = useCallback(
    async <T>(fn: () => Promise<T>): Promise<T | undefined> => {
      if (submittingRef.current) return undefined;
      submittingRef.current = true;
      try {
        return await fn();
      } finally {
        submittingRef.current = false;
      }
    },
    []
  );

  return { guard };
}
