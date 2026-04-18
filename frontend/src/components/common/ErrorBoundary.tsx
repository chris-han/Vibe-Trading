import { Component, type ReactNode } from "react";
import { isRouteErrorResponse, useRouteError } from "react-router-dom";
import { AlertTriangle, Home, RefreshCcw, RotateCw } from "lucide-react";
import { cn } from "@/lib/utils";

type BoundaryFallbackArgs = {
  error?: Error;
  isChunkLoadError: boolean;
  reset: () => void;
};

type BoundaryFallback = ReactNode | ((args: BoundaryFallbackArgs) => ReactNode);

interface Props {
  children: ReactNode;
  fallback?: BoundaryFallback;
  layout?: "inline" | "page";
}

interface State {
  hasError: boolean;
  error?: Error;
}

export function normalizeError(error: unknown): Error | undefined {
  if (error instanceof Error) {
    return error;
  }

  if (typeof error === "string") {
    return new Error(error);
  }

  if (error && typeof error === "object" && "message" in error && typeof error.message === "string") {
    return new Error(error.message);
  }

  return undefined;
}

export function isChunkLoadError(error: unknown): boolean {
  const message = normalizeError(error)?.message?.toLowerCase() ?? "";
  return (
    message.includes("failed to fetch dynamically imported module")
    || message.includes("importing a module script failed")
    || message.includes("chunkloaderror")
    || message.includes("loading chunk")
  );
}

function getErrorDetail(error: unknown): string {
  return normalizeError(error)?.message?.trim() || "Unexpected application error";
}

type ErrorPanelProps = {
  title: string;
  message: string;
  detail?: string;
  layout?: "inline" | "page";
  onRetry?: () => void;
  retryLabel?: string;
  onReload?: () => void;
  reloadLabel?: string;
  showHomeLink?: boolean;
};

export function ErrorPanel({
  title,
  message,
  detail,
  layout = "inline",
  onRetry,
  retryLabel = "Try again",
  onReload,
  reloadLabel = "Reload app",
  showHomeLink = layout === "page",
}: ErrorPanelProps) {
  const isPage = layout === "page";

  return (
    <div
      className={cn(
        isPage
          ? "flex min-h-[100svh] items-center justify-center bg-[radial-gradient(circle_at_top,_hsl(var(--primary)/0.18),_transparent_42%),linear-gradient(180deg,_hsl(var(--background)),_hsl(var(--muted)/0.55))] px-6 py-10"
          : "my-4"
      )}
    >
      <div
        className={cn(
          "overflow-hidden border border-border/80 bg-card text-card-foreground shadow-[0_24px_80px_rgba(14,15,12,0.12)]",
          isPage ? "w-full max-w-2xl rounded-[32px]" : "rounded-card"
        )}
      >
        <div className={cn(isPage ? "p-8 sm:p-10" : "p-4")}> 
          <div className="flex items-start gap-4">
            <div className="flex h-12 w-12 shrink-0 items-center justify-center rounded-2xl bg-destructive/10 text-destructive">
              <AlertTriangle className="h-6 w-6" />
            </div>
            <div className="min-w-0 flex-1">
              <p className="text-xs font-semibold uppercase tracking-[0.24em] text-muted-foreground">
                Application Error
              </p>
              <h1 className={cn("mt-2 font-semibold text-foreground", isPage ? "text-3xl" : "text-base")}>{title}</h1>
              <p className={cn("mt-2 max-w-xl text-muted-foreground", isPage ? "text-base leading-7" : "text-sm leading-6")}>{message}</p>
            </div>
          </div>

          {detail ? (
            <div className="mt-6 rounded-2xl border border-border bg-muted/55 p-4">
              <p className="text-xs font-semibold uppercase tracking-[0.18em] text-muted-foreground">Details</p>
              <p className="mt-2 break-words font-mono text-xs leading-6 text-foreground/85">{detail}</p>
            </div>
          ) : null}

          <div className="mt-6 flex flex-wrap items-center gap-3">
            {onReload ? (
              <button
                type="button"
                onClick={onReload}
                className="inline-flex items-center gap-2 rounded-button bg-primary px-4 py-2.5 text-sm font-medium text-primary-foreground transition-transform hover:scale-[1.02]"
              >
                <RefreshCcw className="h-4 w-4" />
                {reloadLabel}
              </button>
            ) : null}
            {onRetry ? (
              <button
                type="button"
                onClick={onRetry}
                className="inline-flex items-center gap-2 rounded-button border border-border bg-background px-4 py-2.5 text-sm font-medium text-foreground transition-colors hover:bg-muted"
              >
                <RotateCw className="h-4 w-4" />
                {retryLabel}
              </button>
            ) : null}
            {showHomeLink ? (
              <a
                href="/"
                className="inline-flex items-center gap-2 rounded-button border border-border bg-background px-4 py-2.5 text-sm font-medium text-foreground transition-colors hover:bg-muted"
              >
                <Home className="h-4 w-4" />
                Back to home
              </a>
            ) : null}
          </div>
        </div>
      </div>
    </div>
  );
}

function renderBoundaryFallback(error: Error | undefined, layout: "inline" | "page", reset: () => void) {
  const chunkFailure = isChunkLoadError(error);

  return (
    <ErrorPanel
      layout={layout}
      title={chunkFailure ? "A newer frontend build is available" : "This view crashed"}
      message={
        chunkFailure
          ? "This tab is still pointing at an older JavaScript chunk that is no longer being served. Reload the app to sync with the latest frontend build."
          : "The app hit an unexpected error while rendering this section. You can retry this view or return to a safe screen."
      }
      detail={getErrorDetail(error)}
      onRetry={chunkFailure ? undefined : reset}
      onReload={() => window.location.reload()}
      showHomeLink={layout === "page"}
    />
  );
}

export class ErrorBoundary extends Component<Props, State> {
  state: State = { hasError: false };

  static getDerivedStateFromError(error: Error): State {
    return { hasError: true, error };
  }

  componentDidCatch(error: Error) {
    console.error("ErrorBoundary caught an error", error);
  }

  reset = () => {
    this.setState({ hasError: false, error: undefined });
  };

  render() {
    if (this.state.hasError) {
      if (typeof this.props.fallback === "function") {
        return this.props.fallback({
          error: this.state.error,
          isChunkLoadError: isChunkLoadError(this.state.error),
          reset: this.reset,
        });
      }

      if (this.props.fallback) {
        return this.props.fallback;
      }

      return renderBoundaryFallback(this.state.error, this.props.layout ?? "inline", this.reset);
    }

    return this.props.children;
  }
}

export function RouteErrorElement() {
  const routeError = useRouteError();
  const routeFailure = isRouteErrorResponse(routeError);
  const chunkFailure = isChunkLoadError(routeError);
  const detail = routeFailure
    ? `${routeError.status} ${routeError.statusText}`.trim()
    : getErrorDetail(routeError);

  return (
    <ErrorPanel
      layout="page"
      title={chunkFailure ? "The app updated while this page was open" : "This page could not be loaded"}
      message={
        chunkFailure
          ? "A lazy-loaded frontend module is missing because this tab is out of sync with the current build. Reloading will fetch the latest page shell and assets."
          : routeFailure
            ? "The router failed while loading this route. You can go back home or retry from a fresh page load."
            : "An unexpected error interrupted this route before it could render normally."
      }
      detail={detail}
      onReload={() => window.location.reload()}
      showHomeLink
    />
  );
}
