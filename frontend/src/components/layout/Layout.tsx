import { useEffect, useState } from "react";
import { Link, Outlet, useLocation, useSearchParams } from "react-router-dom";
import { BarChart3, Bot, Moon, Sun, Plus, Trash2, Pencil, MessageSquare, ChevronsLeft, ChevronsRight, FileJson, Download } from "lucide-react";
import { cn } from "@/lib/utils";
import { useI18n } from "@/lib/i18n";
import { useDarkMode } from "@/hooks/useDarkMode";
import { api } from "@/lib/api";
import { useAgentStore } from "@/stores/agent";
import { useSessionsStore } from "@/stores/sessions";
import { ConnectionBanner } from "@/components/layout/ConnectionBanner";

const NAV = [
  { to: "/", icon: BarChart3, key: "home" as const },
  { to: "/agent", icon: Bot, key: "agent" as const },
];

export function Layout() {
  const { pathname } = useLocation();
  const [searchParams] = useSearchParams();
  const { t } = useI18n();
  const { dark, toggle } = useDarkMode();
  const sessions = useSessionsStore((s) => s.sessions);
  const sessionsLoading = useSessionsStore((s) => s.loading);
  const loadSessions = useSessionsStore((s) => s.loadSessions);
  const removeSessions = useSessionsStore((s) => s.removeSessions);
  const updateSessionTitle = useSessionsStore((s) => s.renameSession);
  const sseStatus = useAgentStore(s => s.sseStatus);
  const sseRetryAttempt = useAgentStore(s => s.sseRetryAttempt);
  const [collapsed, setCollapsed] = useState(() => localStorage.getItem("qa-sidebar") === "collapsed");

  const activeSessionId = searchParams.get("session");

  useEffect(() => {
    localStorage.setItem("qa-sidebar", collapsed ? "collapsed" : "expanded");
  }, [collapsed]);

  // Load sessions on mount. Also refresh when navigating TO /agent or when
  // the active session changes (covers new session creation from Agent).
  const isAgentPage = pathname.startsWith("/agent");
  useEffect(() => { loadSessions(); }, [loadSessions, isAgentPage, activeSessionId]);

  const [deleteTarget, setDeleteTarget] = useState<string | null>(null);
  const [renameTarget, setRenameTarget] = useState<string | null>(null);
  const [renameValue, setRenameValue] = useState("");

  const deleteSession = async (sid: string) => {
    try {
      const result = await api.deleteSessions([sid]);
      removeSessions(result.deleted);
    } catch { /* ignore */ }
    setDeleteTarget(null);
  };

  const renameSession = async (sid: string) => {
    if (!renameValue.trim()) { setRenameTarget(null); return; }
    try {
      await api.renameSession(sid, renameValue.trim());
      updateSessionTitle(sid, renameValue.trim());
    } catch { /* ignore */ }
    setRenameTarget(null);
  };

  return (
    <div className="flex h-screen bg-background">
      {/* Sidebar with warm neutral styling */}
      <aside className={cn(
        "border-r border-border bg-card flex flex-col shrink-0 transition-all duration-200",
        collapsed ? "w-12" : "w-64"
      )}>
        {/* Brand */}
        <div className={cn("border-b border-border", collapsed ? "p-2 flex justify-center" : "p-4")}>
          <Link to="/" className={cn("flex items-center font-bold text-base text-foreground", collapsed ? "justify-center" : "gap-2")}>
            <div className="h-8 w-8 rounded-full bg-wise-green flex items-center justify-center shrink-0">
              <BarChart3 className="h-4 w-4 text-dark-green" />
            </div>
            {!collapsed && "Vibe-Trading"}
          </Link>
        </div>

        {/* Nav with Wise-inspired styling */}
        <nav className={cn("space-y-1", collapsed ? "p-1" : "p-2")}>
          {NAV.map(({ to, icon: Icon, key }) => {
            const isActive = to === "/" ? pathname === "/" : pathname.startsWith(to);
            return (
              <Link
                key={to}
                to={to}
                className={cn(
                  "flex items-center rounded-button text-sm font-medium transition-all duration-150",
                  collapsed ? "justify-center p-2" : "gap-3 px-3 py-2.5",
                  isActive
                    ? "bg-primary text-primary-foreground"
                    : "text-muted-foreground hover:bg-muted hover:text-foreground hover:scale-[1.02]"
                )}
                title={collapsed ? t[key] : undefined}
              >
                <Icon className={cn("h-4 w-4 shrink-0", isActive && "text-primary-foreground")} />
                {!collapsed && t[key]}
              </Link>
            );
          })}
        </nav>

        {/* Sessions — hidden when collapsed */}
        {!collapsed && (
          <div className="flex-1 overflow-hidden border-t border-border mt-2 flex flex-col">
            {/* Section Header */}
            <div className="flex items-center justify-between px-4 py-3">
              <span className="flex items-center gap-1.5 text-xs font-medium text-muted-foreground">
                <MessageSquare className="h-3.5 w-3.5" />
                {t.sessions}
              </span>
              <div className="flex items-center gap-2">
                <Link
                  to={activeSessionId ? `/session-events?session=${activeSessionId}` : "/session-events"}
                  className="flex items-center gap-1 text-xs text-muted-foreground hover:text-foreground transition-colors"
                  title="Export session events"
                >
                  <Download className="h-3.5 w-3.5" />
                </Link>
                <Link
                  to="/agent"
                  className="flex items-center gap-1 text-xs text-muted-foreground hover:text-foreground transition-colors"
                  title={t.newChat}
                >
                  <Plus className="h-3.5 w-3.5" />
                </Link>
              </div>
            </div>

            {/* Session List */}
            <div className="px-2 pb-2 space-y-0.5 overflow-auto flex-1">
              {sessionsLoading ? (
                <div className="space-y-1.5 px-2 py-1">
                  {[1, 2, 3].map((i) => (
                    <div key={i} className="h-8 rounded bg-muted animate-pulse" />
                  ))}
                </div>
              ) : sessions.length === 0 ? (
                <p className="px-3 py-2 text-xs text-muted-foreground">{t.noSessions}</p>
              ) : null}
              {sessions.map((s) => {
                const isActive = s.session_id === activeSessionId;
                const isDeleting = deleteTarget === s.session_id;
                const isRenaming = renameTarget === s.session_id;
                return (
                  <div
                    key={s.session_id}
                    className={cn(
                      "group relative flex items-center gap-1.5 rounded-sm transition-all duration-150 overflow-hidden",
                      isActive
                        ? "bg-primary text-primary-foreground"
                        : "hover:bg-muted/60 text-muted-foreground"
                    )}
                  >
                    {/* Active indicator - left edge highlight */}
                    {isActive && (
                      <div className="absolute left-0 top-0 bottom-0 w-0.5 bg-dark-green/30" />
                    )}

                    {isRenaming ? (
                      <input
                        autoFocus
                        value={renameValue}
                        onChange={(e) => setRenameValue(e.target.value)}
                        onKeyDown={(e) => { if (e.key === "Enter") renameSession(s.session_id); if (e.key === "Escape") setRenameTarget(null); }}
                        onBlur={() => renameSession(s.session_id)}
                        className="flex-1 min-w-0 px-2 py-1 rounded text-xs border border-primary bg-background text-foreground outline-none"
                      />
                    ) : (
                      <>
                        <Link
                          to={`/agent?session=${s.session_id}`}
                          className={cn(
                            "flex-1 min-w-0 px-2 py-1.5 text-xs transition-colors truncate",
                            isActive ? "text-primary-foreground font-medium" : "group-hover:text-foreground"
                          )}
                          title={s.title || s.session_id}
                        >
                          {s.title || s.session_id.slice(0, 16)}
                        </Link>
                        {!isDeleting ? (
                          <div className={cn(
                            "flex items-center gap-0.5 transition-opacity",
                            isActive ? "opacity-100" : "opacity-0 group-hover:opacity-100"
                          )}>
                            <Link
                              to={`/session-events?session=${s.session_id}`}
                              onClick={(e) => e.stopPropagation()}
                              className={cn(
                                "shrink-0 rounded p-1 transition-colors",
                                isActive
                                  ? "text-primary-foreground/70 hover:text-primary-foreground hover:bg-primary-foreground/10"
                                  : "text-muted-foreground hover:text-foreground hover:bg-muted"
                              )}
                              title="Review events"
                            >
                              <FileJson className="h-3 w-3" />
                            </Link>
                            <button
                              onClick={(e) => { e.preventDefault(); e.stopPropagation(); setRenameTarget(s.session_id); setRenameValue(s.title || ""); }}
                              className={cn(
                                "p-1 rounded transition-colors shrink-0",
                                isActive
                                  ? "text-primary-foreground/70 hover:text-primary-foreground hover:bg-primary-foreground/10"
                                  : "text-muted-foreground hover:text-foreground hover:bg-muted"
                              )}
                              title="Rename"
                            >
                              <Pencil className="h-3 w-3" />
                            </button>
                            <button
                              onClick={(e) => { e.preventDefault(); e.stopPropagation(); setDeleteTarget(s.session_id); }}
                              className={cn(
                                "p-1 rounded transition-colors shrink-0",
                                isActive
                                  ? "text-primary-foreground/70 hover:text-destructive hover:bg-destructive/20"
                                  : "text-muted-foreground hover:text-destructive hover:bg-destructive/10"
                              )}
                              title={t.deleteConfirm}
                            >
                              <Trash2 className="h-3 w-3" />
                            </button>
                          </div>
                        ) : (
                          <div className="flex items-center gap-0.5 shrink-0">
                            <button
                              onClick={() => deleteSession(s.session_id)}
                              className="px-1.5 py-0.5 text-destructive hover:bg-destructive/10 rounded text-[10px] font-medium"
                            >
                              {t.confirmDelete}
                            </button>
                            <button
                              onClick={() => setDeleteTarget(null)}
                              className="px-1.5 py-0.5 text-muted-foreground hover:bg-muted rounded text-[10px]"
                            >
                              {t.cancelDelete}
                            </button>
                          </div>
                        )}
                      </>
                    )}
                  </div>
                );
              })}
            </div>
          </div>
        )}

        {/* Spacer when collapsed */}
        {collapsed && <div className="flex-1" />}

        {/* Footer */}
        <div className={cn("border-t border-border", collapsed ? "p-2 flex flex-col items-center gap-2" : "p-4 space-y-1")}>
          {collapsed ? (
            <>
              <button onClick={toggle} className="p-1.5 text-muted-foreground hover:text-foreground rounded transition-colors" title={dark ? t.lightMode : t.darkMode}>
                {dark ? <Sun className="h-3.5 w-3.5" /> : <Moon className="h-3.5 w-3.5" />}
              </button>
              <button onClick={() => setCollapsed(false)} className="p-1.5 text-muted-foreground hover:text-foreground rounded transition-colors" title="Expand">
                <ChevronsRight className="h-3.5 w-3.5" />
              </button>
            </>
          ) : (
            <>
              <div className="flex items-center justify-between">
                <button
                  onClick={toggle}
                  className="flex items-center gap-1.5 text-xs text-muted-foreground hover:text-foreground transition-colors"
                >
                  {dark ? <Sun className="h-3.5 w-3.5" /> : <Moon className="h-3.5 w-3.5" />}
                  {dark ? t.lightMode : t.darkMode}
                </button>
                <div className="flex items-center gap-1">
                  <button
                    onClick={() => setCollapsed(true)}
                    className="p-1 text-muted-foreground hover:text-foreground rounded transition-colors"
                    title="Collapse"
                  >
                    <ChevronsLeft className="h-3.5 w-3.5" />
                  </button>
                </div>
              </div>
              <p className="text-xs text-muted-foreground">v0.1.0</p>
            </>
          )}
        </div>
      </aside>

      {/* Main */}
      <div className="flex-1 flex flex-col overflow-hidden">
        <ConnectionBanner status={sseStatus} retryAttempt={sseRetryAttempt} />
        <main className="flex-1 overflow-auto">
          <Outlet />
        </main>
      </div>
    </div>
  );
}
