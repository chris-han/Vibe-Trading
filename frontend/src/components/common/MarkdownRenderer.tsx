import { Suspense, lazy, type ReactNode } from "react";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import rehypeHighlight from "rehype-highlight";

const remarkPlugins = [remarkGfm];
const rehypePlugins = [rehypeHighlight];
const LazyMermaidBlock = lazy(async () => {
  const module = await import("./MermaidBlock");
  return { default: module.MermaidBlock };
});

const LazyEChartsBlock = lazy(async () => {
  const module = await import("./EChartsBlock");
  return { default: module.EChartsBlock };
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

  if (!inline && typeof className === "string" && /(?:^|\s)language-echarts(?:\s|$)/.test(className)) {
    return (
      <Suspense
        fallback={
          <div className="my-4 overflow-hidden rounded-card border border-border bg-muted/40 p-4 text-sm text-muted-foreground">
            Loading chart...
          </div>
        }
      >
        <LazyEChartsBlock config={source} />
      </Suspense>
    );
  }

  return (
    <code className={className} {...props}>
      {children}
    </code>
  );
}

export function MarkdownRenderer({ children }: { children: string }) {
  return (
    <ReactMarkdown
      remarkPlugins={remarkPlugins}
      rehypePlugins={rehypePlugins}
      components={{ code: MarkdownCode }}
    >
      {children}
    </ReactMarkdown>
  );
}