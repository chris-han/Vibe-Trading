import { create } from "zustand";
import { api, type SessionItem } from "@/lib/api";

interface SessionsState {
  sessions: SessionItem[];
  loading: boolean;
  loadSessions: () => Promise<void>;
  setSessions: (sessions: SessionItem[]) => void;
  upsertSession: (session: SessionItem) => void;
  patchSession: (sessionId: string, patch: Partial<SessionItem>) => void;
  removeSessions: (sessionIds: string[]) => void;
  renameSession: (sessionId: string, title: string) => void;
}

export const useSessionsStore = create<SessionsState>((set) => ({
  sessions: [],
  loading: false,

  loadSessions: async () => {
    set({ loading: true });
    try {
      const list = await api.listSessions();
      set({ sessions: Array.isArray(list) ? list : [] });
    } catch {
      set({ sessions: [] });
    } finally {
      set({ loading: false });
    }
  },

  setSessions: (sessions) => set({ sessions }),

  upsertSession: (session) =>
    set((state) => {
      const idx = state.sessions.findIndex((s) => s.session_id === session.session_id);
      if (idx === -1) return { sessions: [session, ...state.sessions] };
      return {
        sessions: state.sessions.map((s) => (s.session_id === session.session_id ? { ...s, ...session } : s)),
      };
    }),

  patchSession: (sessionId, patch) =>
    set((state) => {
      const idx = state.sessions.findIndex((s) => s.session_id === sessionId);
      if (idx === -1) return state;
      const next = state.sessions.map((s) => (s.session_id === sessionId ? { ...s, ...patch } : s));
      const updated = next[idx];
      return {
        sessions: [updated, ...next.slice(0, idx), ...next.slice(idx + 1)],
      };
    }),

  removeSessions: (sessionIds) =>
    set((state) => ({
      sessions: state.sessions.filter((s) => !sessionIds.includes(s.session_id)),
    })),

  renameSession: (sessionId, title) =>
    set((state) => ({
      sessions: state.sessions.map((s) => (s.session_id === sessionId ? { ...s, title } : s)),
    })),
}));
