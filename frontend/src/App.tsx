import { useCallback, useEffect, useMemo, useRef, useState } from "react";

import {
  ApiError,
  type AssistantInfo,
  checkReady,
  getInfo,
  type HistoryMessage,
  listDocuments,
  type Source,
  streamChat,
} from "./api";
import { type Command, CommandPalette } from "./components/CommandPalette";
import { Composer } from "./components/Composer";
import { EmptyState } from "./components/EmptyState";
import {
  ArrowDownIcon,
  BookIcon,
  GlobeIcon,
  MenuIcon,
  MonitorIcon,
  MoonIcon,
  PlusIcon,
  SunIcon,
  UploadIcon,
} from "./components/Icons";
import { KnowledgeBase } from "./components/KnowledgeBase";
import { MessageView } from "./components/MessageView";
import { Sidebar } from "./components/Sidebar";
import { SourcePanel } from "./components/SourcePanel";
import { type Toast, Toasts } from "./components/Toasts";
import {
  type Conversation,
  loadConversations,
  type Message,
  newId,
  saveConversations,
  titleFrom,
} from "./storage";
import { useTheme } from "./theme";

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
  const [kbStats, setKbStats] = useState<{ documents: number; passages: number } | null>(null);
  const [sidebarOpen, setSidebarOpen] = useState(false);
  const [useKnowledgeBase, setUseKnowledgeBase] = useState(true);
  const [openSource, setOpenSource] = useState<{ source: Source; total: number } | null>(null);
  const [kbOpen, setKbOpen] = useState(false);
  const [paletteOpen, setPaletteOpen] = useState(false);
  const [toasts, setToasts] = useState<Toast[]>([]);
  const [scrolled, setScrolled] = useState(false);
  const [atBottom, setAtBottom] = useState(true);
  const [theme, setTheme] = useTheme();

  const abortRef = useRef<AbortController | null>(null);
  const scrollRef = useRef<HTMLDivElement>(null);
  const inputRef = useRef<HTMLTextAreaElement>(null);
  const stickToBottom = useRef(true);

  const active = conversations.find((c) => c.id === activeId) ?? null;
  const sorted = useMemo(
    () => [...conversations].sort((a, b) => b.updatedAt - a.updatedAt),
    [conversations],
  );

  const notify = useCallback((text: string, kind: Toast["kind"] = "success") => {
    const id = Date.now() + Math.random();
    setToasts((t) => [...t, { id, text, kind }]);
    setTimeout(() => setToasts((t) => t.filter((x) => x.id !== id)), 3200);
  }, []);

  const refreshStats = useCallback(() => {
    listDocuments()
      .then((docs) =>
        setKbStats({
          documents: docs.length,
          passages: docs.reduce((n, d) => n + d.chunk_count, 0),
        }),
      )
      .catch(() => setKbStats(null));
  }, []);

  useEffect(() => {
    checkReady()
      .then((r) => setBackend(r.status === "ok" ? "ready" : "degraded"))
      .catch(() => setBackend("offline"));
    getInfo()
      .then(setInfo)
      .catch(() => setInfo(null));
    refreshStats();
  }, [refreshStats]);

  useEffect(() => saveConversations(conversations), [conversations]);

  // Follow the stream unless the user has scrolled up to read.
  useEffect(() => {
    const el = scrollRef.current;
    if (!el) return;
    if (!active?.messages.length) el.scrollTop = 0; // empty state: start at the top
    else if (stickToBottom.current) el.scrollTop = el.scrollHeight;
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
    const kb = useKnowledgeBase;
    const userMsg: Message = { id: newId(), role: "user", content: prompt, status: "done" };
    const botMsg: Message = {
      id: newId(),
      role: "assistant",
      content: "",
      status: "streaming",
      kb,
    };
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
    setAtBottom(true);

    const controller = new AbortController();
    abortRef.current = controller;
    try {
      const result = await streamChat(
        prompt,
        toHistory(prior),
        kb,
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

  function submit(text = input, fresh = false) {
    const prompt = text.trim();
    if (!prompt || busy) return;
    setInput("");
    const base = fresh ? null : active;
    const conv = base ?? { id: newId(), title: "", updatedAt: Date.now(), messages: [] };
    void send(prompt, conv.messages, conv);
  }

  function retry() {
    if (!active || busy) return;
    const msgs = active.messages;
    const lastUser = msgs.map((m) => m.role).lastIndexOf("user");
    if (lastUser === -1) return;
    void send(msgs[lastUser].content, msgs.slice(0, lastUser), active);
  }

  const newChat = useCallback(() => {
    abortRef.current?.abort();
    setActiveId(null);
    setInput("");
    setSidebarOpen(false);
    setTimeout(() => inputRef.current?.focus(), 0);
  }, []);

  function deleteConversation(id: string) {
    if (id === activeId) newChat();
    setConversations((cs) => cs.filter((c) => c.id !== id));
    notify("Conversation deleted");
  }

  // Global shortcuts: ⌘/Ctrl+K command palette, "/" focuses the composer.
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if ((e.metaKey || e.ctrlKey) && e.key.toLowerCase() === "k") {
        e.preventDefault();
        setPaletteOpen((v) => !v);
      } else if (e.key === "/" && !(e.target instanceof HTMLElement && e.target.closest("input, textarea"))) {
        e.preventDefault();
        inputRef.current?.focus();
      }
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, []);

  const commands: Command[] = useMemo(
    () => [
      { id: "new", label: "New chat", icon: <PlusIcon width={15} height={15} />, run: newChat },
      {
        id: "kb",
        label: "Open knowledge base",
        icon: <BookIcon width={15} height={15} />,
        run: () => setKbOpen(true),
      },
      {
        id: "upload",
        label: "Upload a document",
        icon: <UploadIcon width={15} height={15} />,
        run: () => setKbOpen(true),
      },
      {
        id: "mode",
        label: useKnowledgeBase ? "Switch to general answers" : "Switch to company documents",
        icon: useKnowledgeBase ? <GlobeIcon width={15} height={15} /> : <BookIcon width={15} height={15} />,
        run: () => setUseKnowledgeBase((v) => !v),
      },
      { id: "light", label: "Theme: light", icon: <SunIcon width={15} height={15} />, run: () => setTheme("light") },
      { id: "dark", label: "Theme: dark", icon: <MoonIcon width={15} height={15} />, run: () => setTheme("dark") },
      {
        id: "system",
        label: "Theme: match system",
        icon: <MonitorIcon width={15} height={15} />,
        run: () => setTheme("system"),
      },
    ],
    [newChat, setTheme, useKnowledgeBase],
  );

  const statusLabel =
    backend === "ready"
      ? (info?.model ?? "connected")
      : backend === "checking"
        ? "connecting…"
        : backend === "degraded"
          ? "database unavailable"
          : "backend offline";

  const hasThread = active !== null && active.messages.length > 0;
  const composer = (variant: "hero" | "dock") => (
    <Composer
      variant={variant}
      inputRef={inputRef}
      value={input}
      onChange={setInput}
      onSubmit={() => submit()}
      onStop={() => abortRef.current?.abort()}
      onAttach={() => setKbOpen(true)}
      busy={busy}
      disabled={backend === "offline"}
      useKnowledgeBase={useKnowledgeBase}
      onKnowledgeBaseChange={setUseKnowledgeBase}
      model={info?.model}
    />
  );

  return (
    <div className="app">
      <Sidebar
        conversations={sorted}
        activeId={activeId}
        open={sidebarOpen}
        documentCount={kbStats?.documents ?? null}
        groups={info?.user_groups ?? []}
        theme={theme}
        onTheme={setTheme}
        onSelect={(id) => {
          setActiveId(id);
          setSidebarOpen(false);
          stickToBottom.current = true;
        }}
        onNew={newChat}
        onDelete={deleteConversation}
        onOpenKnowledgeBase={() => {
          setKbOpen(true);
          setSidebarOpen(false);
        }}
        onOpenPalette={() => {
          setPaletteOpen(true);
          setSidebarOpen(false);
        }}
      />
      {sidebarOpen && <div className="scrim" onClick={() => setSidebarOpen(false)} />}

      <main className="main">
        <header className={`topbar ${scrolled ? "scrolled" : ""}`}>
          <button
            type="button"
            className="icon-button mobile-only"
            onClick={() => setSidebarOpen(true)}
            aria-label="Open sidebar"
          >
            <MenuIcon />
          </button>
          <div className="topbar-title">{hasThread ? active?.title : ""}</div>
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
            <strong>No language model connected.</strong> Retrieval works, but answers are
            placeholders. Set <code>OPENAI_API_KEY</code> (or <code>LLM_API_KEY</code> in{" "}
            <code>.env</code>) and restart the backend.
          </div>
        )}

        <div
          className="scroll"
          ref={scrollRef}
          onScroll={(e) => {
            const el = e.currentTarget;
            const bottom = el.scrollHeight - el.scrollTop - el.clientHeight < 80;
            stickToBottom.current = bottom;
            setAtBottom(bottom);
            setScrolled(el.scrollTop > 4);
          }}
        >
          {hasThread ? (
            <div className="thread">
              {active.messages.map((m, i) => (
                <MessageView
                  key={m.id}
                  message={m}
                  isLast={i === active.messages.length - 1}
                  onRetry={retry}
                  onOpenSource={(source) =>
                    setOpenSource({ source, total: m.sources?.length ?? 0 })
                  }
                  onCopied={() => notify("Answer copied")}
                />
              ))}
            </div>
          ) : (
            <EmptyState
              onPick={(p) => submit(p)}
              composer={composer("hero")}
              stats={kbStats}
              embeddingModel={info?.embedding_model}
            />
          )}
        </div>

        {hasThread && !atBottom && (
          <button
            type="button"
            className="scroll-bottom"
            aria-label="Jump to latest"
            onClick={() => {
              const el = scrollRef.current;
              if (el) el.scrollTo({ top: el.scrollHeight, behavior: "smooth" });
            }}
          >
            <ArrowDownIcon width={16} height={16} />
          </button>
        )}

        {hasThread && composer("dock")}
      </main>

      <SourcePanel
        source={openSource?.source ?? null}
        total={openSource?.total ?? 0}
        onClose={() => setOpenSource(null)}
      />
      <KnowledgeBase
        open={kbOpen}
        onClose={() => setKbOpen(false)}
        onChanged={refreshStats}
        notify={notify}
      />
      <CommandPalette
        open={paletteOpen}
        onClose={() => setPaletteOpen(false)}
        commands={commands}
        conversations={sorted}
        onSelectConversation={(id) => {
          setActiveId(id);
          stickToBottom.current = true;
        }}
        onAsk={(q) => submit(q, true)}
      />
      <Toasts toasts={toasts} />
    </div>
  );
}
