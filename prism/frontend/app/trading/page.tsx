"use client";
import { useState, useRef, useEffect, Suspense } from "react";
import { useRouter, useSearchParams } from "next/navigation";
import { motion, AnimatePresence } from "framer-motion";
import Header from "@/components/Header";
import GridOverlay from "@/components/GridOverlay";
import ProbabilityArc from "@/components/ProbabilityArc";
import { tradingChat, streamTradingAnalysis, listForecasts, listTradingSessions } from "@/lib/api";
import type {
  BeliefSummary,
  BeliefAnalysis,
  DomainAnalysis,
  TradeRecommendation,
  SavedForecast,
  TradingSession,
} from "@/lib/types";

type Stage = "idle" | "chatting" | "analyzing" | "done" | "error";

interface ChatMsg {
  role: "user" | "assistant";
  content: string;
  searchQueries?: string[];
}

// ─── Main page ────────────────────────────────────────────────────────────────

export default function TradingPage() {
  return (
    <Suspense>
      <TradingPageInner />
    </Suspense>
  );
}

function TradingPageInner() {
  const router       = useRouter();
  const searchParams = useSearchParams();
  const [stage, setStage]                 = useState<Stage>("idle");
  const [input, setInput]                 = useState("");
  const [chatMessages, setChatMessages]   = useState<ChatMsg[]>([]);
  const [apiHistory, setApiHistory]       = useState<Record<string, unknown>[]>([]);
  const [beliefSummary, setBeliefSummary] = useState<BeliefSummary | null>(null);
  const [analysis, setAnalysis]           = useState<BeliefAnalysis | null>(null);
  const [screenedCount, setScreenedCount] = useState(0);
  const [recommendations, setRecommendations] = useState<TradeRecommendation[]>([]);
  const [progressLabel, setProgressLabel] = useState("");
  const [loading, setLoading]             = useState(false);
  const [error, setError]                 = useState("");
  const [savedForecasts, setSavedForecasts] = useState<SavedForecast[]>([]);
  const [sessions, setSessions]             = useState<TradingSession[]>([]);
  const [sessionId, setSessionId]           = useState<number | null>(null);

  const scrollRef  = useRef<HTMLDivElement>(null);
  const inputRef   = useRef<HTMLInputElement | HTMLTextAreaElement>(null);

  useEffect(() => {
    const sid = searchParams.get("session");
    listForecasts(500).then(setSavedForecasts).catch(() => {});
    listTradingSessions(20).then(list => {
      setSessions(list);
      if (sid) {
        const s = list.find(s => s.id === Number(sid));
        if (s) {
          setBeliefSummary(JSON.parse(s.belief_summary_json));
          setAnalysis(JSON.parse(s.analysis_json));
          setRecommendations(JSON.parse(s.recommendations_json));
          setSessionId(s.id);
          setStage("done");
        }
      }
    }).catch(() => {});
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);


  function startAnalysis(summary: BeliefSummary) {
    streamTradingAnalysis(summary, (msg) => {
      if (msg.type === "progress") {
        setProgressLabel(msg.label);
      } else if (msg.type === "analyst_done") {
        setAnalysis(msg.analysis);
      } else if (msg.type === "screener_done") {
        setScreenedCount(msg.count);
      } else if (msg.type === "curator_done") {
        setRecommendations(msg.recommendations);
        setStage("done");
        setProgressLabel("");
        if (msg.session_id) {
          setSessionId(msg.session_id);
          router.replace(`/trading?session=${msg.session_id}`, { scroll: false });
        }
        listForecasts(500).then(setSavedForecasts).catch(() => {});
        listTradingSessions(20).then(setSessions).catch(() => {});
      } else if (msg.type === "error") {
        setError(msg.message);
        setStage("error");
        setProgressLabel("");
      }
    });
  }

  async function sendMessage(message: string, history: Record<string, unknown>[]) {
    if (!message.trim() || loading) return;
    setLoading(true);
    setInput("");

    setChatMessages(prev => [...prev, { role: "user", content: message }]);

    try {
      const result = await tradingChat(history, message);
      setApiHistory(result.history);

      if (result.status === "finalized" && result.belief_summary) {
        setBeliefSummary(result.belief_summary);
        setStage("analyzing");
        startAnalysis(result.belief_summary);
      } else if (result.agent_message) {
        setChatMessages(prev => [...prev, {
          role: "assistant",
          content: result.agent_message!,
          searchQueries: result.search_queries,
        }]);
      }
    } catch (err) {
      setError(err instanceof Error ? err.message : "Request failed");
      setStage("error");
    } finally {
      setLoading(false);
    }
  }

  function restoreSession(s: TradingSession) {
    setBeliefSummary(JSON.parse(s.belief_summary_json));
    setAnalysis(JSON.parse(s.analysis_json));
    setRecommendations(JSON.parse(s.recommendations_json));
    setSessionId(s.id);
    setChatMessages([]);
    setApiHistory([]);
    setError("");
    setProgressLabel("");
    setScreenedCount(0);
    setStage("done");
    router.replace(`/trading?session=${s.id}`, { scroll: false });
    listForecasts(500).then(setSavedForecasts).catch(() => {});
  }

  function handleInitialSubmit() {
    if (!input.trim()) return;
    setStage("chatting");
    sendMessage(input, []);
  }

  function handleReply() {
    sendMessage(input, apiHistory);
  }

  function onIdleKey(e: React.KeyboardEvent) {
    if (e.key === "Enter" && !e.shiftKey) { e.preventDefault(); handleInitialSubmit(); }
  }
  function onReplyKey(e: React.KeyboardEvent) {
    if (e.key === "Enter" && !e.shiftKey) { e.preventDefault(); handleReply(); }
  }

  return (
    <div style={{ minHeight: "100vh", background: "#080808", position: "relative" }}>
      <Header />
      <GridOverlay />

      <div
        ref={scrollRef}
        style={{
          position: "relative", zIndex: 10,
          paddingTop: "56px",
          overflowY: "auto",
          height: "100vh",
        }}
      >
        <div style={{ maxWidth: "740px", margin: "0 auto", padding: "40px 28px 80px" }}>

          {/* ── Idle: large centered input ── */}
          <AnimatePresence>
            {stage === "idle" && (
              <motion.div
                key="idle"
                initial={{ opacity: 0, y: 20 }}
                animate={{ opacity: 1, y: 0 }}
                exit={{ opacity: 0, y: -16, transition: { duration: 0.2 } }}
                style={{
                  minHeight: "calc(100vh - 180px)",
                  display: "flex", flexDirection: "column", justifyContent: "center",
                }}
              >
                <IdleView
                  input={input}
                  setInput={setInput}
                  onKey={onIdleKey}
                  onSubmit={handleInitialSubmit}
                  inputRef={inputRef as React.RefObject<HTMLTextAreaElement>}
                  sessions={sessions}
                  onRestoreSession={restoreSession}
                />
              </motion.div>
            )}
          </AnimatePresence>

          {/* ── Active: chat + progressive results ── */}
          {stage !== "idle" && (
            <div>
              {/* New session button */}
              <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: "28px" }}>
                <div style={{
                  fontFamily: "var(--font-mono), monospace", fontSize: "9px",
                  letterSpacing: "0.2em", textTransform: "uppercase",
                  color: "#3a3835", display: "flex", alignItems: "center", gap: "8px",
                }}>
                  <span style={{ color: "#e36438" }}>◈</span> Trading Companion
                </div>
                <button
                  onClick={() => {
                    setStage("idle");
                    setBeliefSummary(null);
                    setAnalysis(null);
                    setRecommendations([]);
                    setChatMessages([]);
                    setApiHistory([]);
                    setError("");
                    setProgressLabel("");
                    setScreenedCount(0);
                    setSessionId(null);
                    router.replace("/trading", { scroll: false });
                  }}
                  style={{
                    background: "transparent", border: "1px solid #282828",
                    borderRadius: "7px", padding: "6px 14px",
                    fontFamily: "var(--font-mono), monospace", fontSize: "9px",
                    fontWeight: 700, letterSpacing: "0.1em", textTransform: "uppercase",
                    color: "#3a3835", cursor: "pointer", transition: "border-color 0.15s, color 0.15s",
                  }}
                  onMouseEnter={e => { e.currentTarget.style.borderColor = "#e36438"; e.currentTarget.style.color = "#e36438"; }}
                  onMouseLeave={e => { e.currentTarget.style.borderColor = "#282828"; e.currentTarget.style.color = "#3a3835"; }}
                >
                  + New Session
                </button>
              </div>
              {/* Chat thread */}
              <ChatThread messages={chatMessages} loading={loading && stage === "chatting"} />

              {/* Reply bar (only while waiting for agent to finalize) */}
              {stage === "chatting" && (
                <motion.div
                  initial={{ opacity: 0, y: 10 }}
                  animate={{ opacity: 1, y: 0 }}
                  transition={{ duration: 0.3 }}
                >
                  <ReplyBar
                    input={input}
                    setInput={setInput}
                    onKey={onReplyKey}
                    onSubmit={handleReply}
                    disabled={loading}
                  />
                </motion.div>
              )}

              {/* Belief summary card */}
              {beliefSummary && (
                <motion.div
                  initial={{ opacity: 0, y: 28 }}
                  animate={{ opacity: 1, y: 0 }}
                  transition={{ duration: 0.55, ease: [0.16, 1, 0.3, 1] }}
                >
                  <BeliefCard summary={beliefSummary} />
                </motion.div>
              )}

              {/* Domain impact grid */}
              {analysis && (
                <motion.div
                  initial={{ opacity: 0, y: 28 }}
                  animate={{ opacity: 1, y: 0 }}
                  transition={{ duration: 0.55, delay: 0.1, ease: [0.16, 1, 0.3, 1] }}
                >
                  <DomainGrid analysis={analysis} />
                  {analysis.most_surprising_connection && (
                    <SurpriseCallout text={analysis.most_surprising_connection} />
                  )}
                </motion.div>
              )}

              {/* Screener status line */}
              {screenedCount > 0 && (
                <motion.div
                  initial={{ opacity: 0 }}
                  animate={{ opacity: 1 }}
                  style={{
                    fontFamily: "var(--font-mono), monospace", fontSize: "10px",
                    color: "#3a3835", margin: "8px 0 4px",
                    display: "flex", alignItems: "center", gap: "8px",
                  }}
                >
                  <span style={{ color: "#e36438" }}>→</span>
                  {screenedCount} relevant events screened from Kalshi catalog
                </motion.div>
              )}

              {/* Running progress indicator */}
              <AnimatePresence mode="wait">
                {progressLabel && (
                  <motion.div
                    key={progressLabel}
                    initial={{ opacity: 0, x: -6 }}
                    animate={{ opacity: 1, x: 0 }}
                    exit={{ opacity: 0 }}
                    transition={{ duration: 0.25 }}
                    style={{
                      fontFamily: "var(--font-mono), monospace", fontSize: "11px",
                      color: "#6b6865", margin: "14px 0",
                      display: "flex", alignItems: "center", gap: "10px",
                    }}
                  >
                    <span className="blink" style={{ color: "#e36438", fontSize: "7px" }}>●</span>
                    {progressLabel}
                  </motion.div>
                )}
              </AnimatePresence>

              {/* Recommendation cards */}
              {recommendations.length > 0 && (
                <div style={{ marginTop: "28px" }}>
                  <SectionLabel label={`${recommendations.length} recommended markets`} dot="purple" />
                  <div style={{ display: "flex", flexDirection: "column", gap: "10px" }}>
                    {recommendations.map((rec, i) => (
                      <motion.div
                        key={rec.ticker}
                        initial={{ opacity: 0, y: 18 }}
                        animate={{ opacity: 1, y: 0 }}
                        transition={{ duration: 0.4, delay: i * 0.07, ease: [0.16, 1, 0.3, 1] }}
                      >
                        <RecCard
                          rec={rec}
                          forecast={savedForecasts.find(f => f.ticker === rec.ticker) ?? null}
                          onExplore={() => router.push(
                            `/market/${rec.event_ticker}?title=${encodeURIComponent(rec.event_title ?? rec.question)}&cat=${encodeURIComponent(rec.category ?? "")}&sub=&from=trading${sessionId ? `&session=${sessionId}` : ""}`
                          )}
                          onViewForecast={(id) => router.push(`/market/${rec.event_ticker}?saved=${id}&from=trading${sessionId ? `&session=${sessionId}` : ""}`)}
                          onRunForecast={() => router.push(
                            `/market/${rec.event_ticker}?title=${encodeURIComponent(rec.event_title ?? rec.question)}&cat=${encodeURIComponent(rec.category ?? "")}&sub=&from=trading${sessionId ? `&session=${sessionId}` : ""}`
                          )}
                        />
                      </motion.div>
                    ))}
                  </div>
                </div>
              )}

              {/* Previous sessions (done state only) */}
              {stage === "done" && sessions.filter(s => s.id !== sessionId).length > 0 && (
                <div style={{ marginTop: "48px" }}>
                  <SectionLabel label="Previous Sessions" />
                  <div style={{ display: "flex", flexDirection: "column", gap: "7px" }}>
                    {sessions.filter(s => s.id !== sessionId).map((s, i) => {
                      const recs = (() => { try { return JSON.parse(s.recommendations_json).length; } catch { return 0; } })();
                      const drivers = (() => { try { return JSON.parse(s.key_drivers_json) as string[]; } catch { return [] as string[]; } })();
                      return (
                        <motion.button
                          key={s.id}
                          initial={{ opacity: 0, y: 8 }}
                          animate={{ opacity: 1, y: 0 }}
                          transition={{ duration: 0.3, delay: i * 0.04 }}
                          onClick={() => restoreSession(s)}
                          style={{
                            width: "100%", textAlign: "left",
                            background: "rgba(14,14,14,0.95)",
                            border: "1px solid #222", borderRadius: "11px",
                            padding: "14px 16px",
                            transition: "border-color 0.15s, background 0.15s",
                            cursor: "pointer",
                          }}
                          onMouseEnter={e => {
                            e.currentTarget.style.borderColor = "rgba(227,100,56,0.22)";
                            e.currentTarget.style.background = "rgba(18,18,18,0.98)";
                          }}
                          onMouseLeave={e => {
                            e.currentTarget.style.borderColor = "#222";
                            e.currentTarget.style.background = "rgba(14,14,14,0.95)";
                          }}
                        >
                          <div style={{ display: "flex", justifyContent: "space-between", alignItems: "flex-start", gap: "12px" }}>
                            <div style={{ flex: 1, minWidth: 0 }}>
                              <div style={{
                                fontSize: "13px", fontWeight: 600, color: "#ede9e3",
                                lineHeight: 1.4, marginBottom: "6px",
                                overflow: "hidden", display: "-webkit-box",
                                WebkitLineClamp: 2, WebkitBoxOrient: "vertical" as const,
                              }}>
                                {s.core_belief}
                              </div>
                              <div style={{ display: "flex", gap: "6px", flexWrap: "wrap" }}>
                                {drivers.slice(0, 3).map((d, j) => (
                                  <span key={j} style={{
                                    fontSize: "10px", color: "#4a4845",
                                    background: "rgba(255,255,255,0.03)",
                                    border: "1px solid #1e1e1e", borderRadius: "4px",
                                    padding: "2px 7px",
                                  }}>{d}</span>
                                ))}
                              </div>
                            </div>
                            <div style={{ flexShrink: 0, textAlign: "right" }}>
                              <div style={{ fontFamily: "var(--font-mono), monospace", fontSize: "9px", color: "#e36438", marginBottom: "4px" }}>
                                {recs} market{recs !== 1 ? "s" : ""}
                              </div>
                              <div style={{ fontFamily: "var(--font-mono), monospace", fontSize: "9px", color: "#2a2826" }}>
                                {relTime(s.created_at)}
                              </div>
                            </div>
                          </div>
                        </motion.button>
                      );
                    })}
                  </div>
                </div>
              )}

              {/* Error state */}
              {error && (
                <motion.div
                  initial={{ opacity: 0 }}
                  animate={{ opacity: 1 }}
                  style={{
                    margin: "20px 0",
                    padding: "14px 18px",
                    background: "rgba(248,113,113,0.06)",
                    border: "1px solid rgba(248,113,113,0.2)",
                    borderRadius: "10px",
                    fontFamily: "var(--font-mono), monospace",
                    fontSize: "12px", color: "#f87171",
                  }}
                >
                  {error}
                </motion.div>
              )}
            </div>
          )}
        </div>
      </div>
    </div>
  );
}

// ─── Sub-components ───────────────────────────────────────────────────────────

function relTime(ts: string): string {
  try {
    const d = Date.now() - new Date(ts).getTime();
    const m = Math.floor(d / 60000);
    if (m < 60) return `${m}m ago`;
    const h = Math.floor(m / 60);
    if (h < 24) return `${h}h ago`;
    return `${Math.floor(h / 24)}d ago`;
  } catch { return ""; }
}

function IdleView({
  input, setInput, onKey, onSubmit, inputRef, sessions, onRestoreSession,
}: {
  input: string;
  setInput: (v: string) => void;
  onKey: (e: React.KeyboardEvent) => void;
  onSubmit: () => void;
  inputRef: React.RefObject<HTMLTextAreaElement>;
  sessions: TradingSession[];
  onRestoreSession: (s: TradingSession) => void;
}) {
  return (
    <div>
      <div style={{
        fontFamily: "var(--font-mono), monospace", fontSize: "9px",
        letterSpacing: "0.2em", textTransform: "uppercase",
        color: "#3a3835", marginBottom: "20px",
        display: "flex", alignItems: "center", gap: "8px",
      }}>
        <span style={{ color: "#e36438" }}>◈</span> Trading Companion
      </div>

      <h1 style={{
        fontSize: "30px", fontWeight: 600, color: "#ede9e3",
        lineHeight: 1.25, marginBottom: "12px",
      }}>
        What&apos;s your belief<br />about the future?
      </h1>

      <p style={{
        fontSize: "14px", color: "#4a4845", lineHeight: 1.65,
        marginBottom: "32px", maxWidth: "520px",
      }}>
        Describe a view on geopolitics, markets, technology, or anything else.
        The pipeline interviews you, maps second-order effects across 16 domains,
        and surfaces the best Kalshi prediction markets to express it.
      </p>

      <div style={{
        background: "rgba(14,14,14,0.95)",
        border: "1px solid #282828", borderRadius: "14px",
        padding: "18px 20px",
        backdropFilter: "blur(20px)", WebkitBackdropFilter: "blur(20px)",
        boxShadow: "0 0 0 1px rgba(255,255,255,0.02), 0 8px 32px rgba(0,0,0,0.5)",
      }}>
        <textarea
          ref={inputRef}
          value={input}
          onChange={e => setInput(e.target.value)}
          onKeyDown={onKey}
          placeholder="e.g. I think the US-China trade war will escalate significantly this year, pushing inflation back up and delaying Fed cuts…"
          rows={4}
          style={{
            width: "100%", background: "transparent", border: "none",
            fontSize: "14px", color: "#ede9e3",
            fontFamily: "var(--font-jakarta), system-ui, sans-serif",
            outline: "none", resize: "none", lineHeight: 1.65,
          }}
        />
        <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginTop: "14px" }}>
          <span style={{
            fontFamily: "var(--font-mono), monospace", fontSize: "9px",
            color: "#2a2826", letterSpacing: "0.1em",
          }}>
            ↵ enter to submit
          </span>
          <button
            onClick={onSubmit}
            disabled={!input.trim()}
            style={{
              background: input.trim() ? "#e36438" : "#181818",
              color: "#fff", border: "none", borderRadius: "8px",
              padding: "9px 22px", fontSize: "11px",
              fontFamily: "var(--font-mono), monospace",
              fontWeight: 600, letterSpacing: "0.06em",
              transition: "background 0.15s",
              opacity: input.trim() ? 1 : 0.35,
              cursor: input.trim() ? "pointer" : "default",
            }}
            onMouseEnter={e => { if (input.trim()) e.currentTarget.style.background = "#c4421a"; }}
            onMouseLeave={e => { if (input.trim()) e.currentTarget.style.background = "#e36438"; }}
          >
            Find Markets →
          </button>
        </div>
      </div>

      {/* Previous sessions */}
      {sessions.length > 0 && (
        <div style={{ marginTop: "40px" }}>
          <SectionLabel label="Previous Sessions" />
          <div style={{ display: "flex", flexDirection: "column", gap: "7px" }}>
            {sessions.map((s, i) => {
              const recs = (() => { try { return JSON.parse(s.recommendations_json).length; } catch { return 0; } })();
              const drivers = (() => { try { return JSON.parse(s.key_drivers_json) as string[]; } catch { return [] as string[]; } })();
              return (
                <motion.button
                  key={s.id}
                  initial={{ opacity: 0, y: 8 }}
                  animate={{ opacity: 1, y: 0 }}
                  transition={{ duration: 0.3, delay: i * 0.04 }}
                  onClick={() => onRestoreSession(s)}
                  style={{
                    width: "100%", textAlign: "left",
                    background: "rgba(14,14,14,0.95)",
                    border: "1px solid #222", borderRadius: "11px",
                    padding: "14px 16px",
                    transition: "border-color 0.15s, background 0.15s",
                    cursor: "pointer",
                  }}
                  onMouseEnter={e => {
                    e.currentTarget.style.borderColor = "rgba(227,100,56,0.22)";
                    e.currentTarget.style.background = "rgba(18,18,18,0.98)";
                  }}
                  onMouseLeave={e => {
                    e.currentTarget.style.borderColor = "#222";
                    e.currentTarget.style.background = "rgba(14,14,14,0.95)";
                  }}
                >
                  <div style={{ display: "flex", justifyContent: "space-between", alignItems: "flex-start", gap: "12px" }}>
                    <div style={{ flex: 1, minWidth: 0 }}>
                      <div style={{
                        fontSize: "13px", fontWeight: 600, color: "#ede9e3",
                        lineHeight: 1.4, marginBottom: "6px",
                        overflow: "hidden", display: "-webkit-box",
                        WebkitLineClamp: 2, WebkitBoxOrient: "vertical" as const,
                      }}>
                        {s.core_belief}
                      </div>
                      <div style={{ display: "flex", gap: "6px", flexWrap: "wrap" }}>
                        {drivers.slice(0, 3).map((d, j) => (
                          <span key={j} style={{
                            fontSize: "10px", color: "#4a4845",
                            background: "rgba(255,255,255,0.03)",
                            border: "1px solid #1e1e1e", borderRadius: "4px",
                            padding: "2px 7px",
                          }}>{d}</span>
                        ))}
                      </div>
                    </div>
                    <div style={{ flexShrink: 0, textAlign: "right" }}>
                      <div style={{
                        fontFamily: "var(--font-mono), monospace", fontSize: "9px",
                        color: "#e36438", marginBottom: "4px",
                      }}>
                        {recs} market{recs !== 1 ? "s" : ""}
                      </div>
                      <div style={{
                        fontFamily: "var(--font-mono), monospace", fontSize: "9px",
                        color: "#2a2826",
                      }}>
                        {relTime(s.created_at)}
                      </div>
                    </div>
                  </div>
                </motion.button>
              );
            })}
          </div>
        </div>
      )}
    </div>
  );
}

function ChatThread({ messages, loading }: { messages: ChatMsg[]; loading: boolean }) {
  if (messages.length === 0 && !loading) return null;
  return (
    <div style={{ marginBottom: "28px" }}>
      <SectionLabel label="Belief Interview" dot="purple" />
      <div style={{ display: "flex", flexDirection: "column", gap: "14px" }}>
        {messages.map((msg, i) => (
          <motion.div
            key={i}
            initial={{ opacity: 0, y: 8 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ duration: 0.3 }}
          >
            {msg.role === "user" ? (
              <div style={{ display: "flex", justifyContent: "flex-end" }}>
                <div style={{
                  maxWidth: "76%",
                  background: "rgba(227,100,56,0.07)",
                  border: "1px solid rgba(227,100,56,0.16)",
                  borderRadius: "12px 12px 3px 12px",
                  padding: "11px 15px",
                  fontSize: "14px", color: "#ede9e3", lineHeight: 1.6,
                }}>
                  {msg.content}
                </div>
              </div>
            ) : (
              <div style={{ display: "flex", flexDirection: "column", gap: "7px", maxWidth: "84%" }}>
                <div style={{
                  background: "rgba(18,18,18,0.95)",
                  border: "1px solid #252525",
                  borderRadius: "12px 12px 12px 3px",
                  padding: "12px 16px",
                  fontSize: "14px", color: "#c5c0ba", lineHeight: 1.65,
                }}>
                  {msg.content}
                </div>
              </div>
            )}
          </motion.div>
        ))}
        {loading && (
          <div style={{
            fontFamily: "var(--font-mono), monospace", fontSize: "11px",
            color: "#3a3835", display: "flex", alignItems: "center", gap: "8px",
          }}>
            <span className="blink" style={{ color: "#e36438", fontSize: "7px" }}>●</span>
            thinking…
          </div>
        )}
      </div>
    </div>
  );
}

function ReplyBar({
  input, setInput, onKey, onSubmit, disabled,
}: {
  input: string;
  setInput: (v: string) => void;
  onKey: (e: React.KeyboardEvent) => void;
  onSubmit: () => void;
  disabled: boolean;
}) {
  return (
    <div style={{
      background: "rgba(14,14,14,0.95)",
      border: "1px solid #282828", borderRadius: "12px",
      padding: "6px 6px 6px 16px",
      display: "flex", gap: "8px", alignItems: "center",
      marginBottom: "32px",
      backdropFilter: "blur(20px)", WebkitBackdropFilter: "blur(20px)",
    }}>
      <input
        value={input}
        onChange={e => setInput(e.target.value)}
        onKeyDown={onKey}
        placeholder="Your reply…"
        disabled={disabled}
        autoFocus
        style={{
          flex: 1, background: "transparent", border: "none",
          fontSize: "13px", color: "#ede9e3",
          fontFamily: "var(--font-jakarta), system-ui, sans-serif",
          outline: "none", opacity: disabled ? 0.5 : 1,
        }}
      />
      <button
        onClick={onSubmit}
        disabled={disabled || !input.trim()}
        style={{
          background: disabled || !input.trim() ? "#181818" : "#e36438",
          color: "#fff", border: "none", borderRadius: "8px",
          padding: "8px 18px", fontSize: "11px",
          fontFamily: "var(--font-mono), monospace",
          fontWeight: 600, letterSpacing: "0.06em",
          transition: "background 0.15s",
          opacity: disabled || !input.trim() ? 0.4 : 1,
          cursor: disabled || !input.trim() ? "default" : "pointer",
        }}
        onMouseEnter={e => { if (!disabled && input.trim()) e.currentTarget.style.background = "#c4421a"; }}
        onMouseLeave={e => { if (!disabled && input.trim()) e.currentTarget.style.background = "#e36438"; }}
      >
        {disabled ? "…" : "Reply →"}
      </button>
    </div>
  );
}

function BeliefCard({ summary }: { summary: BeliefSummary }) {
  return (
    <div style={{ marginBottom: "28px" }}>
      <SectionLabel label="Your Belief" dot="purple" />
      <div style={{
        background: "rgba(18,18,18,0.98)",
        border: "1px solid rgba(91,156,246,0.18)",
        borderRadius: "14px", padding: "22px 24px",
        position: "relative", overflow: "hidden",
      }}>
        <div style={{
          position: "absolute", top: 0, left: 0, right: 0, height: "1px",
          background: "linear-gradient(90deg, transparent, rgba(91,156,246,0.5) 50%, transparent)",
        }} />
        <p style={{
          fontSize: "16px", fontWeight: 600, color: "#ede9e3",
          lineHeight: 1.5, marginBottom: "20px",
          fontStyle: "italic",
        }}>
          &ldquo;{summary.core_belief}&rdquo;
        </p>
        <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: "16px" }}>
          <MetaField label="Time Horizon" value={summary.time_horizon} />
          <MetaField label="Scope" value={summary.scope} />
          <div style={{ gridColumn: "1 / -1" }}>
            <div style={{
              fontFamily: "var(--font-mono), monospace", fontSize: "9px",
              color: "#3a3835", letterSpacing: "0.12em", textTransform: "uppercase",
              marginBottom: "7px",
            }}>Key Drivers</div>
            <div style={{ display: "flex", flexWrap: "wrap", gap: "5px" }}>
              {summary.key_drivers.slice(0, 5).map((d, i) => (
                <span key={i} style={{
                  fontSize: "11px", background: "rgba(255,255,255,0.04)",
                  border: "1px solid #252525", borderRadius: "5px",
                  padding: "3px 8px", color: "#9b9790",
                }}>{d}</span>
              ))}
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}

function MetaField({ label, value, color }: { label: string; value: string; color?: string }) {
  return (
    <div>
      <div style={{
        fontFamily: "var(--font-mono), monospace", fontSize: "9px",
        color: "#3a3835", letterSpacing: "0.12em", textTransform: "uppercase", marginBottom: "5px",
      }}>
        {label}
      </div>
      <div style={{ fontSize: "13px", color: color ?? "#9b9790", lineHeight: 1.4 }}>{value}</div>
    </div>
  );
}

function DomainGrid({ analysis }: { analysis: BeliefAnalysis }) {
  return (
    <div style={{ marginBottom: "8px" }}>
      <SectionLabel label="Domain Impact Map" dot="purple" />
      <div style={{
        display: "grid",
        gridTemplateColumns: "repeat(auto-fill, minmax(195px, 1fr))",
        gap: "5px",
      }}>
        {analysis.affected_domains.map((d: DomainAnalysis, i: number) => {
          const hi = d.relevance === "high";
          const med = d.relevance === "medium";
          return (
            <motion.div
              key={d.domain}
              initial={{ opacity: 0, scale: 0.94 }}
              animate={{ opacity: 1, scale: 1 }}
              transition={{ duration: 0.28, delay: i * 0.025 }}
              style={{
                background: hi ? "rgba(22,10,5,0.97)" : "rgba(13,13,13,0.97)",
                border: hi
                  ? "1px solid rgba(227,100,56,0.28)"
                  : med
                  ? "1px solid rgba(227,100,56,0.09)"
                  : "1px solid #191919",
                borderRadius: "9px", padding: "11px 13px",
                opacity: d.relevance === "low" ? 0.38 : 1,
              }}
            >
              <div style={{ display: "flex", alignItems: "center", gap: "7px", marginBottom: hi || med ? "7px" : 0 }}>
                <span style={{
                  width: "5px", height: "5px", borderRadius: "50%", flexShrink: 0,
                  background: hi ? "#e36438" : med ? "#6b3822" : "#252320",
                }} />
                <div style={{
                  fontFamily: "var(--font-mono), monospace", fontSize: "9px",
                  fontWeight: 700, textTransform: "uppercase", letterSpacing: "0.1em",
                  color: hi ? "#e36438" : med ? "#6b4830" : "#2a2826",
                  overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap",
                }}>
                  {d.domain.split(" (")[0]}
                </div>
              </div>
              {(hi || med) && (
                <div style={{
                  fontSize: "11px", color: "#4a4845", lineHeight: 1.45,
                  overflow: "hidden", display: "-webkit-box",
                  WebkitLineClamp: 2, WebkitBoxOrient: "vertical" as const,
                }}>
                  {d.mechanism}
                </div>
              )}
            </motion.div>
          );
        })}
      </div>
    </div>
  );
}

function SurpriseCallout({ text }: { text: string }) {
  return (
    <div style={{
      margin: "16px 0 28px",
      padding: "15px 20px",
      background: "rgba(91,156,246,0.04)",
      border: "1px solid rgba(91,156,246,0.14)",
      borderRadius: "11px",
      display: "flex", gap: "14px", alignItems: "flex-start",
    }}>
      <span style={{
        fontFamily: "var(--font-mono), monospace", fontSize: "9px",
        fontWeight: 700, textTransform: "uppercase", letterSpacing: "0.14em",
        color: "#5b9cf6", flexShrink: 0, paddingTop: "2px",
        whiteSpace: "nowrap",
      }}>
        Non-obvious bet
      </span>
      <div style={{ fontSize: "13px", color: "#9b9790", lineHeight: 1.6 }}>{text}</div>
    </div>
  );
}

function RecCard({
  rec, forecast, onExplore, onViewForecast, onRunForecast,
}: {
  rec: TradeRecommendation;
  forecast: SavedForecast | null;
  onExplore: () => void;
  onViewForecast: (id: number) => void;
  onRunForecast: () => void;
}) {
  const isYes = rec.direction === "YES";
  const dirColor = isYes ? "#4ade80" : "#f87171";

  const edge    = forecast ? forecast.forecaster_prob - forecast.kalshi_price : null;
  const edgePos = edge !== null && edge > 0.03;
  const edgeNeg = edge !== null && edge < -0.03;
  const edgeColor = edgePos ? "#5b9cf6" : edgeNeg ? "#f87171" : "#3a3835";

  return (
    <div
      style={{
        background: "rgba(18,18,18,0.98)",
        border: "1px solid #272727", borderRadius: "14px",
        overflow: "hidden", position: "relative",
        transition: "border-color 0.2s, box-shadow 0.2s",
      }}
      onMouseEnter={e => {
        e.currentTarget.style.borderColor = "rgba(227,100,56,0.28)";
        e.currentTarget.style.boxShadow = "0 0 0 1px rgba(227,100,56,0.07), 0 12px 40px rgba(0,0,0,0.7)";
      }}
      onMouseLeave={e => {
        e.currentTarget.style.borderColor = "#272727";
        e.currentTarget.style.boxShadow = "none";
      }}
    >
      {/* Score bar */}
      <div style={{
        position: "absolute", top: 0, left: 0,
        width: `${rec.score * 10}%`, height: "2px",
        background: "linear-gradient(90deg, #e36438, rgba(227,100,56,0.2))",
      }} />

      {/* Main body */}
      <div style={{ padding: "20px 22px" }}>
        <div style={{ display: "flex", justifyContent: "space-between", alignItems: "flex-start", gap: "16px" }}>
          <div style={{ flex: 1, minWidth: 0 }}>

            {/* Meta: category + event + series */}
            <div style={{ marginBottom: "10px" }}>
              {rec.category && (
                <div style={{
                  fontFamily: "var(--font-mono), monospace", fontSize: "9px",
                  fontWeight: 700, textTransform: "uppercase", letterSpacing: "0.16em",
                  color: "#e36438", marginBottom: "4px",
                }}>
                  {rec.category}
                </div>
              )}
              {rec.event_title && (
                <div style={{ fontSize: "12px", color: "#4a4845", lineHeight: 1.4, marginBottom: "2px" }}>
                  {rec.event_title}
                </div>
              )}
              {rec.series_ticker && (
                <div style={{
                  fontFamily: "var(--font-mono), monospace", fontSize: "9px",
                  color: "#2a2826", letterSpacing: "0.06em",
                }}>
                  {rec.series_ticker}
                </div>
              )}
            </div>

            {/* Direction badge + score */}
            <div style={{ display: "flex", alignItems: "center", gap: "8px", marginBottom: "10px", flexWrap: "wrap" }}>
              <span style={{
                fontFamily: "var(--font-mono), monospace", fontSize: "9px",
                fontWeight: 700, textTransform: "uppercase", letterSpacing: "0.12em",
                color: dirColor,
                background: isYes ? "rgba(74,222,128,0.08)" : "rgba(248,113,113,0.08)",
                border: `1px solid ${dirColor}30`,
                borderRadius: "4px", padding: "3px 9px",
              }}>
                BET {rec.direction}
              </span>
              <span style={{
                fontFamily: "var(--font-mono), monospace", fontSize: "9px",
                color: "#3a3835", letterSpacing: "0.06em",
              }}>
                {rec.score}/10
              </span>
            </div>

            {/* Question */}
            <div style={{
              fontSize: "14px", fontWeight: 600, color: "#ede9e3",
              lineHeight: 1.5, marginBottom: "10px",
            }}>
              {rec.question}
            </div>

            <div style={{ fontSize: "12px", color: "#6b6865", lineHeight: 1.55, marginBottom: "12px" }}>
              {rec.rationale}
            </div>

            <div style={{ fontSize: "11px", color: "#3a3835", lineHeight: 1.5, marginBottom: "14px", fontStyle: "italic" }}>
              {rec.relevance}
            </div>

            <div style={{ display: "flex", alignItems: "center", gap: "14px", flexWrap: "wrap" }}>
              <span style={{ fontFamily: "var(--font-mono), monospace", fontSize: "10px", color: "#3a3835" }}>
                closes {rec.close_date}
              </span>
              <button
                onClick={onExplore}
                style={{
                  background: "transparent", border: "none", padding: 0,
                  fontFamily: "var(--font-mono), monospace", fontSize: "10px",
                  color: "#e36438", letterSpacing: "0.04em", cursor: "pointer",
                  transition: "color 0.15s",
                }}
                onMouseEnter={e => e.currentTarget.style.color = "#ff7a50"}
                onMouseLeave={e => e.currentTarget.style.color = "#e36438"}
              >
                explore market →
              </button>
            </div>
          </div>

          <div style={{ flexShrink: 0, display: "flex", flexDirection: "column", alignItems: "center", gap: "6px" }}>
            <span style={{
              fontFamily: "var(--font-mono), monospace", fontSize: "9px",
              fontWeight: 700, textTransform: "uppercase", letterSpacing: "0.12em",
              color: "#3a3835",
            }}>
              Kalshi Price
            </span>
            <ProbabilityArc probability={rec.price} size={72} />
          </div>
        </div>
      </div>

      {/* Prism Forecast strip */}
      <div style={{
        borderTop: "1px solid #222",
        padding: "12px 22px",
        display: "flex", alignItems: "center", justifyContent: "space-between", gap: "12px",
        background: forecast ? "rgba(91,156,246,0.05)" : "rgba(227,100,56,0.03)",
      }}>
        <div style={{ display: "flex", alignItems: "center", gap: "10px", minWidth: 0 }}>
          <span style={{
            fontFamily: "var(--font-mono), monospace", fontSize: "9px",
            fontWeight: 700, textTransform: "uppercase", letterSpacing: "0.14em",
            color: forecast ? "#5b9cf6" : "#e36438", flexShrink: 0,
          }}>
            Prism Forecast
          </span>

          {forecast ? (
            <span style={{
              fontFamily: "var(--font-mono), monospace", fontSize: "10px",
              color: "#6b6865", letterSpacing: "0.04em",
              overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap",
            }}>
              <span style={{ color: "#9b9790" }}>{(forecast.forecaster_prob * 100).toFixed(1)}%</span>
              <span style={{ color: "#4a4845" }}> · mkt {(forecast.kalshi_price * 100).toFixed(1)}%</span>
              <span style={{ color: edgeColor, fontWeight: 600 }}>
                {" "}· {edgePos ? "+" : ""}{((edge ?? 0) * 100).toFixed(1)}pp
              </span>
            </span>
          ) : (
            <span style={{ fontSize: "11px", color: "#9b9790" }}>
              Ask Prism to forecast the probability of this event
            </span>
          )}
        </div>

        <button
          onClick={forecast ? () => onViewForecast(forecast.id) : onRunForecast}
          style={{
            background: "transparent", border: "none", padding: 0, flexShrink: 0,
            fontFamily: "var(--font-mono), monospace", fontSize: "10px",
            color: forecast ? "#5b9cf6" : "#e36438",
            letterSpacing: "0.04em", cursor: "pointer", transition: "color 0.15s",
            whiteSpace: "nowrap",
          }}
          onMouseEnter={e => e.currentTarget.style.color = forecast ? "#7fb3ff" : "#ff7a50"}
          onMouseLeave={e => e.currentTarget.style.color = forecast ? "#5b9cf6" : "#e36438"}
        >
          {forecast ? "view report →" : "forecast →"}
        </button>
      </div>
    </div>
  );
}

function SectionLabel({ label, dot }: { label: string; dot?: "orange" | "blue" | "purple" }) {
  const dotColor = dot === "orange" ? "#e36438" : dot === "purple" ? "#9b7fe8" : "#5b9cf6";
  return (
    <div style={{
      fontFamily: "var(--font-mono), monospace", fontSize: "10px", fontWeight: 700,
      textTransform: "uppercase", letterSpacing: "0.18em", color: "#9b9790",
      marginBottom: "14px", paddingBottom: "10px", borderBottom: "1px solid #1e1e1e",
      display: "flex", alignItems: "center", gap: "10px",
    }}>
      {dot && (
        <span
          className="blink"
          style={{ fontSize: "7px", color: dotColor, animationDelay: dot === "blue" ? "0.7s" : "0s" }}
        >●</span>
      )}
      {label}
    </div>
  );
}
