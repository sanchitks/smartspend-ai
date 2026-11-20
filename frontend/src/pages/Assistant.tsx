import { Calculator, MessageSquarePlus, SendHorizontal, Sparkles, Trash2 } from "lucide-react";
import { useEffect, useRef, useState, type FormEvent } from "react";
import { Link } from "react-router";

import { DraftReview } from "../components/QuickAdd";
import { Button, Card, Dialog, Notice, cx } from "../components/ui";
import { ApiError, api } from "../lib/api";
import { relativeTime } from "../lib/format";
import type { AIStatus, ChatReply, Conversation, ParseResult, StoredMessage } from "../lib/types";
import { useApi } from "../lib/useApi";

type Msg = { id: string; role: "user" | "assistant"; content: string; reply?: Partial<ChatReply>; error?: boolean };

const SUGGESTIONS = [
  "How much did I spend this month?",
  "Which category did I spend most on?",
  "How much is left in my food budget?",
  "Compare this month with last month",
  "What if I cut shopping by 15%?",
  "How do I create a realistic budget?",
];

export function Assistant() {
  const status = useApi<AIStatus>("/ai/status");
  const convos = useApi<Conversation[]>("/ai/conversations");
  const [conversationId, setConversationId] = useState<number | null>(null);
  const [messages, setMessages] = useState<Msg[]>([]);
  const [text, setText] = useState("");
  const [busy, setBusy] = useState(false);
  const [draft, setDraft] = useState<ParseResult | null>(null);
  const [savedDraft, setSavedDraft] = useState(false);
  const endRef = useRef<HTMLDivElement>(null);
  const inputRef = useRef<HTMLTextAreaElement>(null);

  useEffect(() => {
    endRef.current?.scrollIntoView({ block: "end" });
  }, [messages, busy]);

  async function open(id: number) {
    setConversationId(id);
    setSavedDraft(false);
    try {
      const stored = await api<StoredMessage[]>(`/ai/conversations/${id}/messages`);
      setMessages(stored.map((m) => ({ id: String(m.id), role: m.role, content: m.content, reply: m.role === "assistant" ? m.meta : undefined })));
    } catch {
      setMessages([]);
    }
  }

  function startNew() {
    setConversationId(null);
    setMessages([]);
    setSavedDraft(false);
    inputRef.current?.focus();
  }

  async function send(message: string) {
    const clean = message.trim();
    if (!clean || busy) return;
    setText("");
    setSavedDraft(false);
    setMessages((m) => [...m, { id: `u${Date.now()}`, role: "user", content: clean }]);
    setBusy(true);
    try {
      const r = await api<ChatReply>("/ai/chat", { body: { message: clean, conversation_id: conversationId } });
      if (!conversationId) void convos.reload();
      setConversationId(r.conversation_id);
      setMessages((m) => [...m, { id: `a${r.message_id}`, role: "assistant", content: r.answer, reply: r }]);
    } catch (e) {
      setMessages((m) => [
        ...m,
        { id: `e${Date.now()}`, role: "assistant", error: true, content: e instanceof ApiError ? e.message : "The assistant isn't available right now. Your records and budgets still work as usual." },
      ]);
    } finally {
      setBusy(false);
    }
  }

  async function remove(id: number) {
    await api(`/ai/conversations/${id}`, { method: "DELETE" }).catch(() => undefined);
    if (id === conversationId) startNew();
    void convos.reload();
  }

  const onSubmit = (e: FormEvent) => {
    e.preventDefault();
    void send(text);
  };

  return (
    <div className="grid gap-6 lg:grid-cols-[240px_1fr]">
      <aside className="hidden lg:block" aria-label="Conversations">
        <Button variant="secondary" className="mb-3 w-full" onClick={startNew}>
          <MessageSquarePlus className="size-4" aria-hidden /> New conversation
        </Button>
        <ul className="flex flex-col gap-0.5">
          {(convos.data ?? []).map((c) => (
            <li key={c.id} className="group flex items-center">
              <button
                onClick={() => open(c.id)}
                className={cx("min-w-0 flex-1 rounded-lg px-3 py-2 text-left", c.id === conversationId ? "bg-brand-soft" : "hover:bg-surface")}
                aria-current={c.id === conversationId ? "true" : undefined}
              >
                <span className="block truncate text-sm text-ink">{c.title}</span>
                <span className="block text-xs text-muted">{relativeTime(c.updated_at)}</span>
              </button>
              <button
                onClick={() => remove(c.id)}
                className="grid size-8 shrink-0 place-items-center rounded-lg text-muted opacity-0 group-hover:opacity-100 hover:text-critical-ink focus:opacity-100"
                aria-label={`Delete conversation ${c.title}`}
              >
                <Trash2 className="size-3.5" aria-hidden />
              </button>
            </li>
          ))}
        </ul>
      </aside>

      <Card className="flex h-[calc(100dvh-7.5rem)] min-h-[480px] flex-col lg:h-[calc(100dvh-4rem)]">
        <div className="flex items-center justify-between gap-3 border-b border-line px-5 py-3">
          <div>
            <h1 className="flex items-center gap-2 font-semibold">
              <Sparkles className="size-4 text-brand" aria-hidden /> SpendWise AI
            </h1>
            <p className="text-xs text-muted">
              {status.data ? (status.data.live ? `Answers worded by Claude (${status.data.model}); numbers calculated by SmartSpend.` : "Demo mode: rule-based answers, no AI key configured.") : " "}
            </p>
          </div>
          <Button variant="ghost" size="sm" onClick={startNew} className="lg:hidden">
            New
          </Button>
        </div>

        <div className="flex-1 overflow-y-auto px-4 py-5 sm:px-6" aria-live="polite">
          {messages.length === 0 ? (
            <div className="mx-auto max-w-lg py-6 text-center">
              <h2 className="text-lg font-semibold">Ask about your money</h2>
              <p className="mt-1 text-sm text-muted">Answers come from your own records, with the period and figures shown. You can also tell me about a new expense.</p>
              <div className="mt-6 flex flex-wrap justify-center gap-2">
                {SUGGESTIONS.map((s) => (
                  <button key={s} onClick={() => send(s)} className="rounded-full border border-line-strong bg-surface px-3 py-1.5 text-sm text-ink-2 hover:border-brand hover:text-brand">
                    {s}
                  </button>
                ))}
              </div>
            </div>
          ) : (
            <ol className="mx-auto flex max-w-2xl flex-col gap-4">
              {messages.map((m) => (
                <li key={m.id} className={m.role === "user" ? "flex justify-end" : ""}>
                  {m.role === "user" ? (
                    <p className="max-w-[85%] rounded-2xl rounded-br-md bg-brand px-4 py-2.5 text-sm whitespace-pre-wrap text-white">{m.content}</p>
                  ) : (
                    <AssistantMessage msg={m} onReview={setDraft} />
                  )}
                </li>
              ))}
              {busy && (
                <li className="flex items-center gap-2 text-sm text-muted" role="status">
                  <span className="flex gap-1" aria-hidden>
                    <span className="size-1.5 animate-bounce rounded-full bg-muted [animation-delay:-0.3s]" />
                    <span className="size-1.5 animate-bounce rounded-full bg-muted [animation-delay:-0.15s]" />
                    <span className="size-1.5 animate-bounce rounded-full bg-muted" />
                  </span>
                  Working it out…
                </li>
              )}
              {savedDraft && (
                <li>
                  <Notice tone="success">Saved. It's now in your transactions and budgets.</Notice>
                </li>
              )}
            </ol>
          )}
          <div ref={endRef} />
        </div>

        <form onSubmit={onSubmit} className="border-t border-line p-3 sm:p-4">
          <div className="flex items-end gap-2">
            <label htmlFor="chat-input" className="sr-only">
              Message
            </label>
            <textarea
              id="chat-input"
              ref={inputRef}
              rows={1}
              maxLength={1000}
              value={text}
              onChange={(e) => setText(e.target.value)}
              onKeyDown={(e) => {
                if (e.key === "Enter" && !e.shiftKey) {
                  e.preventDefault();
                  void send(text);
                }
              }}
              placeholder="Ask a question, or “spent ₹300 on groceries”"
              className="max-h-32 min-h-10 flex-1 resize-none rounded-lg border border-line-strong px-3 py-2 text-sm focus:border-brand focus:ring-2 focus:ring-brand/20 focus:outline-none"
            />
            <Button type="submit" disabled={!text.trim() || busy} aria-label="Send">
              <SendHorizontal className="size-4" aria-hidden />
            </Button>
          </div>
          <p className="mt-2 text-xs text-muted">General budgeting help, not financial advice. Don't share passwords or card numbers.</p>
        </form>
      </Card>

      <Dialog open={Boolean(draft)} onClose={() => setDraft(null)} title="Review transaction">
        {draft && (
          <DraftReview
            result={draft}
            onCancel={() => setDraft(null)}
            onDone={() => {
              setDraft(null);
              setSavedDraft(true);
            }}
          />
        )}
      </Dialog>
    </div>
  );
}

function AssistantMessage({ msg, onReview }: { msg: Msg; onReview: (d: ParseResult) => void }) {
  const r = msg.reply;
  const facts = r?.facts;
  return (
    <div className={cx("max-w-[92%] rounded-2xl rounded-bl-md border px-4 py-3 text-sm", msg.error ? "border-critical/30 bg-critical-soft text-critical-ink" : "border-line bg-surface")}>
      <p className="whitespace-pre-wrap text-ink">{msg.content}</p>

      {facts && facts.items.length > 0 && (
        <div className="mt-3 rounded-lg bg-canvas p-3">
          <p className="mb-2 flex items-center gap-1.5 text-xs font-medium text-ink-2">
            <Calculator className="size-3.5" aria-hidden /> Calculated from your records{facts.period ? ` · ${facts.period}` : ""}
          </p>
          <dl className="tnum grid grid-cols-[1fr_auto] gap-x-4 gap-y-1 text-xs">
            {facts.items.map((f) => (
              <div key={f.label} className="contents">
                <dt className="text-muted">{f.label}</dt>
                <dd className="text-right font-medium text-ink">{f.value}</dd>
              </div>
            ))}
          </dl>
          {facts.notes.length > 0 && <p className="mt-2 text-xs text-muted">{facts.notes.join(" ")}</p>}
        </div>
      )}

      {r?.kind === "draft" && r.draft && (
        <Button size="sm" className="mt-3" onClick={() => onReview(r.draft!)}>
          Review and save
        </Button>
      )}

      {(r?.links?.length ?? 0) > 0 && (
        <div className="mt-3 flex flex-wrap gap-2">
          {r!.links!.map((l) => (
            <Link key={l.to} to={l.to} className="rounded-md border border-line-strong px-2.5 py-1 text-xs font-medium text-ink-2 hover:border-brand hover:text-brand">
              {l.label}
            </Link>
          ))}
        </div>
      )}

      {r?.provider === "rules" && r.kind !== "boundary" && <p className="mt-2 text-xs text-muted">The AI service was busy, so this was answered with basic matching.</p>}
    </div>
  );
}
