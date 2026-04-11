import { useEffect, useMemo, useState } from "react";
import { Link, useSearchParams } from "react-router-dom";
import { ArrowUpDown, Download, FileJson, RefreshCw, Trash2 } from "lucide-react";
import { toast } from "sonner";
import { api, type SessionEventItem, type SessionTrajectoryExport } from "@/lib/api";
import { useSessionsStore } from "@/stores/sessions";

function downloadJsonl(filename: string, lines: unknown[]) {
  const body = lines.map((line) => JSON.stringify(line)).join("\n") + "\n";
  const blob = new Blob([body], { type: "application/x-ndjson;charset=utf-8" });
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = filename;
  a.click();
  URL.revokeObjectURL(url);
}

function formatEventBody(event: SessionEventItem): string {
  if (event.reasoning) return event.reasoning;
  if (event.content) return event.content;
  if (event.args) return JSON.stringify(event.args, null, 2);
  if (event.metadata) return JSON.stringify(event.metadata, null, 2);
  return "";
}

export function SessionEvents() {
  const [searchParams, setSearchParams] = useSearchParams();
  const sessionId = searchParams.get("session") || "";
  const sessions = useSessionsStore((s) => s.sessions);
  const sessionsLoading = useSessionsStore((s) => s.loading);
  const loadSessions = useSessionsStore((s) => s.loadSessions);
  const removeSessions = useSessionsStore((s) => s.removeSessions);
  const [events, setEvents] = useState<SessionEventItem[]>([]);
  const [trajectory, setTrajectory] = useState<SessionTrajectoryExport | null>(null);
  const [selectedSessionIds, setSelectedSessionIds] = useState<string[]>([]);
  const [showSchema, setShowSchema] = useState(false);
  const [timestampSort, setTimestampSort] = useState<"desc" | "asc">("desc");
  const [showDeleteModal, setShowDeleteModal] = useState(false);
  const [deleting, setDeleting] = useState(false);
  const [loading, setLoading] = useState(false);

  const canonicalSchema = useMemo(() => ({
    event_id: "string",
    session_id: "string",
    attempt_id: "string | null",
    event_type: [
      "message.created",
      "assistant.delta",
      "assistant.reasoning",
      "tool.call",
      "tool.result",
      "tool.progress",
      "attempt.created",
      "attempt.started",
      "attempt.completed",
      "attempt.failed",
    ],
    timestamp: "ISO-8601 string",
    role: '"user" | "assistant" | "tool" | "system" | null',
    content: "string | null",
    reasoning: "string | null",
    tool: "string | null",
    tool_call_id: "string | null",
    args: "Record<string, unknown> | null",
    status: "string | null",
    metadata: "Record<string, unknown>",
  }), []);

  useEffect(() => {
    loadSessions();
  }, [loadSessions]);

  useEffect(() => {
    setSelectedSessionIds((prev) => prev.filter((id) => sessions.some((session) => session.session_id === id)));
  }, [sessions]);

  useEffect(() => {
    if (!sessionId) return;
    if (sessionsLoading) return;
    if (sessions.some((session) => session.session_id === sessionId)) return;
    setSearchParams({});
    setEvents([]);
    setTrajectory(null);
  }, [sessionId, sessions, sessionsLoading, setSearchParams]);

  useEffect(() => {
    if (!sessionId) return;
    setSelectedSessionIds((prev) => (prev.includes(sessionId) ? prev : [sessionId, ...prev]));
  }, [sessionId]);

  useEffect(() => {
    if (!sessionId) {
      setEvents([]);
      setTrajectory(null);
      return;
    }
    setLoading(true);
    Promise.all([
      api.getSessionEvents(sessionId),
      api.getSessionTrajectory(sessionId),
    ]).then(([eventItems, exportData]) => {
      setEvents(eventItems);
      setTrajectory(exportData);
    }).catch(() => {
      setEvents([]);
      setTrajectory(null);
    }).finally(() => setLoading(false));
  }, [sessionId]);

  const counts = useMemo(() => {
    const byType: Record<string, number> = {};
    for (const event of events) byType[event.event_type] = (byType[event.event_type] || 0) + 1;
    return byType;
  }, [events]);

  const selectedSessions = useMemo(
    () => sessions.filter((session) => selectedSessionIds.includes(session.session_id)),
    [sessions, selectedSessionIds]
  );

  const sortedSessions = useMemo(() => {
    const copy = [...sessions];
    copy.sort((a, b) => {
      const aTs = Date.parse(a.updated_at || a.created_at || "") || 0;
      const bTs = Date.parse(b.updated_at || b.created_at || "") || 0;
      return timestampSort === "desc" ? bTs - aTs : aTs - bTs;
    });
    return copy;
  }, [sessions, timestampSort]);

  const toggleSession = (sid: string) => {
    setSelectedSessionIds((prev) => (
      prev.includes(sid) ? prev.filter((id) => id !== sid) : [...prev, sid]
    ));
  };

  const toggleAllSessions = () => {
    setSelectedSessionIds((prev) => (
      prev.length === sessions.length ? [] : sessions.map((session) => session.session_id)
    ));
  };

  const toggleTimestampSort = () => {
    setTimestampSort((prev) => (prev === "desc" ? "asc" : "desc"));
  };

  const exportTrajectory = async () => {
    if (selectedSessionIds.length === 0) return;
    try {
      const exports = await Promise.all(selectedSessionIds.map((sid) => api.getSessionTrajectory(sid)));
      const name = selectedSessionIds.length === 1
        ? `${selectedSessionIds[0]}_atropos_trajectory.jsonl`
        : `selected_sessions_atropos_trajectory.jsonl`;
      downloadJsonl(name, exports.map((item) => item.trajectory));
      toast.success("Atropos JSONL exported");
    } catch (err) {
      toast.error(err instanceof Error ? err.message : "Trajectory export failed");
    }
  };

  const exportEvents = async () => {
    if (selectedSessionIds.length === 0) return;
    try {
      const eventGroups = await Promise.all(selectedSessionIds.map((sid) => api.getSessionEvents(sid)));
      const lines = eventGroups.flat();
      const name = selectedSessionIds.length === 1
        ? `${selectedSessionIds[0]}_events.jsonl`
        : `selected_sessions_events.jsonl`;
      downloadJsonl(name, lines);
      toast.success("Event log exported");
    } catch (err) {
      toast.error(err instanceof Error ? err.message : "Event export failed");
    }
  };

  const requestDeleteSelectedSessions = () => {
    if (selectedSessionIds.length === 0) return;
    setShowDeleteModal(true);
  };

  const deleteSelectedSessions = async () => {
    if (selectedSessionIds.length === 0) return;
    setDeleting(true);
    const deletingIds = [...selectedSessionIds];
    const result = await api.deleteSessions(deletingIds).catch(() => ({ deleted: [] as string[], missing: deletingIds, status: "error" }));
    const deletedIds = result.deleted || [];
    removeSessions(deletedIds);
    setSelectedSessionIds([]);
    setDeleting(false);
    setShowDeleteModal(false);

    if (sessionId && deletedIds.includes(sessionId)) {
      setSearchParams({});
      setEvents([]);
      setTrajectory(null);
    }
  };

  return (
    <div className="min-h-screen bg-background p-6">
      <div className="mx-auto max-w-7xl space-y-6">
        <div className="flex flex-col gap-4 rounded-card border border-border bg-card p-6 shadow-sm md:flex-row md:items-end md:justify-between">
          <div className="space-y-2">
            <p className="text-xs font-medium uppercase tracking-[0.2em] text-muted-foreground">Session Event Review</p>
            <h1 className="text-3xl font-semibold text-foreground">Canonical `events.jsonl`</h1>
            <p className="max-w-3xl text-sm text-muted-foreground">
              Review the canonical session event log and export the projected Atropos trajectory dataset entry.
            </p>
          </div>
          <div className="flex flex-wrap gap-2">
            <button
              onClick={() => setShowSchema((prev) => !prev)}
              className="inline-flex items-center gap-2 rounded-button border border-border px-3 py-2 text-sm text-foreground hover:bg-muted"
            >
              <FileJson className="h-4 w-4" />
              {showSchema ? "Hide Schema" : "View Schema"}
            </button>
            <button
              onClick={() => sessionId && setSearchParams({ session: sessionId })}
              className="inline-flex items-center gap-2 rounded-button border border-border px-3 py-2 text-sm text-foreground hover:bg-muted"
              disabled={!sessionId || loading}
            >
              <RefreshCw className="h-4 w-4" />
              Refresh
            </button>
          </div>
        </div>

        {showSchema && (
          <section className="rounded-card border border-border bg-card p-4 shadow-sm">
            <div className="mb-3 flex items-center justify-between">
              <div>
                <h2 className="text-sm font-semibold text-foreground">Canonical Schema</h2>
                <p className="text-xs text-muted-foreground">`SessionEvent` append-only record shape.</p>
              </div>
            </div>
            <pre className="overflow-auto whitespace-pre-wrap break-words rounded-md bg-muted/40 p-3 text-[11px] text-foreground">
              {JSON.stringify(canonicalSchema, null, 2)}
            </pre>
          </section>
        )}

        <div className="grid gap-6 lg:grid-cols-[320px,1fr]">
          <section className="rounded-card border border-border bg-card p-4 shadow-sm">
            <div className="mb-3 flex items-center justify-between gap-3">
              <div className="flex items-center gap-2">
                <h2 className="text-sm font-semibold text-foreground">Sessions</h2>
                <span className="text-xs text-muted-foreground">{sessions.length}</span>
              </div>
              <div className="flex flex-wrap items-center gap-2">
                <button
                  onClick={requestDeleteSelectedSessions}
                  className="inline-flex h-10 w-10 items-center justify-center rounded-button border border-destructive/30 text-destructive hover:bg-destructive/10"
                  disabled={selectedSessionIds.length === 0}
                  title="Delete Selected"
                  aria-label="Delete Selected"
                >
                  <Trash2 className="h-4 w-4" />
                </button>
                <button
                  onClick={exportEvents}
                  className="inline-flex h-10 w-10 items-center justify-center rounded-button border border-border bg-muted/30 text-foreground hover:bg-muted"
                  disabled={selectedSessionIds.length === 0}
                  title="Export Events"
                  aria-label="Export Events"
                >
                  <FileJson className="h-4 w-4" />
                </button>
                <button
                  onClick={exportTrajectory}
                  className="inline-flex h-10 w-10 items-center justify-center rounded-button border border-border bg-muted/30 text-foreground hover:bg-muted"
                  disabled={selectedSessionIds.length === 0}
                  title="Export Atropos JSONL"
                  aria-label="Export Atropos JSONL"
                >
                  <Download className="h-4 w-4" />
                </button>
              </div>
            </div>
            <div className="overflow-hidden rounded-button border border-border">
              <table className="w-full table-fixed border-collapse text-left text-sm">
                <thead className="bg-muted/50 text-xs uppercase tracking-wide text-muted-foreground">
                  <tr>
                    <th className="w-10 px-3 py-2">
                      <input
                        type="checkbox"
                        checked={sessions.length > 0 && selectedSessionIds.length === sessions.length}
                        onChange={toggleAllSessions}
                        className="h-4 w-4 rounded border-border"
                        aria-label="Select all sessions"
                      />
                    </th>
                    <th className="px-3 py-2">Title</th>
                    <th className="px-3 py-2">Session ID</th>
                    <th className="px-3 py-2">
                      <button
                        type="button"
                        onClick={toggleTimestampSort}
                        className="inline-flex items-center gap-1 text-xs uppercase tracking-wide text-muted-foreground hover:text-foreground"
                      >
                        Timestamp
                        <ArrowUpDown className="h-3 w-3" />
                      </button>
                    </th>
                  </tr>
                </thead>
                <tbody>
                  {sortedSessions.map((session) => {
                    const active = session.session_id === sessionId;
                    const selected = selectedSessionIds.includes(session.session_id);
                    const timestamp = session.updated_at || session.created_at || "";
                    return (
                      <tr
                        key={session.session_id}
                        onClick={() => setSearchParams({ session: session.session_id })}
                        className={`cursor-pointer border-t border-border transition-colors ${
                          active ? "bg-primary/10" : "hover:bg-muted/40"
                        }`}
                      >
                        <td
                          className="px-3 py-3"
                          onClick={(e) => {
                            e.stopPropagation();
                            toggleSession(session.session_id);
                          }}
                        >
                          <input
                            type="checkbox"
                            checked={selected}
                            readOnly
                            className="h-4 w-4 rounded border-border"
                            aria-label={`Select ${session.title || session.session_id}`}
                          />
                        </td>
                        <td className="px-3 py-3">
                          <div className={`truncate font-medium ${active ? "text-primary" : "text-foreground"}`}>
                            {session.title || session.session_id}
                          </div>
                        </td>
                        <td className="px-3 py-3 text-xs text-muted-foreground">
                          <div className="truncate">{session.session_id}</div>
                        </td>
                        <td className="px-3 py-3 text-xs text-muted-foreground">
                          <div className="truncate">{timestamp ? new Date(timestamp).toLocaleString() : "—"}</div>
                        </td>
                      </tr>
                    );
                  })}
                </tbody>
              </table>
              {sessionsLoading && <p className="p-3 text-sm text-muted-foreground">Loading sessions...</p>}
              {!sessionsLoading && sessions.length === 0 && <p className="p-3 text-sm text-muted-foreground">No sessions found.</p>}
            </div>
          </section>

          <div className="space-y-6">
            <section className="rounded-card border border-border bg-card p-4 shadow-sm">
              <div className="mb-4 flex items-center justify-between">
                <div>
                  <h2 className="text-sm font-semibold text-foreground">Summary</h2>
                  <p className="text-xs text-muted-foreground">
                    {sessionId || "Select a session"}
                    {selectedSessions.length > 0 ? ` · ${selectedSessions.length} selected` : ""}
                  </p>
                </div>
                {trajectory && (
                  <Link to={`/agent?session=${trajectory.session_id}`} className="text-sm text-primary hover:underline">
                    Open Chat
                  </Link>
                )}
              </div>
              {loading ? (
                <p className="text-sm text-muted-foreground">Loading canonical events...</p>
              ) : !sessionId ? (
                <p className="text-sm text-muted-foreground">Select a session to inspect its event log.</p>
              ) : (
                <div className="grid gap-3 md:grid-cols-3">
                  <div className="rounded-button border border-border p-3">
                    <div className="text-xs uppercase tracking-wide text-muted-foreground">Events</div>
                    <div className="mt-1 text-2xl font-semibold text-foreground">{events.length}</div>
                  </div>
                  <div className="rounded-button border border-border p-3 md:col-span-2">
                    <div className="text-xs uppercase tracking-wide text-muted-foreground">Event Types</div>
                    <div className="mt-2 flex flex-wrap gap-2">
                      {Object.entries(counts).map(([type, count]) => (
                        <span key={type} className="rounded-full bg-muted px-2.5 py-1 text-xs text-foreground">
                          {type} {count}
                        </span>
                      ))}
                      {Object.keys(counts).length === 0 && <span className="text-sm text-muted-foreground">No events recorded.</span>}
                    </div>
                  </div>
                </div>
              )}
            </section>

            <section className="grid gap-6 xl:grid-cols-2">
              <div className="rounded-card border border-border bg-card p-4 shadow-sm">
                <h2 className="mb-3 text-sm font-semibold text-foreground">Event Log</h2>
                <div className="max-h-[70vh] space-y-3 overflow-auto pr-1">
                  {events.map((event) => (
                    <div key={event.event_id} className="rounded-button border border-border p-3">
                      <div className="flex items-center justify-between gap-3">
                        <div className="text-xs font-medium text-foreground">{event.event_type}</div>
                        <div className="text-[11px] text-muted-foreground">{new Date(event.timestamp).toLocaleString()}</div>
                      </div>
                      <div className="mt-1 text-[11px] text-muted-foreground">
                        {event.attempt_id ? `attempt ${event.attempt_id}` : "session event"}
                        {event.tool ? ` · tool ${event.tool}` : ""}
                        {event.status ? ` · ${event.status}` : ""}
                      </div>
                      {formatEventBody(event) && (
                        <pre className="mt-2 whitespace-pre-wrap break-words rounded-md bg-muted/40 p-2 text-[11px] text-foreground">
                          {formatEventBody(event)}
                        </pre>
                      )}
                    </div>
                  ))}
                  {!loading && sessionId && events.length === 0 && <p className="text-sm text-muted-foreground">No events for this session.</p>}
                </div>
              </div>

              <div className="rounded-card border border-border bg-card p-4 shadow-sm">
                <h2 className="mb-3 text-sm font-semibold text-foreground">Atropos Projection</h2>
                <div className="max-h-[70vh] overflow-auto">
                  <pre className="whitespace-pre-wrap break-words rounded-md bg-muted/40 p-3 text-[11px] text-foreground">
                    {trajectory ? JSON.stringify(trajectory.trajectory, null, 2) : "No trajectory available."}
                  </pre>
                </div>
              </div>
            </section>
          </div>
        </div>
      </div>

      {showDeleteModal && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/40 p-4">
          <div className="w-full max-w-md rounded-card border border-border bg-card p-5 shadow-xl">
            <div className="space-y-2">
              <h2 className="text-lg font-semibold text-foreground">Delete Selected Sessions</h2>
              <p className="text-sm text-muted-foreground">
                Delete {selectedSessionIds.length} selected session{selectedSessionIds.length > 1 ? "s" : ""}?
                This removes the session records and canonical `events.jsonl` data.
              </p>
            </div>
            <div className="mt-5 flex justify-end gap-2">
              <button
                onClick={() => setShowDeleteModal(false)}
                className="rounded-button border border-border px-3 py-2 text-sm text-foreground hover:bg-muted"
                disabled={deleting}
              >
                Cancel
              </button>
              <button
                onClick={deleteSelectedSessions}
                className="rounded-button bg-destructive px-3 py-2 text-sm font-medium text-destructive-foreground hover:bg-destructive/90 disabled:opacity-60"
                disabled={deleting}
              >
                {deleting ? "Deleting..." : "Delete"}
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
