import { memo, useState, useCallback } from "react";
import { User, XCircle, RefreshCw, Copy, Check, Download } from "lucide-react";
import { formatTimestamp } from "@/lib/formatters";
import type { AgentMessage } from "@/types/agent";
import { AgentAvatar } from "./AgentAvatar";
import { RunCompleteCard } from "./RunCompleteCard";
import { MarkdownRenderer } from "@/components/common/MarkdownRenderer";
import { markdownProseClass } from "@/components/common/markdownStyles";

function CopyButton({ text }: { text: string }) {
  const [copied, setCopied] = useState(false);
  const handleCopy = useCallback(() => {
    navigator.clipboard.writeText(text).then(() => {
      setCopied(true);
      setTimeout(() => setCopied(false), 1500);
    });
  }, [text]);
  return (
    <button
      onClick={handleCopy}
      className="p-1.5 rounded-button bg-muted/80 hover:bg-muted text-muted-foreground hover:text-foreground transition-opacity"
      title={copied ? "Copied" : "Copy"}
    >
      {copied ? <Check className="h-3.5 w-3.5 text-success" /> : <Copy className="h-3.5 w-3.5" />}
    </button>
  );
}

function DownloadButton({ text, filename }: { text: string; filename?: string }) {
  const handleDownload = useCallback(() => {
    const blob = new Blob([text], { type: "text/markdown;charset=utf-8" });
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = filename || `message_${new Date().toISOString().slice(0, 10)}.md`;
    a.click();
    URL.revokeObjectURL(url);
  }, [text, filename]);
  return (
    <button
      onClick={handleDownload}
      className="p-1.5 rounded-button bg-muted/80 hover:bg-muted text-muted-foreground hover:text-foreground transition-opacity"
      title="Download"
    >
      <Download className="h-3.5 w-3.5" />
    </button>
  );
}

function getRetryHint(content: string): string {
  const lower = content.toLowerCase();
  if (lower.includes("timeout") || lower.includes("timed out")) {
    return "Execution timed out. Try simplifying the strategy or reducing the number of assets.";
  }
  if (lower.includes("api") || lower.includes("rate limit") || lower.includes("429") || lower.includes("500") || lower.includes("502") || lower.includes("503")) {
    return "API call failed. Please retry later.";
  }
  return "Execution failed. Click to retry.";
}

interface Props {
  msg: AgentMessage;
  onRetry?: (msg: AgentMessage) => void;
}

export const MessageBubble = memo(function MessageBubble({ msg, onRetry }: Props) {
  const ts = msg.timestamp ? formatTimestamp(msg.timestamp) : null;

  if (msg.type === "user") {
    return (
      <div className="flex justify-end gap-3 group">
        <div className="relative min-w-0 max-w-[72%] rounded-card rounded-tr-sm bg-primary text-primary-foreground px-4 py-2.5 text-sm leading-relaxed whitespace-pre-wrap break-words break-all overflow-hidden">
          <div className="absolute top-1.5 right-1.5 flex items-center gap-1 opacity-0 group-hover:opacity-100 transition-opacity">
            <CopyButton text={msg.content} />
            <DownloadButton text={msg.content} filename={`user_message_${new Date(msg.timestamp).toISOString().slice(0, 10)}.md`} />
          </div>
          {msg.content}
          {ts && <span className="block text-[9px] opacity-70 text-right mt-1">{ts}</span>}
        </div>
        <div className="h-8 w-8 rounded-full border border-border/70 bg-transparent flex items-center justify-center shrink-0 mt-0.5">
          <User className="h-4 w-4 text-muted-foreground" />
        </div>
      </div>
    );
  }

  if (msg.type === "answer") {
    return (
      <div className="flex gap-3 group">
        <AgentAvatar />
        <div className="flex-1 min-w-0 relative">
          <div className="absolute top-2 right-2 flex items-center gap-1 opacity-0 group-hover:opacity-100 transition-opacity">
            <CopyButton text={msg.content} />
            <DownloadButton text={msg.content} filename={`assistant_message_${new Date(msg.timestamp).toISOString().slice(0, 10)}.md`} />
          </div>
          <div className={markdownProseClass("chat")}>
            <MarkdownRenderer>{msg.content}</MarkdownRenderer>
          </div>
          {ts && <span className="text-[9px] text-muted-foreground/50 mt-1 opacity-0 group-hover:opacity-100 transition-opacity">{ts}</span>}
        </div>
      </div>
    );
  }

  if (msg.type === "run_complete" && msg.runId) {
    return <RunCompleteCard msg={msg} />;
  }

  if (msg.type === "error") {
    const hint = getRetryHint(msg.content);
    return (
      <div className="flex gap-3">
        <AgentAvatar />
        <div className="space-y-2">
          <div className="flex items-start gap-2 rounded-card border border-destructive/30 bg-destructive/10 px-4 py-3">
            <XCircle className="h-4 w-4 text-destructive shrink-0 mt-0.5" />
            <p className="min-w-0 text-sm text-destructive leading-relaxed break-words break-all whitespace-pre-wrap">{msg.content}</p>
          </div>
          {onRetry && (
            <button
              onClick={() => onRetry(msg)}
              className="flex items-center gap-1.5 px-3 py-1.5 rounded-button text-xs text-muted-foreground hover:text-foreground hover:bg-muted transition-all"
              title={hint}
            >
              <RefreshCw className="h-3 w-3" />
              <span>{hint}</span>
            </button>
          )}
        </div>
      </div>
    );
  }

  // Fallback: show content for any unhandled message type
  if (msg.content) {
    return (
      <div className="flex gap-3">
        <AgentAvatar />
        <p className="min-w-0 text-sm text-muted-foreground leading-relaxed break-words break-all whitespace-pre-wrap">{msg.content}</p>
      </div>
    );
  }

  return null;
});
