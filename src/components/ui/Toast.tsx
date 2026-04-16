"use client";

import {
  createContext,
  useContext,
  useState,
  useCallback,
  useMemo,
  useEffect,
  useRef,
} from "react";
import { CheckCircle2, AlertCircle, Info, X } from "lucide-react";

type ToastVariant = "success" | "error" | "info";

interface ToastItem {
  id: number;
  message: string;
  variant: ToastVariant;
}

interface ToastContextValue {
  success: (message: string) => void;
  error: (message: string) => void;
  info: (message: string) => void;
}

const ToastContext = createContext<ToastContextValue | null>(null);

let nextId = 0;

export function ToastProvider({ children }: { children: React.ReactNode }) {
  const [toasts, setToasts] = useState<ToastItem[]>([]);

  const addToast = useCallback((message: string, variant: ToastVariant) => {
    const id = nextId++;
    setToasts((prev) => [...prev, { id, message, variant }]);
  }, []);

  const removeToast = useCallback((id: number) => {
    setToasts((prev) => prev.filter((t) => t.id !== id));
  }, []);

  const success = useCallback((msg: string) => addToast(msg, "success"), [addToast]);
  const error = useCallback((msg: string) => addToast(msg, "error"), [addToast]);
  const info = useCallback((msg: string) => addToast(msg, "info"), [addToast]);

  const value: ToastContextValue = useMemo(
    () => ({ success, error, info }),
    [success, error, info]
  );

  return (
    <ToastContext.Provider value={value}>
      {children}
      <div
        aria-live="polite"
        aria-label="Notifications"
        className="fixed bottom-4 right-4 z-50 flex flex-col gap-2 max-w-sm"
      >
        {toasts.map((toast) => (
          <ToastItem
            key={toast.id}
            toast={toast}
            id={toast.id}
            removeToast={removeToast}
          />
        ))}
      </div>
    </ToastContext.Provider>
  );
}

function ToastItem({
  toast,
  id,
  removeToast,
}: {
  toast: ToastItem;
  id: number;
  removeToast: (id: number) => void;
}) {
  const timerRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const onDismiss = useCallback(() => removeToast(id), [id, removeToast]);

  useEffect(() => {
    timerRef.current = setTimeout(onDismiss, 4000);
    return () => {
      if (timerRef.current) {
        clearTimeout(timerRef.current);
      }
    };
  }, [onDismiss]);

  const Icon =
    toast.variant === "success"
      ? CheckCircle2
      : toast.variant === "error"
      ? AlertCircle
      : Info;

  const borderColor =
    toast.variant === "success"
      ? "border-l-green"
      : toast.variant === "error"
      ? "border-l-red"
      : "border-l-accent";

  const iconColor =
    toast.variant === "success"
      ? "text-green"
      : toast.variant === "error"
      ? "text-red"
      : "text-accent";

  return (
    <div
      role="status"
      className={`flex items-start gap-3 bg-bg-3 border border-border ${borderColor} border-l-2 rounded-lg p-3 shadow-lg shadow-black/40 animate-in slide-in-from-right`}
    >
      <Icon size={16} className={`${iconColor} flex-shrink-0 mt-0.5`} />
      <p className="text-sm text-text-1 flex-1">{toast.message}</p>
      <button
        type="button"
        onClick={onDismiss}
        aria-label="Dismiss notification"
        className="text-text-3 hover:text-text-1 transition-colors flex-shrink-0"
      >
        <X size={14} />
      </button>
    </div>
  );
}

export function useToast(): ToastContextValue {
  const ctx = useContext(ToastContext);
  if (!ctx) {
    throw new Error("useToast must be used within a ToastProvider");
  }
  return ctx;
}
