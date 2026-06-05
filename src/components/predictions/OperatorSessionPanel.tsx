"use client";

import { FormEvent, useCallback, useEffect, useState } from "react";
import { LockKeyhole, ShieldCheck } from "lucide-react";
import Button from "@/components/ui/Button";
import { useToast } from "@/components/ui/Toast";
import { fetchWithTimeout, readJsonResponseOrThrow } from "@/lib/client-json";

type OperatorSessionStatus = {
  configured?: boolean;
  authorized?: boolean;
};

type OperatorSessionPanelProps = {
  onUnlocked?: () => void;
};

export function OperatorSessionPanel({ onUnlocked }: OperatorSessionPanelProps) {
  const toast = useToast();
  const [status, setStatus] = useState<OperatorSessionStatus | null>(null);
  const [token, setToken] = useState("");
  const [loading, setLoading] = useState(false);
  const [unlocking, setUnlocking] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const refreshStatus = useCallback(async () => {
    setLoading(true);
    try {
      const response = await fetchWithTimeout("/api/operator/session", undefined, "Operator session");
      const data = await readJsonResponseOrThrow<OperatorSessionStatus>(response, "Operator session");
      setStatus(data);
      setError(null);
    } catch (err) {
      const message = err instanceof Error ? err.message : "Failed to load operator session.";
      setStatus(null);
      setError(message);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    void refreshStatus();
  }, [refreshStatus]);

  const submitUnlock = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    if (!token.trim()) return;
    setUnlocking(true);
    try {
      const response = await fetchWithTimeout("/api/operator/session", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ token }),
      }, "Operator unlock");
      await readJsonResponseOrThrow(response, "Operator unlock");
      setToken("");
      setStatus({ configured: true, authorized: true });
      setError(null);
      toast.success("Operator session opened.");
      onUnlocked?.();
    } catch (err) {
      const message = err instanceof Error ? err.message : "Failed to open operator session.";
      setError(message);
      toast.error(message);
    } finally {
      setUnlocking(false);
    }
  };

  const configured = status?.configured !== false;
  const authorized = Boolean(status?.authorized);

  return (
    <div className="rounded-lg border border-border bg-bg-1 px-4 py-3">
      <div className="flex flex-col gap-3 lg:flex-row lg:items-center lg:justify-between">
        <div className="min-w-0">
          <div className="flex items-center gap-2 text-sm font-semibold text-text-0">
            {authorized ? (
              <ShieldCheck size={15} className="text-green" aria-hidden="true" />
            ) : (
              <LockKeyhole size={15} className="text-amber-200" aria-hidden="true" />
            )}
            <span>Local Operator</span>
            <span className="font-mono text-xs font-normal text-text-2">
              {loading ? "CHECKING" : authorized ? "UNLOCKED" : configured ? "LOCKED" : "NOT CONFIGURED"}
            </span>
          </div>
          <p className="mt-1 text-xs text-text-3">
            Browser mutations use the local operator session; scan and record actions stay blocked until it is open.
          </p>
          {error ? (
            <div className="mt-2 text-xs text-red">
              {error}
            </div>
          ) : null}
        </div>
        {!authorized && configured ? (
          <form onSubmit={submitUnlock} className="flex w-full flex-col gap-2 sm:w-auto sm:flex-row sm:items-center">
            <label className="sr-only" htmlFor="operator-session-token">Operator token</label>
            <input
              id="operator-session-token"
              type="password"
              value={token}
              autoComplete="off"
              onChange={(event) => setToken(event.target.value)}
              className="min-w-[220px] rounded-md border border-border bg-bg-3 px-3 py-2 text-sm text-text-0"
            />
            <Button
              type="submit"
              size="sm"
              variant="secondary"
              loading={unlocking}
              disabled={!token.trim()}
              icon={<LockKeyhole size={12} />}
            >
              Unlock
            </Button>
          </form>
        ) : (
          <Button
            size="sm"
            variant="ghost"
            loading={loading}
            onClick={() => void refreshStatus()}
          >
            Check
          </Button>
        )}
      </div>
    </div>
  );
}
