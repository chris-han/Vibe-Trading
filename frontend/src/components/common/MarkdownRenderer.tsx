import { Suspense, lazy, type ReactNode } from "react";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import rehypeHighlight from "rehype-highlight";
import { cn } from "@/lib/utils";
import { ErrorBoundary, ErrorPanel } from "@/components/common/ErrorBoundary";

const remarkPlugins = [remarkGfm];
const rehypePlugins = [rehypeHighlight];
const LazyMermaidBlock = lazy(async () => {
  const module = await import("./MermaidBlock");
  return { default: module.MermaidBlock };
});

const LazyVChartBlock = lazy(async () => {
  const module = await import("./VChartBlock");
  return { default: module.VChartBlock };
});

const LazyEChartsBlock = lazy(async () => {
  const module = await import("./EChartsBlock");
  return { default: module.EChartsBlock };
});

function RichBlockFallback({
  title,
  message,
  source,
  onRetry,
  onReload,
}: {
  title: string;
  message: string;
  source: string;
  onRetry?: () => void;
  onReload?: () => void;
}) {
  return (
    <div className="my-4">
      <ErrorPanel
        title={title}
        message={message}
        detail={source}
        onRetry={onRetry}
        onReload={onReload}
        reloadLabel="Reload page"
      />
    </div>
  );
}

type CodeProps = React.ComponentPropsWithoutRef<"code"> & {
  inline?: boolean;
  children?: ReactNode;
};

function shouldInsertBoundarySpace(left: string, right: string): boolean {
  if (!left || !right) return false;
  const leftChar = left[left.length - 1];
  const rightChar = right[0];
  return /[A-Za-z0-9]/.test(leftChar) && /[A-Za-z0-9]/.test(rightChar);
}

function mergeTextParts(parts: string[]): string {
  let merged = "";
  for (const part of parts) {
    if (!part) continue;
    if (shouldInsertBoundarySpace(merged, part)) {
      merged += " ";
    }
    merged += part;
  }
  return merged;
}

function flattenText(node: ReactNode): string {
  if (typeof node === "string" || typeof node === "number") {
    return String(node);
  }
  if (Array.isArray(node)) {
    return mergeTextParts(node.map(flattenText));
  }
  if (node && typeof node === "object" && "props" in node) {
    return flattenText((node as { props?: { children?: ReactNode } }).props?.children);
  }
  return "";
}

function MarkdownCode({ inline, className, children, ...props }: CodeProps) {
  const source = flattenText(children).replace(/\n$/, "");

  if (!inline && typeof className === "string" && /(?:^|\s)language-mermaid(?:\s|$)/.test(className)) {
    return (
      <ErrorBoundary
        fallback={({ isChunkLoadError, reset }) => (
          <RichBlockFallback
            title={isChunkLoadError ? "Mermaid renderer is out of date" : "Mermaid diagram failed to load"}
            message={
              isChunkLoadError
                ? "This page is referencing an older Mermaid bundle. Reload the page to fetch the current frontend assets."
                : "The diagram renderer crashed while loading. You can retry this block without losing the rest of the page."
            }
            source={source}
            onRetry={isChunkLoadError ? undefined : reset}
            onReload={() => window.location.reload()}
          />
        )}
      >
        <Suspense
          fallback={
            <div className="my-4 overflow-hidden rounded-2xl border border-border bg-muted/40 p-4 text-sm text-muted-foreground">
              Loading Mermaid diagram...
            </div>
          }
        >
          <LazyMermaidBlock chart={source} />
        </Suspense>
      </ErrorBoundary>
    );
  }

  if (!inline && typeof className === "string" && /(?:^|\s)language-(?:vchart|chart)(?:\s|$)/.test(className)) {
    return (
      <ErrorBoundary
        fallback={({ isChunkLoadError, reset }) => (
          <RichBlockFallback
            title={isChunkLoadError ? "Chart bundle is out of date" : "Chart failed to load"}
            message={
              isChunkLoadError
                ? "The current page shell no longer matches the chart bundle on the server. Reload to resync the app."
                : "This chart renderer failed, but the rest of the report is still available."
            }
            source={source}
            onRetry={isChunkLoadError ? undefined : reset}
            onReload={() => window.location.reload()}
          />
        )}
      >
        <Suspense
          fallback={
            <div className="my-4 overflow-hidden rounded-card border border-border bg-muted/40 p-4 text-sm text-muted-foreground">
              Loading chart...
            </div>
          }
        >
          <LazyVChartBlock config={source} />
        </Suspense>
      </ErrorBoundary>
    );
  }

  if (!inline && typeof className === "string" && /(?:^|\s)language-echarts(?:\s|$)/.test(className)) {
    return (
      <ErrorBoundary
        fallback={({ isChunkLoadError, reset }) => (
          <RichBlockFallback
            title={isChunkLoadError ? "Chart bundle is out of date" : "Chart failed to load"}
            message={
              isChunkLoadError
                ? "This page references a stale chart chunk. Reload to fetch the latest build."
                : "The chart renderer crashed while loading. Retry this block or reload the page if the problem persists."
            }
            source={source}
            onRetry={isChunkLoadError ? undefined : reset}
            onReload={() => window.location.reload()}
          />
        )}
      >
        <Suspense
          fallback={
            <div className="my-4 overflow-hidden rounded-card border border-border bg-muted/40 p-4 text-sm text-muted-foreground">
              Loading chart...
            </div>
          }
        >
          <LazyEChartsBlock config={source} />
        </Suspense>
      </ErrorBoundary>
    );
  }

  return (
    <code className={className} {...props}>
      {children}
    </code>
  );
}

/** Strip the <pre> wrapper when the child is a rich block (mermaid / vchart / echarts). */
function MarkdownPre({ children, className, ...props }: React.ComponentPropsWithoutRef<"pre"> & { children?: ReactNode }) {
  // ReactMarkdown renders <pre><code class="language-*">…</code></pre>.
  // MarkdownCode is called first and returns <Suspense> for vchart/mermaid blocks,
  // so by the time MarkdownPre runs, `children` is a <Suspense> element (not a <code>).
  // We strip <pre> for any non-DOM component child (Suspense, lazy components) OR if
  // the child's className directly matches a rich-block language class.
  if (children && typeof children === "object" && !Array.isArray(children) && "props" in children) {
    const child = children as React.ReactElement<{ className?: string }>;
    const childClass = String(child.props?.className || "");
    if (
      typeof child.type !== "string" ||
      /(?:^|\s)language-(?:mermaid|vchart|chart|echarts)(?:\s|$)/.test(childClass)
    ) {
      return <>{children}</>;
    }
  }
  return (
    <pre
      className={cn(
        "overflow-x-auto whitespace-pre break-normal",
        "[&_code]:whitespace-pre [&_code]:break-normal [&_code]:font-mono",
        className
      )}
      {...props}
    >
      {children}
    </pre>
  );
}

export function MarkdownRenderer({ children }: { children: string }) {
  return (
    <ReactMarkdown
      remarkPlugins={remarkPlugins}
      rehypePlugins={rehypePlugins}
      components={{ code: MarkdownCode, pre: MarkdownPre }}
    >
      {children}
    </ReactMarkdown>
  );
}
