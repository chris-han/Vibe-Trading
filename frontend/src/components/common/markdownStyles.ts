import { cn } from "@/lib/utils";

const baseMarkdownProseClass =
  "prose prose-sm dark:prose-invert max-w-none leading-relaxed text-foreground break-words overflow-hidden " +
  "prose-table:border prose-table:border-border prose-th:bg-muted/50 prose-th:px-3 prose-th:py-1.5 " +
  "prose-td:px-3 prose-td:py-1.5 prose-th:text-left prose-th:text-xs prose-th:font-medium prose-td:text-xs " +
  "[&_pre]:overflow-auto [&_pre]:rounded-md [&_pre]:border [&_pre]:border-border [&_pre]:p-3 " +
  "[&_pre]:bg-muted [&_pre]:text-foreground [&_pre_code]:text-foreground [&_code]:text-[11px] " +
  "[&_pre:has(.vchart-block)]:bg-transparent [&_pre:has(.vchart-block)]:border-0 [&_pre:has(.vchart-block)]:p-0 " +
  "[&_pre:has(.mermaid-block)]:bg-transparent [&_pre:has(.mermaid-block)]:border-0 [&_pre:has(.mermaid-block)]:p-0";

export function markdownProseClass(variant: "chat" | "report" = "report") {
  return cn(
    baseMarkdownProseClass,
    variant === "report" && "report rounded-xl border border-border bg-card p-4",
    variant === "chat" && "min-w-0"
  );
}
