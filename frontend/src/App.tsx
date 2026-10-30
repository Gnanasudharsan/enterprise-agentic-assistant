import { useCallback, useEffect, useMemo, useRef, useState } from "react";

import {
  type AgentHandlers,
  type AgentRun,
  AgentRunError,
  ApiError,
  type AssistantInfo,
  checkReady,
  decideAction,
  getInfo,
  type IssueArguments,
  listTools,
  type ToolInfo,
  type HistoryMessage,
  listDocuments,
  resumeAgent,
  type Source,
  streamAgent,
  streamChat,
} from "./api";
import { ActionsPanel } from "./components/ActionsPanel";
import { type Command, CommandPalette } from "./components/CommandPalette";
import { Composer } from "./components/Composer";
import { EmptyState } from "./components/EmptyState";
import {
  ArrowDownIcon,
  BookIcon,
  GlobeIcon,
  MenuIcon,
  SparkIcon,
  MonitorIcon,
  MoonIcon,
  PlusIcon,
  SunIcon,
  TicketIcon,
  UploadIcon,
} from "./components/Icons";
import { KnowledgeBase } from "./components/KnowledgeBase";
import { MessageView } from "./components/MessageView";
import { Sidebar } from "./components/Sidebar";
import { SourcePanel } from "./components/SourcePanel";
import { TracePanel } from "./components/TracePanel";
import { type Toast, Toasts } from "./components/Toasts";
import {
  type Conversation,
  loadConversations,
  type Message,
  type Mode,
  newId,
  saveConversations,
  titleFrom,
} from "./storage";
import { useTheme } from "./theme";

type Backend = "checking" | "ready" | "degraded" | "offline";

const MODE_KEY = "eaa.mode";

function loadMode(): Mode {
  try {
    const v = localStorage.getItem(MODE_KEY);
    return v === "docs" || v === "general" || v === "agent" ? v : "agent";
  } catch {
    return "agent";
  }
}

function describeError(err: unknown): string {
  return err instanceof ApiError ? err.message : "Couldn't reach the backend. Is it running on port 8000?";
}

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
  const [mode, setMode] = useState<Mode>(loadMode);
  const [traceRun, setTraceRun] = useState<string | null>(null);
  const [tools, setTools] = useState<ToolInfo[]>([]);
  const [actionsOpen, setActionsOpen] = useState(false);
  const [actionsVersion, setActionsVersion] = useState(0);
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
  const pendingActions = conversations.reduce(
    (n, c) =>
      n + c.messages.reduce((k, m) => k + (m.agent?.actions?.filter((a) => a.status === "proposed").length ?? 0), 0),
    0,
  );
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
    listTools()
      .then(setTools)
      .catch(() => setTools([]));
    refreshStats();
  }, [refreshStats]);

  useEffect(() => saveConversations(conversations), [conversations]);
  useEffect(() => {
    try {
      localStorage.setItem(MODE_KEY, mode);
    } catch {
      // Per-viewer convenience only.
    }
  }, [mode]);

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

  /** Live updates of an agent answer, folded into the message as events arrive. */
  function agentHandlers(convId: string, msgId: string): AgentHandlers {
    const patch = (fn: (m: Message) => Message) => updateMessage(convId, msgId, fn);
    const patchAgent = (fn: (a: NonNullable<Message["agent"]>) => Partial<NonNullable<Message["agent"]>>) =>
      patch((m) => {
        const a = m.agent ?? { steps: {}, sql: {} };
        return { ...m, agent: { ...a, ...fn(a) } };
      });
    return {
      onRun: (runId) => patchAgent(() => ({ runId, resumable: false })),
      onPlan: (plan, planStatus) => patchAgent(() => ({ plan, planStatus })),
      onStep: (e) => patchAgent((a) => ({ steps: { ...a.steps, [e.step_id ?? e.node]: e } })),
      onSql: (e) => patchAgent((a) => ({ sql: { ...a.sql, [e.step_id]: e } })),
      onEvidence: (sources, tables) => {
        patch((m) => ({ ...m, sources, retrieval: sources.length ? "used" : "no_results" }));
        patchAgent(() => ({ tables }));
      },
      onAnswerReset: () => patch((m) => ({ ...m, content: "" })),
      onAction: (action) =>
        patchAgent((a) => ({
          actions: [...(a.actions ?? []).filter((x) => x.id !== action.id), action],
        })),
      onDelta: (text) => patch((m) => ({ ...m, content: m.content + text })),
    };
  }

  function finishAgent(convId: string, msgId: string, run: AgentRun) {
    updateMessage(convId, msgId, (m) => ({
      ...m,
      content: run.answer ?? "", // citation-checked final text replaces the streamed draft
      status: "done",
      sources: run.sources,
      citations: run.citations.sources,
      retrieval: run.sources.length ? "used" : "no_results",
      agent: {
        ...(m.agent ?? { steps: {}, sql: {} }),
        runId: run.run_id,
        plan: run.plan ?? undefined,
        tables: run.tables,
        tableCitations: run.citations.tables,
        trace: run.trace,
        latencyMs: run.latency_ms ?? undefined,
        model: run.model,
        invalidCitations: run.invalid_citations,
        resumable: false,
        actions: run.actions,
        awaitingApproval: run.status === "needs_approval",
      },
    }));
    setActionsVersion((v) => v + 1);
  }

  function failAgent(convId: string, msgId: string, err: unknown, aborted: boolean) {
    updateMessage(convId, msgId, (m) =>
      aborted
        ? { ...m, status: "stopped" }
        : {
            ...m,
            status: "error",
            error: describeError(err),
            agent: m.agent && { ...m.agent, resumable: err instanceof AgentRunError && !!err.runId },
          },
    );
  }

  async function send(prompt: string, prior: Message[], conv: Conversation) {
    const sendMode = mode;
    const userMsg: Message = { id: newId(), role: "user", content: prompt, status: "done" };
    const botMsg: Message = {
      id: newId(),
      role: "assistant",
      content: "",
      status: "streaming",
      kb: sendMode !== "general",
      mode: sendMode,
      agent: sendMode === "agent" ? { steps: {}, sql: {} } : undefined,
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
      if (sendMode === "agent") {
        const run = await streamAgent(
          prompt,
          toHistory(prior),
          agentHandlers(conv.id, botMsg.id),
          controller.signal,
        );
        finishAgent(conv.id, botMsg.id, run);
        return;
      }
      const result = await streamChat(
        prompt,
        toHistory(prior),
        sendMode === "docs",
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
      if (sendMode === "agent") failAgent(conv.id, botMsg.id, err, controller.signal.aborted);
      else if (controller.signal.aborted) {
        updateMessage(conv.id, botMsg.id, (m) => ({ ...m, status: "stopped" }));
      } else {
        updateMessage(conv.id, botMsg.id, (m) => ({ ...m, status: "error", error: describeError(err) }));
      }
    } finally {
      abortRef.current = null;
      setBusy(false);
    }
  }

  /** Approve or reject a proposed action; the paused run then continues in this message. */
  async function decide(
    msgId: string,
    actionId: string,
    decision: "approve" | "reject",
    args?: IssueArguments,
  ) {
    const msg = active?.messages.find((m) => m.id === msgId);
    const runId = msg?.agent?.runId;
    if (!active || !runId || busy) return;
    const convId = active.id;
    setBusy(true);
    try {
      const run = await decideAction(
        runId,
        actionId,
        { decision, arguments: args as Record<string, unknown> | undefined },
        agentHandlers(convId, msgId),
      );
      finishAgent(convId, msgId, run);
      const action = run.actions.find((a) => a.id === actionId);
      if (action?.status === "executed") notify(`Created ${action.result?.key ?? "the issue"}`);
      else if (action?.status === "rejected") notify("Action rejected; nothing was created");
      else if (action?.status === "failed") notify(action.error ?? "The action failed", "error");
    } catch (err) {
      notify(describeError(err), "error");
    } finally {
      setBusy(false);
    }
  }

  /** Continue a failed agent run from its last checkpoint, in the same message. */
  async function resume() {
    if (!active || busy) return;
    const msg = active.messages[active.messages.length - 1];
    const runId = msg?.agent?.runId;
    if (!msg || !runId) return;
    const convId = active.id;
    updateMessage(convId, msg.id, (m) => ({ ...m, status: "streaming", error: undefined }));
    setBusy(true);
    const controller = new AbortController();
    abortRef.current = controller;
    try {
      finishAgent(convId, msg.id, await resumeAgent(runId, agentHandlers(convId, msg.id), controller.signal));
    } catch (err) {
      failAgent(convId, msg.id, err, controller.signal.aborted);
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
        id: "actions",
        label: "Open actions & audit log",
        icon: <TicketIcon width={15} height={15} />,
        run: () => setActionsOpen(true),
      },
      { id: "agent", label: "Mode: research agent (documents + data)", icon: <SparkIcon width={15} height={15} />, run: () => setMode("agent") },
      { id: "docs", label: "Mode: company documents only", icon: <BookIcon width={15} height={15} />, run: () => setMode("docs") },
      { id: "general", label: "Mode: general answers", icon: <GlobeIcon width={15} height={15} />, run: () => setMode("general") },
      { id: "light", label: "Theme: light", icon: <SunIcon width={15} height={15} />, run: () => setTheme("light") },
      { id: "dark", label: "Theme: dark", icon: <MoonIcon width={15} height={15} />, run: () => setTheme("dark") },
      {
        id: "system",
        label: "Theme: match system",
        icon: <MonitorIcon width={15} height={15} />,
        run: () => setTheme("system"),
      },
    ],
    [newChat, setTheme],
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
      mode={mode}
      onModeChange={setMode}
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
        pendingActions={pendingActions}
        onOpenActions={() => {
          setActionsOpen(true);
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
                  onOpenTrace={setTraceRun}
                  onResume={resume}
                  onDecide={(actionId, decision, args) => decide(m.id, actionId, decision, args)}
                  tools={tools}
                  busy={busy}
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
      <TracePanel runId={traceRun} onClose={() => setTraceRun(null)} />
      <ActionsPanel
        open={actionsOpen}
        onClose={() => setActionsOpen(false)}
        refreshKey={actionsVersion}
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
