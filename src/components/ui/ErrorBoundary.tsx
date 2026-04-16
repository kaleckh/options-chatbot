"use client";

import React from "react";
import { AlertTriangle, RefreshCw } from "lucide-react";

interface ErrorBoundaryProps {
  children: React.ReactNode;
  fallback?: React.ReactNode;
}

interface ErrorBoundaryState {
  hasError: boolean;
  error: Error | null;
}

export default class ErrorBoundary extends React.Component<
  ErrorBoundaryProps,
  ErrorBoundaryState
> {
  constructor(props: ErrorBoundaryProps) {
    super(props);
    this.state = { hasError: false, error: null };
  }

  static getDerivedStateFromError(error: Error): ErrorBoundaryState {
    return { hasError: true, error };
  }

  componentDidCatch(error: Error, info: React.ErrorInfo) {
    console.error("ErrorBoundary caught:", error, info.componentStack);
  }

  render() {
    if (this.state.hasError) {
      if (this.props.fallback) return this.props.fallback;

      return (
        <div
          role="alert"
          className="flex flex-col items-center justify-center p-8 mx-auto max-w-md mt-16"
        >
          <div className="w-12 h-12 rounded-full bg-red-dim flex items-center justify-center mb-4">
            <AlertTriangle size={24} className="text-red" />
          </div>
          <h2 className="text-lg font-semibold text-text-0 mb-2">
            Something went wrong
          </h2>
          <p className="text-sm text-text-2 text-center mb-4">
            An unexpected error occurred. Try refreshing or click below to
            recover.
          </p>
          {process.env.NODE_ENV === "development" && this.state.error && (
            <pre className="text-xs text-red bg-bg-3 border border-border rounded p-3 mb-4 max-w-full overflow-auto">
              {this.state.error.message}
            </pre>
          )}
          <button
            type="button"
            onClick={() => this.setState({ hasError: false, error: null })}
            className="flex items-center gap-2 px-4 py-2 rounded-md bg-accent text-white text-sm font-medium hover:bg-accent/80 focus-visible:outline focus-visible:outline-2 focus-visible:outline-accent focus-visible:outline-offset-2 transition-colors"
          >
            <RefreshCw size={14} />
            Try Again
          </button>
        </div>
      );
    }

    return this.props.children;
  }
}
