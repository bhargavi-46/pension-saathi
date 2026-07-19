"use client";

import { use, useEffect, useRef, useState } from "react";
import Link from "next/link";
import { api, AgentActionEvent, ChatMessage, Claim, NON_CASH_SCHEME_IDS } from "@/lib/api";

const AGENTS = [
  { id: "discovery", label: "Discovery", icon: "🔍" },
  { id: "document", label: "Document", icon: "📄" },
  { id: "filing", label: "Filing", icon: "📮" },
  { id: "tracking", label: "Tracking", icon: "📡" },
  { id: "voice", label: "Voice", icon: "🎙️" },
] as const;

const AGENT_COLORS: Record<string, string> = {
  discovery: "border-l-amber-400",
  document: "border-l-sky-400",
  filing: "border-l-emerald-400",
  tracking: "border-l-violet-400",
  voice: "border-l-rose-400",
};

export default function DashboardPage({
  params,
}: {
  params: Promise<{ widowId: string }>;
}) {
  const { widowId } = use(params);
  const [events, setEvents] = useState<AgentActionEvent[]>([]);
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [claims, setClaims] = useState<Claim[]>([]);
  const [totalValue, setTotalValue] = useState(0);
  const [connected, setConnected] = useState(false);
  const [expanded, setExpanded] = useState<number | null>(null);
  const activeAgents = useRef<Map<string, number>>(new Map());
  const [, forceRender] = useState(0);
  const chatEndRef = useRef<HTMLDivElement>(null);

  // SSE subscription
  useEffect(() => {
    const source = new EventSource(api.streamUrl(widowId));
    source.onopen = () => setConnected(true);
    source.onerror = () => setConnected(false);
    source.onmessage = (e) => {
      const event: AgentActionEvent = JSON.parse(e.data);
      setEvents((prev) =>
        prev.some((p) => p.id === event.id) ? prev : [event, ...prev].slice(0, 200)
      );
      activeAgents.current.set(event.agent_name, Date.now());
      forceRender((n) => n + 1);
    };
    const pulseTimer = setInterval(() => forceRender((n) => n + 1), 2000);
    return () => {
      source.close();
      clearInterval(pulseTimer);
    };
  }, [widowId]);

  // Poll chat + claims every 3s (read-only preview)
  useEffect(() => {
    let cancelled = false;
    const load = async () => {
      try {
        const [msgRes, claimRes] = await Promise.all([
          api.getMessages(widowId),
          api.getClaims(widowId),
        ]);
        if (cancelled) return;
        setMessages(msgRes.messages);
        setClaims(claimRes.claims);
        setTotalValue(claimRes.total_annual_value);
      } catch {
        /* backend offline — SSE indicator already shows it */
      }
    };
    load();
    const timer = setInterval(load, 3000);
    return () => {
      cancelled = true;
      clearInterval(timer);
    };
  }, [widowId]);

  useEffect(() => {
    chatEndRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages]);

  const filed = claims.filter((c) => c.status !== "discovered").length;
  const completed = claims.filter((c) => c.status === "received");
  // Cash DBT transfers only — an insurance-card activation (PM-JAY) is a
  // benefit going live, not money credited, so it gets its own counter.
  const paymentsReceived = completed.filter((c) => !NON_CASH_SCHEME_IDS.has(c.scheme_id)).length;
  const benefitsActivated = completed.filter((c) => NON_CASH_SCHEME_IDS.has(c.scheme_id)).length;

  return (
    <div className="flex h-dvh flex-col bg-[#1a0b13] text-gray-100">
      {/* Header */}
      <header className="flex items-center justify-between border-b border-white/10 bg-aubergine px-4 py-3">
        <div className="flex items-center gap-3">
          <Link href="/" className="text-gold hover:text-gold-light">← </Link>
          <h1 className="font-[family-name:var(--font-playfair)] text-lg font-bold text-gold">
            Pension Saathi · Agent Console
          </h1>
          <span className="rounded bg-white/10 px-2 py-0.5 font-mono text-xs text-gray-300">
            {widowId}
          </span>
        </div>
        <div className="flex items-center gap-2 text-xs">
          <span className={`h-2 w-2 rounded-full ${connected ? "bg-green-400" : "bg-red-400"}`} />
          {connected ? "live stream connected" : "connecting…"}
        </div>
      </header>

      <div className="flex min-h-0 flex-1 flex-col md:flex-row">
        {/* Left: chat preview */}
        <section className="flex h-56 flex-col border-b border-white/10 md:h-auto md:w-2/5 md:border-b-0 md:border-r">
          <div className="border-b border-white/10 px-4 py-2 text-xs uppercase tracking-widest text-gray-400">
            Widow&apos;s conversation (live)
          </div>
          <div className="flex-1 space-y-2 overflow-y-auto bg-[#241019] p-3">
            {messages.length === 0 && (
              <div className="mt-6 text-center text-xs text-gray-500">
                No conversation yet — open /chat to begin
              </div>
            )}
            {messages.map((m) => (
              <div key={m.id} className={`flex ${m.role === "user" ? "justify-end" : "justify-start"}`}>
                <div
                  className={`max-w-[85%] rounded-lg px-3 py-1.5 text-xs ${
                    m.role === "user" ? "bg-wa-green/80 text-white" : "bg-white/10"
                  }`}
                >
                  {m.content}
                </div>
              </div>
            ))}
            <div ref={chatEndRef} />
          </div>
        </section>

        {/* Right: agent console */}
        <section className="flex min-h-0 flex-1 flex-col">
          {/* Agent chips */}
          <div className="flex flex-wrap gap-2 border-b border-white/10 px-4 py-3">
            {AGENTS.map((a) => {
              const lastActive = activeAgents.current.get(a.id) ?? 0;
              const isActive = Date.now() - lastActive < 6000;
              return (
                <div
                  key={a.id}
                  className={`flex items-center gap-1.5 rounded-full border px-3 py-1 text-xs ${
                    isActive
                      ? "border-gold bg-gold/20 text-gold-light"
                      : "border-white/15 text-gray-400"
                  }`}
                >
                  <span className={isActive ? "animate-pulse-dot" : ""}>{a.icon}</span>
                  {a.label}
                  {isActive && <span className="h-1.5 w-1.5 rounded-full bg-gold animate-pulse-dot" />}
                </div>
              );
            })}
          </div>

          {/* Feed */}
          <div className="flex-1 space-y-2 overflow-y-auto p-4">
            {events.length === 0 && (
              <div className="mt-10 text-center text-sm text-gray-500">
                Waiting for agent activity…
                <div className="mt-1 text-xs">
                  Try the pre-seeded demo at{" "}
                  <Link href="/dashboard/demo-widow" className="text-gold underline">
                    /dashboard/demo-widow
                  </Link>
                </div>
              </div>
            )}
            {events.map((e) => (
              <div
                key={e.id}
                className={`animate-slide-in rounded-lg border-l-4 bg-white/5 p-3 ${AGENT_COLORS[e.agent_name] ?? "border-l-gray-400"}`}
              >
                <div className="flex items-center justify-between text-xs text-gray-400">
                  <span className="flex items-center gap-1.5 font-medium uppercase tracking-wide">
                    {AGENTS.find((a) => a.id === e.agent_name)?.icon}{" "}
                    {e.agent_name} agent
                  </span>
                  <span>{new Date(e.created_at).toLocaleTimeString()}</span>
                </div>
                <div className="mt-1 text-sm">{e.action}</div>
                {e.details && (
                  <button
                    onClick={() => setExpanded(expanded === e.id ? null : e.id)}
                    className="mt-1 text-xs text-gold hover:underline"
                  >
                    {expanded === e.id ? "hide details" : "show details"}
                  </button>
                )}
                {expanded === e.id && e.details && (
                  <pre className="mt-2 overflow-x-auto rounded bg-black/40 p-2 text-[10px] text-gray-300">
                    {JSON.stringify(e.details, null, 2)}
                  </pre>
                )}
              </div>
            ))}
          </div>

          {/* Summary bar */}
          <div className="flex flex-wrap items-center gap-x-6 gap-y-1 border-t border-gold/30 bg-aubergine px-4 py-3 text-sm">
            <span>
              Schemes found: <b className="text-gold-light">{claims.length}</b>
            </span>
            <span>
              Filed: <b className="text-gold-light">{filed}</b>
            </span>
            <span>
              Payments received: <b className="text-gold-light">{paymentsReceived}</b>
            </span>
            <span>
              Benefits activated: <b className="text-gold-light">{benefitsActivated}</b>
            </span>
            <span className="ml-auto">
              Annual value discovered:{" "}
              <b className="font-[family-name:var(--font-playfair)] text-lg text-gold">
                ₹{totalValue.toLocaleString("en-IN")}
              </b>
            </span>
          </div>
        </section>
      </div>
    </div>
  );
}
