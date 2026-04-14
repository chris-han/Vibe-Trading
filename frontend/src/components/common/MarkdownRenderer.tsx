import { Suspense, lazy, type ReactNode } from "react";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import rehypeHighlight from "rehype-highlight";
import { cn } from "@/lib/utils";

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

type CodeProps = React.ComponentPropsWithoutRef<"code"> & {
  inline?: boolean;
  children?: ReactNode;
};

function flattenText(node: ReactNode): string {
  if (typeof node === "string" || typeof node === "number") {
    return String(node);
  }
  if (Array.isArray(node)) {
    return node.map(flattenText).join("");
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
      <Suspense
        fallback={
          <div className="my-4 overflow-hidden rounded-2xl border border-border bg-muted/40 p-4 text-sm text-muted-foreground">
            Loading Mermaid diagram...
          </div>
        }
      >
        <LazyMermaidBlock chart={source} />
      </Suspense>
    );
  }

  if (!inline && typeof className === "string" && /(?:^|\s)language-vchart(?:\s|$)/.test(className)) {
    return (
      <Suspense
        fallback={
          <div className="my-4 overflow-hidden rounded-card border border-border bg-muted/40 p-4 text-sm text-muted-foreground">
            Loading chart...
          </div>
        }
      >
        <LazyVChartBlock config={source} />
      </Suspense>
    );
  }

  return (
    <code className={className} {...props}>
      {children}
    </code>
  );
}

/** Strip the <pre> wrapper when the child is a rich block (mermaid / vchart). */
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
      /(?:^|\s)language-(?:mermaid|vchart)(?:\s|$)/.test(childClass)
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
