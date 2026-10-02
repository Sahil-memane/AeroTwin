import { useEffect, useRef, useState } from "react";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import { copilotApi } from "@/services/copilotClient";
import { ApiError } from "@/services/apiClient";

// Accuracy-First Phase 6 — the backend prefixes every grounded claim
// with a bracketed source tag (copilot_engine.py's SYSTEM_PROMPT rule).
// Rendered as a small colored pill rather than left as literal text.
// Every occurrence is wrapped in backticks first (still on the RAW
// string, before ReactMarkdown parses it) so it rides through as an
// inline-code node — the safest way to intercept a substring without a
// custom remark plugin — then the `code` override below recognizes the
// `§TAG§` marker and renders a pill instead of a code chip.
const SOURCE_TAG_RE = /\[(LIVE|PREDICTION|DOCS|SIMULATION)\]/g;
const SOURCE_TAG_COLORS: Record<string, string> = {
  LIVE: "#4C9A6A",
  PREDICTION: "#5B8FD6",
  DOCS: "#B08A5A",
  SIMULATION: "#8B7FC7",
};

function tagifySourceMarkers(markdown: string): string {
  return markdown.replace(SOURCE_TAG_RE, (_match, tag: string) => `\`§${tag}§\``);
}

/** Tailwind overrides for Copilot answers — the model replies in Markdown
 * (bold, bullets, occasional tables), and this keeps that rendering in the
 * same compact, muted-instrument style as the rest of the panel instead of
 * browser-default markdown styling (which reads as oversized/blog-like). */
const MARKDOWN_COMPONENTS = {
  p: (p: React.ComponentPropsWithoutRef<"p">) => <p className="my-1.5 first:mt-0 last:mb-0" {...p} />,
  strong: (p: React.ComponentPropsWithoutRef<"strong">) => <strong className="font-semibold text-text" {...p} />,
  em: (p: React.ComponentPropsWithoutRef<"em">) => <em className="italic" {...p} />,
  ul: (p: React.ComponentPropsWithoutRef<"ul">) => <ul className="my-1.5 list-disc space-y-0.5 pl-4" {...p} />,
  ol: (p: React.ComponentPropsWithoutRef<"ol">) => <ol className="my-1.5 list-decimal space-y-0.5 pl-4" {...p} />,
  li: (p: React.ComponentPropsWithoutRef<"li">) => <li className="leading-relaxed" {...p} />,
  h1: (p: React.ComponentPropsWithoutRef<"h1">) => <h1 className="mb-1 mt-2 text-[13px] font-bold first:mt-0" {...p} />,
  h2: (p: React.ComponentPropsWithoutRef<"h2">) => <h2 className="mb-1 mt-2 text-[12.5px] font-semibold first:mt-0" {...p} />,
  h3: (p: React.ComponentPropsWithoutRef<"h3">) => <h3 className="mb-1 mt-2 text-[12px] font-semibold first:mt-0" {...p} />,
  code: ({ children, ...p }: React.ComponentPropsWithoutRef<"code">) => {
    const match = typeof children === "string" && children.match(/^§(LIVE|PREDICTION|DOCS|SIMULATION)§$/);
    if (match) {
      const tag = match[1];
      const color = SOURCE_TAG_COLORS[tag];
      return (
        <span
          className="mr-1 inline-block rounded-sm border px-1 py-0.5 align-middle text-[9px] font-bold tracking-wide"
          style={{ color, borderColor: color }}
        >
          {tag}
        </span>
      );
    }
    return (
      <code className="rounded-sm bg-surface2 px-1 py-0.5 font-mono text-[11px]" {...p}>
        {children}
      </code>
    );
  },
  pre: (p: React.ComponentPropsWithoutRef<"pre">) => (
    <pre className="my-1.5 overflow-x-auto rounded-sm bg-surface2 p-2 font-mono text-[11px]" {...p} />
  ),
  a: (p: React.ComponentPropsWithoutRef<"a">) => <a className="text-accent underline" target="_blank" rel="noreferrer" {...p} />,
  table: (p: React.ComponentPropsWithoutRef<"table">) => (
    <table className="my-1.5 w-full border-collapse text-[11px]" {...p} />
  ),
  th: (p: React.ComponentPropsWithoutRef<"th">) => (
    <th className="border border-border px-1.5 py-1 text-left font-semibold" {...p} />
  ),
  td: (p: React.ComponentPropsWithoutRef<"td">) => <td className="border border-border px-1.5 py-1" {...p} />,
};

interface Message {
  role: "user" | "assistant";
  text: string;
  typed?: boolean;
}

interface CopilotPanelProps {
  engineId?: string;
  engineSerial?: string;
  defaultExpanded?: boolean;
}

// Accuracy-First Phase 6 — pre-fills and sends a common question with
// one click. No new backend endpoint or per-button AI system: each one
// just calls the same copilotApi.query() any typed message would.
// Queries use {ENGINE} as a placeholder replaced at click-time with the
// real serial number (e.g. "for engine SN-001") so the backend intent
// classifier can identify the engine directly from the message text.
const QUICK_ACTIONS: { label: string; query: string }[] = [
  { label: "Explain Current Health", query: "Explain the current health score for {ENGINE}." },
  { label: "Why Did Health Drop?", query: "Why did the health score drop for {ENGINE}?" },
  { label: "Explain RUL", query: "Explain what RUL means and how it's calculated for {ENGINE}." },
  { label: "Explain Active Alerts", query: "Explain any active alerts for {ENGINE}." },
];

/** Character-reveal effect, in the spirit of Magic UI's "Typing Animation"
 * (registry: typing-animation) — scoped to revealing an already-fetched
 * response rather than its full word-rotation feature set. */
function useTypedReveal(fullText: string, active: boolean, speedMs = 12) {
  const [shown, setShown] = useState(active ? "" : fullText);

  useEffect(() => {
    if (!active) {
      setShown(fullText);
      return;
    }
    let i = 0;
    const id = setInterval(() => {
      i += 1;
      setShown(fullText.slice(0, i));
      if (i >= fullText.length) clearInterval(id);
    }, speedMs);
    return () => clearInterval(id);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [fullText, active]);

  return shown;
}

function AssistantBubble({ text, isNew }: { text: string; isNew: boolean }) {
  const shown = useTypedReveal(text, isNew);
  const done = shown.length === text.length;
  return (
    <div className="self-start max-w-[94%] rounded-lg rounded-bl-sm border border-border bg-surface px-3 py-2.5 text-xs leading-relaxed">
      {done ? (
        // Mid-reveal, `shown` is a truncated slice — "**Remaining" has no
        // closing "**" yet, so markdown-rendering it would flicker
        // broken/half-bold formatting for the ~1s the animation runs.
        // Rendering plain text until the full string has arrived, then
        // swapping to Markdown once it's syntactically complete, avoids
        // that without giving up the typing effect.
        <div className="markdown-body">
          <ReactMarkdown remarkPlugins={[remarkGfm]} components={MARKDOWN_COMPONENTS}>
            {tagifySourceMarkers(text)}
          </ReactMarkdown>
        </div>
      ) : (
        <span className="whitespace-pre-wrap">
          {shown}
          <span className="inline-block animate-blink-cursor">▍</span>
        </span>
      )}
    </div>
  );
}

export function CopilotPanel({ engineId, engineSerial, defaultExpanded = false }: CopilotPanelProps) {
  const [expanded, setExpanded] = useState(defaultExpanded);
  const [messages, setMessages] = useState<Message[]>([]);
  const [input, setInput] = useState("");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const scrollRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    scrollRef.current?.scrollTo({ top: scrollRef.current.scrollHeight, behavior: "smooth" });
  }, [messages]);

  async function sendText(text: string) {
    if (!text || loading) return;
    setInput("");
    setError(null);
    setMessages((m) => [...m, { role: "user", text }]);
    setLoading(true);
    try {
      const res = await copilotApi.query(text, engineId);
      setMessages((m) => [...m, { role: "assistant", text: res.answer }]);
    } catch (err) {
      if (err instanceof ApiError && err.status === 503) {
        setError("Copilot isn't configured on the backend yet (missing GEMINI_API_KEY).");
      } else if (err instanceof ApiError && err.status === 502) {
        setError("Copilot's upstream model call failed — check backend logs for the exact error.");
      } else {
        setError("Couldn't reach the Copilot.");
      }
    } finally {
      setLoading(false);
    }
  }

  async function send() {
    await sendText(input.trim());
  }

  if (!expanded) {
    return (
      <button
        onClick={() => setExpanded(true)}
        className="absolute right-0 top-1/2 -translate-y-1/2 flex items-center gap-2 rounded-l border border-r-0 border-borderStrong bg-surface2 px-2 py-4 text-[11px] font-bold tracking-widest text-textMuted hover:text-accent"
        style={{ writingMode: "vertical-rl" }}
      >
        <svg width={14} height={14} viewBox="0 0 16 16" fill="none" stroke="currentColor" strokeWidth={1.4} style={{ writingMode: "horizontal-tb", transform: "rotate(90deg)" }}>
          <path d="M2 3.5h12v7H6.5L3.5 13v-2.5H2v-7z" strokeLinejoin="round" />
        </svg>
        COPILOT
      </button>
    );
  }

  return (
    <div className="flex w-[380px] flex-shrink-0 flex-col border-l border-border bg-surface">
      <div className="flex h-12 flex-shrink-0 items-center gap-2 border-b border-border px-3.5">
        <svg width={15} height={15} viewBox="0 0 16 16" fill="none" stroke="#5B8FD6" strokeWidth={1.4}>
          <path d="M2 3.5h12v7H6.5L3.5 13v-2.5H2v-7z" strokeLinejoin="round" />
        </svg>
        <div className="text-xs font-bold tracking-wide">AEROTWIN COPILOT</div>
        <div className="flex-grow" />
        <button onClick={() => setExpanded(false)} className="text-textMuted hover:text-text">
          <svg width={14} height={14} viewBox="0 0 16 16" fill="none" stroke="currentColor" strokeWidth={1.6}>
            <path d="M10 3l-5 5 5 5" />
          </svg>
        </button>
      </div>

      <div ref={scrollRef} className="scrollbar-thin flex flex-grow flex-col gap-2.5 overflow-auto p-4">
        {messages.length === 0 && (
          <div className="text-xs text-textFaint">
            Ask about AeroTwin's models, engine health concepts, or predictive maintenance. Live engine data is used
            only when explicitly supplied.
          </div>
        )}
        {messages.map((m, i) =>
          m.role === "user" ? (
            <div key={i} className="self-end max-w-[88%] rounded-lg rounded-br-sm border border-borderStrong bg-surface3 px-3 py-2 text-xs">
              {m.text}
            </div>
          ) : (
            <AssistantBubble key={i} text={m.text} isNew={i === messages.length - 1} />
          ),
        )}
        {loading && <div className="text-xs text-textFaint">Thinking…</div>}
        {error && <div className="text-xs text-critical">{error}</div>}
      </div>

      <div className="flex flex-col gap-2 border-t border-border px-3 pt-2.5 pb-1">
        <div className="flex flex-wrap gap-1.5">
          {QUICK_ACTIONS.map((qa) => (
            <button
              key={qa.label}
              onClick={() => {
                if (engineSerial) {
                  // On an engine page: replace the placeholder with the real serial and
                  // send immediately — the backend will resolve the engine from the text.
                  sendText(qa.query.replace("{ENGINE}", `engine ${engineSerial}`));
                } else {
                  // On the Dashboard (no engine context): pre-fill the input so the
                  // user can type in the serial number before submitting.
                  setInput(qa.query.replace("{ENGINE}", "engine "));
                }
              }}
              disabled={loading}
              className="rounded-full border border-borderStrong bg-surface2 px-2.5 py-1 text-[10px] font-semibold text-textMuted hover:border-accent hover:text-accent disabled:opacity-50"
            >
              {qa.label}
            </button>
          ))}
        </div>
        {engineSerial ? (
          <div className="text-[10px] text-textFaint">
            Context: engine <span className="font-semibold text-accent">{engineSerial}</span>
          </div>
        ) : (
          <div className="text-[10px] text-textFaint italic">
            Note: Include the engine serial (e.g. SN-001) in your prompt for live data.
          </div>
        )}
      </div>

      <div className="flex gap-2 p-3">
        <input
          value={input}
          onChange={(e) => setInput(e.target.value)}
          onKeyDown={(e) => e.key === "Enter" && send()}
          placeholder={engineId ? "Ask about this engine…" : "Type your question (include engine ID for live data)…"}
          className="flex-grow rounded-sm border border-borderStrong bg-surface2 px-2.5 py-2 text-xs outline-none focus:border-accent"
          disabled={loading}
        />
        <button
          onClick={send}
          disabled={loading}
          className="rounded-sm bg-accent px-3 py-2 text-xs font-semibold text-bg disabled:opacity-50"
        >
          Send
        </button>
      </div>
    </div>
  );
}
