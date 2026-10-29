// Conversations are kept in this browser only (a per-viewer convenience).
// Server-side conversation storage arrives with the agent runtime in Phase 3.

import type { ChatResponse, RetrievalStatus, Source } from "./api";

export interface Message {
  id: string;
  role: "user" | "assistant";
  content: string;
  status?: "streaming" | "done" | "error" | "stopped";
  error?: string;
  retrieval?: RetrievalStatus;
  sources?: Source[];
  citations?: number[];
  meta?: Omit<ChatResponse, "answer" | "sources" | "citations" | "retrieval">;
}

export interface Conversation {
  id: string;
  title: string;
  updatedAt: number;
  messages: Message[];
}

const KEY = "eaa.conversations.v1";
const MAX_CONVERSATIONS = 30;

export function loadConversations(): Conversation[] {
  try {
    const raw = localStorage.getItem(KEY);
    const parsed = raw ? (JSON.parse(raw) as Conversation[]) : [];
    // A reload mid-stream leaves half-finished answers; mark them as stopped.
    return parsed.map((c) => ({
      ...c,
      messages: c.messages.map((m) =>
        m.status === "streaming" ? { ...m, status: "stopped" as const } : m,
      ),
    }));
  } catch {
    return [];
  }
}

export function saveConversations(conversations: Conversation[]): void {
  try {
    const kept = conversations
      .filter((c) => c.messages.length > 0)
      .sort((a, b) => b.updatedAt - a.updatedAt)
      .slice(0, MAX_CONVERSATIONS);
    localStorage.setItem(KEY, JSON.stringify(kept));
  } catch {
    // Storage unavailable (private mode, quota); the app still works in memory.
  }
}

export function newId(): string {
  return crypto.randomUUID();
}

export function titleFrom(prompt: string): string {
  const oneLine = prompt.replace(/\s+/g, " ").trim();
  return oneLine.length > 48 ? `${oneLine.slice(0, 45)}…` : oneLine;
}
