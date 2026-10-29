import { useCallback, useEffect, useRef, useState } from "react";

import {
  ApiError,
  type AssistantInfo,
  checkReady,
  getInfo,
  type HistoryMessage,
  type Source,
  streamChat,
} from "./api";
import { Composer } from "./components/Composer";
import { EmptyState } from "./components/EmptyState";
import { MenuIcon, PlusIcon } from "./components/Icons";
import { KnowledgeBase } from "./components/KnowledgeBase";
import { MessageView } from "./components/MessageView";
import { Sidebar } from "./components/Sidebar";
import { SourcePanel } from "./components/SourcePanel";
import {
  type Conversation,
  loadConversations,
  type Message,
  newId,
  saveConversations,
  titleFrom,
} from "./storage";

type Backend = "checking" | "ready" | "degraded" | "offline";

/** Completed turns before the new prompt, in the shape the API expects. */
function toHistory(messages: Message[]): HistoryMessage[] {
  return messages
    .filter((m) => m.content && (m.role === "user" || m.status === "done"))
    .map((m) => ({ role: m.role, content: m.content }));
}

export default function App() {
  const [conversations, setConversations] = useState<Conversation[]>(loadConversations);
  const [activeId, setActiveId] = useState<string | null>(null);
  const [input, setInput] = useState("");
  const [busy, setBusy] = useState(false);
  const [info, setInfo] = useState<AssistantInfo | null>(null);
  const [backend, setBackend] = useState<Backend>("checking");
  const [sidebarOpen, setSidebarOpen] = useState(false);
  const [useKnowledgeBase, setUseKnowledgeBase] = useState(true);
  const [openSource, setOpenSource] = useState<Source | null>(null);
  const [kbOpen, setKbOpen] = useState(false);

  const abortRef = useRef<AbortController | null>(null);
  const scrollRef = useRef<HTMLDivElement>(null);
  const stickToBottom = useRef(true);

  const active = conversations.find((c) => c.id === activeId) ?? null;

  useEffect(() => {
    checkReady()
      .then((r) => setBackend(r.status === "ok" ? "ready" : "degraded"))
      .catch(() => setBackend("offline"));
    getInfo()
      .then(setInfo)
      .catch(() => setInfo(null));
  }, []);

  useEffect(() => saveConversations(conversations), [conversations]);

  // Follow the stream unless the user has scrolled up to read.
  useEffect(() => {
    const el = scrollRef.current;
    if (el && stickToBottom.current) el.scrollTop = el.scrollHeight;
  }, [active?.messages]);

  const updateMessage = useCallback(
    (convId: string, msgId: string, fn: (m: Message) => Message) => {
      setConversations((cs) =>
        cs.map((c) =>
          c.id === convId
            ? { ...c, messages: c.messages.map((m) => (m.id === msgId ? fn(m) : m)) }
            : c,
        ),
      );
    },
    [],
  );

  async function send(prompt: string, prior: Message[], conv: Conversation) {
    const userMsg: Message = { id: newId(), role: "user", content: prompt, status: "done" };
    const botMsg: Message = { id: newId(), role: "assistant", content: "", status: "streaming" };
    const next: Conversation = {
      ...conv,
      title: conv.messages.length ? conv.title : titleFrom(prompt),
      updatedAt: Date.now(),
      messages: [...prior, userMsg, botMsg],
    };
    setConversations((cs) => [next, ...cs.filter((c) => c.id !== conv.id)]);
    setActiveId(conv.id);
    setBusy(true);
    stickToBottom.current = true;

    const controller = new AbortController();
    abortRef.current = controller;
    try {
      const result = await streamChat(
        prompt,
        toHistory(prior),
        useKnowledgeBase,
        {
          onSources: (retrieval, sources) =>
            updateMessage(conv.id, botMsg.id, (m) => ({ ...m, retrieval, sources })),
          onDelta: (text) =>
            updateMessage(conv.id, botMsg.id, (m) => ({ ...m, content: m.content + text })),
        },
        controller.signal,
      );
      const { answer, sources, citations, retrieval, ...meta } = result;
      updateMessage(conv.id, botMsg.id, (m) => ({
        ...m,
        content: answer, // citation-checked final text replaces the streamed draft
        status: "done",
        retrieval,
        sources,
        citations,
        meta,
      }));
    } catch (err) {
      if (controller.signal.aborted) {
        updateMessage(conv.id, botMsg.id, (m) => ({ ...m, status: "stopped" }));
      } else {
        const error =
          err instanceof ApiError
            ? err.message
            : "Couldn't reach the backend. Is it running on port 8000?";
        updateMessage(conv.id, botMsg.id, (m) => ({ ...m, status: "error", error }));
      }
    } finally {
      abortRef.current = null;
      setBusy(false);
    }
  }

  function submit(text = input) {
    const prompt = text.trim();
    if (!prompt || busy) return;
    setInput("");
    const conv = active ?? { id: newId(), title: "", updatedAt: Date.now(), messages: [] };
    void send(prompt, conv.messages, conv);
  }

  function retry() {
    if (!active || busy) return;
    const msgs = active.messages;
    const lastUser = msgs.map((m) => m.role).lastIndexOf("user");
    if (lastUser === -1) return;
    void send(msgs[lastUser].content, msgs.slice(0, lastUser), active);
  }

  function newChat() {
    abortRef.current?.abort();
    setActiveId(null);
    setInput("");
    setSidebarOpen(false);
  }

  function deleteConversation(id: string) {
    if (id === activeId) newChat();
    setConversations((cs) => cs.filter((c) => c.id !== id));
  }

  const statusLabel =
    backend === "ready"
      ? (info?.model ?? "connected")
      : backend === "checking"
        ? "connecting…"
        : backend === "degraded"
          ? "database unavailable"
          : "backend offline";

  return (
    <div className="app">
      <Sidebar
        conversations={[...conversations].sort((a, b) => b.updatedAt - a.updatedAt)}
        activeId={activeId}
        open={sidebarOpen}
        onSelect={(id) => {
          setActiveId(id);
          setSidebarOpen(false);
        }}
        onNew={newChat}
        onDelete={deleteConversation}
        onOpenKnowledgeBase={() => {
          setKbOpen(true);
          setSidebarOpen(false);
        }}
      />
      {sidebarOpen && <div className="scrim" onClick={() => setSidebarOpen(false)} />}

      <main className="main">
        <header className="topbar">
          <button
            type="button"
            className="icon-button mobile-only"
            onClick={() => setSidebarOpen(true)}
            aria-label="Open sidebar"
          >
            <MenuIcon />
          </button>
          <div className="topbar-title">{active?.title || "New conversation"}</div>
          <div className="topbar-right">
            {info?.demo_mode && <span className="badge badge-warn">Demo mode</span>}
            <span className={`status status-${backend}`} title={`Backend: ${backend}`}>
              <span className="status-dot" />
              {statusLabel}
            </span>
            <button
              type="button"
              className="icon-button mobile-only"
              onClick={newChat}
              aria-label="New chat"
            >
              <PlusIcon />
            </button>
          </div>
        </header>

        {info?.demo_mode && (
          <div className="banner">
            <strong>No language model connected.</strong> Answers are placeholders. Set{" "}
            <code>OPENAI_API_KEY</code> (or <code>LLM_API_KEY</code> in <code>.env</code>) and
            restart the backend.
          </div>
        )}

        <div
          className="scroll"
          ref={scrollRef}
          onScroll={(e) => {
            const el = e.currentTarget;
            stickToBottom.current = el.scrollHeight - el.scrollTop - el.clientHeight < 80;
          }}
        >
          {active && active.messages.length > 0 ? (
            <div className="thread">
              {active.messages.map((m, i) => (
                <MessageView
                  key={m.id}
                  message={m}
                  isLast={i === active.messages.length - 1}
                  onRetry={retry}
                  onOpenSource={setOpenSource}
                />
              ))}
            </div>
          ) : (
            <EmptyState onPick={(p) => submit(p)} />
          )}
        </div>

        <Composer
          value={input}
          onChange={setInput}
          onSubmit={() => submit()}
          onStop={() => abortRef.current?.abort()}
          busy={busy}
          disabled={backend === "offline"}
          useKnowledgeBase={useKnowledgeBase}
          onToggleKnowledgeBase={() => setUseKnowledgeBase((v) => !v)}
        />
      </main>

      <SourcePanel source={openSource} onClose={() => setOpenSource(null)} />
      <KnowledgeBase open={kbOpen} onClose={() => setKbOpen(false)} />
    </div>
  );
}
