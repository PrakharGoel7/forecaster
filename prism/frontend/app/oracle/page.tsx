"use client";
import { useState, useEffect, useRef, useCallback } from "react";
import { useRouter } from "next/navigation";
import { motion, AnimatePresence } from "framer-motion";
import Header from "@/components/Header";
import GridOverlay from "@/components/GridOverlay";
import { oracleTurn, streamOraclePipeline } from "@/lib/api";
import type {
  OracleChatMessage,
  OracleDomain,
  OracleRecommendation,
} from "@/lib/types";

type Phase = "input" | "chat" | "pipeline" | "results";
type StageStatus = "waiting" | "running" | "done";

const STAGE_LABELS: Record<string, string> = {
  analyst:  "Mapping domain impact",
  screener: "Screening markets",
  markets:  "Fetching live data",
  curator:  "Curating best bets",
};

const STAGE_ORDER = ["analyst", "screener", "markets", "curator"];

export default function OraclePage() {
  const router = useRouter();

  // ── Phase ──────────────────────────────────────────────────────────────────
  const [phase, setPhase] = useState<Phase>("input");

  // ── Input ──────────────────────────────────────────────────────────────────
  const [belief, setBelief] = useState("");

  // ── Chat ───────────────────────────────────────────────────────────────────
  const [chatMsgs, setChatMsgs]     = useState<OracleChatMessage[]>([]);
  const [history, setHistory]       = useState<unknown[]>([]);
  const [questionCount, setQuestionCount] = useState(0);
  const [chatInput, setChatInput]   = useState("");
  const [isLoading, setIsLoading]   = useState(false);
  const [errorMsg, setErrorMsg]     = useState("");
  const chatEndRef = useRef<HTMLDivElement>(null);

  // ── Pipeline ───────────────────────────────────────────────────────────────
  const [stages, setStages] = useState<Record<string, StageStatus>>(
    Object.fromEntries(STAGE_ORDER.map(s => [s, "waiting" as StageStatus]))
  );
  const [analystDomains, setAnalystDomains] = useState<OracleDomain[]>([]);
  const [analystInsight, setAnalystInsight] = useState("");
  const [beliefSummary, setBeliefSummary]   = useState<Record<string, unknown> | null>(null);
  const [pipelineError, setPipelineError]   = useState("");

  // ── Results ────────────────────────────────────────────────────────────────
  const [recommendations, setRecommendations] = useState<OracleRecommendation[]>([]);
  const [showChat, setShowChat] = useState(false);

  // Auto-scroll chat
  useEffect(() => {
    chatEndRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [chatMsgs, isLoading]);

  // ── Start: submit initial belief ───────────────────────────────────────────
  const submitBelief = useCallback(async () => {
    const text = belief.trim();
    if (!text || isLoading) return;
    setIsLoading(true);
    setErrorMsg("");
    setPhase("chat");
    setChatMsgs([{ role: "user", content: text }]);

    try {
      const res = await oracleTurn([], text);
      setHistory(res.history);
      if (res.status === "finalized" && res.belief_summary) {
        setBeliefSummary(res.belief_summary);
        startPipeline(res.belief_summary);
      } else {
        setChatMsgs(prev => [...prev, {
          role: "oracle",
          content: res.agent_message ?? "",
          searchQueries: res.search_queries,
        }]);
        setQuestionCount(1);
      }
    } catch (e) {
      setErrorMsg(e instanceof Error ? e.message : "Something went wrong");
      setPhase("input");
    } finally {
      setIsLoading(false);
    }
  }, [belief, isLoading]);

  // ── Chat: send follow-up ───────────────────────────────────────────────────
  const sendMessage = useCallback(async () => {
    const text = chatInput.trim();
    if (!text || isLoading) return;
    setChatInput("");
    setIsLoading(true);
    setErrorMsg("");
    setChatMsgs(prev => [...prev, { role: "user", content: text }]);

    try {
      const res = await oracleTurn(history, text);
      setHistory(res.history);
      if (res.status === "finalized" && res.belief_summary) {
        setBeliefSummary(res.belief_summary);
        startPipeline(res.belief_summary);
      } else {
        setChatMsgs(prev => [...prev, {
          role: "oracle",
          content: res.agent_message ?? "",
          searchQueries: res.search_queries,
        }]);
        setQuestionCount(prev => prev + 1);
      }
    } catch (e) {
      setErrorMsg(e instanceof Error ? e.message : "Something went wrong");
    } finally {
      setIsLoading(false);
    }
  }, [chatInput, history, isLoading]);

  // ── Pipeline ───────────────────────────────────────────────────────────────
  const startPipeline = useCallback((summary: Record<string, unknown>) => {
    setPhase("pipeline");
    streamOraclePipeline(summary, msg => {
      if (msg.type === "stage") {
        setStages(prev => ({ ...prev, [msg.stage]: msg.status }));
        if (msg.status === "done" && msg.stage === "analyst" && msg.data) {
          const d = msg.data as { domains: OracleDomain[]; insight: string };
          setAnalystDomains(d.domains ?? []);
          setAnalystInsight(d.insight ?? "");
        }
      } else if (msg.type === "complete") {
        setRecommendations(msg.data.recommendations);
        setAnalystDomains(msg.data.analysis.domains);
        setAnalystInsight(msg.data.analysis.insight);
        setPhase("results");
      } else if (msg.type === "error") {
        setPipelineError(msg.message);
      }
    });
  }, []);

  const onInputKey = (e: React.KeyboardEvent<HTMLTextAreaElement>) => {
    if (e.key === "Enter" && !e.shiftKey) { e.preventDefault(); submitBelief(); }
  };
  const onChatKey = (e: React.KeyboardEvent<HTMLTextAreaElement>) => {
    if (e.key === "Enter" && !e.shiftKey) { e.preventDefault(); sendMessage(); }
  };

  const coreBelief = (beliefSummary?.core_belief as string) ?? belief;

  // ── Render ─────────────────────────────────────────────────────────────────
  return (
    <div style={{ minHeight: "100vh", background: "#080808", position: "relative" }}>
      <Header />
      <GridOverlay />

      <div style={{ position: "relative", zIndex: 10 }}>

        {/* ── Phase: INPUT ────────────────────────────────────────────────── */}
        <AnimatePresence>
          {phase === "input" && (
            <motion.div
              key="input"
              initial={{ opacity: 0, y: 16 }}
              animate={{ opacity: 1, y: 0 }}
              exit={{ opacity: 0, y: -12 }}
              transition={{ duration: 0.4 }}
              style={{
                minHeight: "100vh", display: "flex", flexDirection: "column",
                alignItems: "center", justifyContent: "center",
                padding: "40px 24px",
              }}
            >
              <div style={{ width: "100%", maxWidth: "620px" }}>
                {/* Label */}
                <div style={{
                  fontFamily: "var(--font-mono), monospace", fontSize: "10px",
                  fontWeight: 700, letterSpacing: "0.22em", textTransform: "uppercase",
                  color: "#e36438", marginBottom: "10px",
                  display: "flex", alignItems: "center", gap: "8px",
                }}>
                  <span className="blink" style={{ fontSize: "7px" }}>●</span>
                  ORACLE
                </div>

                <h1 style={{
                  fontSize: "28px", fontWeight: 700, color: "#ede9e3",
                  lineHeight: 1.3, marginBottom: "8px",
                }}>
                  Turn your belief into prediction market bets.
                </h1>
                <p style={{
                  fontSize: "13px", color: "#6b6865", lineHeight: 1.75,
                  marginBottom: "28px",
                }}>
                  Describe how you think the future will unfold. Oracle interviews you to understand your conviction, then surfaces the best Kalshi markets to express it.
                </p>

                {/* Textarea */}
                <div style={{
                  background: "rgba(14,14,14,0.95)",
                  border: "1px solid #282828", borderRadius: "14px",
                  padding: "18px", marginBottom: "12px",
                  boxShadow: "0 0 0 1px rgba(255,255,255,0.02), 0 8px 32px rgba(0,0,0,0.5)",
                  backdropFilter: "blur(20px)",
                }}>
                  <textarea
                    value={belief}
                    onChange={e => setBelief(e.target.value)}
                    onKeyDown={onInputKey}
                    placeholder="I believe that…"
                    rows={4}
                    style={{
                      width: "100%", background: "transparent", border: "none",
                      resize: "none", fontSize: "14px", color: "#ede9e3",
                      fontFamily: "var(--font-jakarta), system-ui, sans-serif",
                      lineHeight: 1.7, outline: "none",
                    }}
                  />
                </div>

                {errorMsg && (
                  <div style={{
                    fontSize: "11px", color: "#f87171", fontFamily: "var(--font-mono), monospace",
                    marginBottom: "10px",
                  }}>{errorMsg}</div>
                )}

                <div style={{ display: "flex", justifyContent: "flex-end" }}>
                  <button
                    onClick={submitBelief}
                    disabled={!belief.trim() || isLoading}
                    style={{
                      background: belief.trim() ? "#e36438" : "#181818",
                      color: "#fff", border: "none", borderRadius: "10px",
                      padding: "11px 24px", fontSize: "12px",
                      fontFamily: "var(--font-mono), monospace", fontWeight: 600,
                      letterSpacing: "0.06em", transition: "background 0.15s",
                      opacity: isLoading ? 0.5 : 1,
                    }}
                    onMouseEnter={e => { if (belief.trim()) e.currentTarget.style.background = "#c4421a"; }}
                    onMouseLeave={e => { if (belief.trim()) e.currentTarget.style.background = "#e36438"; }}
                  >
                    {isLoading ? "…" : "analyze →"}
                  </button>
                </div>
              </div>
            </motion.div>
          )}
        </AnimatePresence>

        {/* ── Phase: CHAT ─────────────────────────────────────────────────── */}
        {phase === "chat" && (
          <motion.div
            key="chat"
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            transition={{ duration: 0.3 }}
            style={{
              minHeight: "100vh", display: "flex", flexDirection: "column",
              alignItems: "center", padding: "84px 24px 40px",
            }}
          >
            <div style={{ width: "100%", maxWidth: "620px", flex: 1, display: "flex", flexDirection: "column" }}>

              {/* Chat thread */}
              <div style={{ flex: 1, overflowY: "auto", paddingBottom: "16px" }}>
                {chatMsgs.map((msg, i) => (
                  <motion.div
                    key={i}
                    initial={{ opacity: 0, y: 8 }}
                    animate={{ opacity: 1, y: 0 }}
                    transition={{ duration: 0.3 }}
                    style={{ marginBottom: "24px" }}
                  >
                    <div style={{
                      fontFamily: "var(--font-mono), monospace", fontSize: "9px",
                      fontWeight: 700, letterSpacing: "0.14em", textTransform: "uppercase",
                      color: msg.role === "oracle" ? "#e36438" : "#3a3835",
                      marginBottom: "6px",
                    }}>
                      {msg.role === "oracle" ? "Oracle" : "You"}
                    </div>
                    {msg.searchQueries && msg.searchQueries.length > 0 && (
                      <div style={{
                        fontFamily: "var(--font-mono), monospace", fontSize: "10px",
                        color: "#2a2826", marginBottom: "6px", fontStyle: "italic",
                      }}>
                        {msg.searchQueries.map((q, qi) => (
                          <span key={qi}>· searching: {q}{qi < (msg.searchQueries?.length ?? 0) - 1 ? "  " : ""}</span>
                        ))}
                      </div>
                    )}
                    <div style={{
                      fontSize: "14px", color: "#ede9e3", lineHeight: 1.75,
                      fontFamily: "var(--font-jakarta), system-ui, sans-serif",
                    }}>
                      {msg.content}
                    </div>
                  </motion.div>
                ))}

                {/* Thinking indicator */}
                {isLoading && (
                  <div style={{
                    fontFamily: "var(--font-mono), monospace", fontSize: "11px",
                    color: "#e36438", display: "flex", alignItems: "center", gap: "8px",
                    marginBottom: "24px",
                  }}>
                    <span className="blink" style={{ fontSize: "7px" }}>●</span>
                    Oracle is thinking…
                  </div>
                )}
                <div ref={chatEndRef} />
              </div>

              {/* Input bar */}
              <div>
                {errorMsg && (
                  <div style={{
                    fontSize: "11px", color: "#f87171",
                    fontFamily: "var(--font-mono), monospace", marginBottom: "8px",
                  }}>{errorMsg}</div>
                )}
                <div style={{
                  background: "rgba(14,14,14,0.95)", border: "1px solid #282828",
                  borderRadius: "12px", padding: "12px 12px 12px 16px",
                  display: "flex", gap: "8px", alignItems: "flex-end",
                  backdropFilter: "blur(20px)",
                }}>
                  <textarea
                    value={chatInput}
                    onChange={e => setChatInput(e.target.value)}
                    onKeyDown={onChatKey}
                    placeholder="Your answer…"
                    rows={2}
                    style={{
                      flex: 1, background: "transparent", border: "none",
                      resize: "none", fontSize: "13px", color: "#ede9e3",
                      fontFamily: "var(--font-jakarta), system-ui, sans-serif",
                      lineHeight: 1.6, outline: "none",
                    }}
                  />
                  <button
                    onClick={sendMessage}
                    disabled={!chatInput.trim() || isLoading}
                    style={{
                      background: chatInput.trim() ? "#e36438" : "#181818",
                      color: "#fff", border: "none", borderRadius: "8px",
                      padding: "8px 16px", fontSize: "11px",
                      fontFamily: "var(--font-mono), monospace", fontWeight: 600,
                      letterSpacing: "0.06em", flexShrink: 0,
                      transition: "background 0.15s", opacity: isLoading ? 0.5 : 1,
                    }}
                  >
                    send
                  </button>
                </div>
                {questionCount > 0 && (
                  <div style={{
                    fontFamily: "var(--font-mono), monospace", fontSize: "9px",
                    color: "#2a2826", marginTop: "8px", textAlign: "right",
                    letterSpacing: "0.1em",
                  }}>
                    Question {questionCount} of 3
                  </div>
                )}
              </div>
            </div>
          </motion.div>
        )}

        {/* ── Phase: PIPELINE ─────────────────────────────────────────────── */}
        {phase === "pipeline" && (
          <motion.div
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            transition={{ duration: 0.4 }}
            style={{
              minHeight: "100vh", display: "flex", flexDirection: "column",
              alignItems: "center", padding: "100px 24px 60px",
            }}
          >
            <div style={{ width: "100%", maxWidth: "560px" }}>

              {/* Belief echo */}
              <div style={{
                background: "#0f0f0f", border: "1px solid #1c1c1c",
                borderRadius: "12px", padding: "16px 20px", marginBottom: "32px",
              }}>
                <div style={{
                  fontFamily: "var(--font-mono), monospace", fontSize: "9px",
                  fontWeight: 700, letterSpacing: "0.14em", textTransform: "uppercase",
                  color: "#3a3835", marginBottom: "6px",
                }}>Belief captured</div>
                <div style={{ fontSize: "13px", color: "#9b9790", lineHeight: 1.65 }}>
                  {coreBelief}
                </div>
              </div>

              {/* Pipeline stages */}
              <div style={{ display: "flex", flexDirection: "column", gap: "0" }}>
                {STAGE_ORDER.map((stage, i) => {
                  const status = stages[stage];
                  return (
                    <div key={stage}>
                      <motion.div
                        initial={{ opacity: 0, x: -8 }}
                        animate={{ opacity: 1, x: 0 }}
                        transition={{ duration: 0.3, delay: i * 0.06 }}
                        style={{
                          display: "flex", alignItems: "flex-start", gap: "14px",
                          padding: "14px 0",
                          borderBottom: i < STAGE_ORDER.length - 1 ? "1px solid #111" : "none",
                        }}
                      >
                        {/* Status icon */}
                        <div style={{
                          width: "18px", height: "18px", flexShrink: 0,
                          display: "flex", alignItems: "center", justifyContent: "center",
                          marginTop: "1px",
                        }}>
                          {status === "done"    && <span style={{ color: "#4ade80", fontSize: "12px" }}>✓</span>}
                          {status === "running" && <span className="blink" style={{ color: "#e36438", fontSize: "8px" }}>●</span>}
                          {status === "waiting" && <span style={{ color: "#1e1e1e", fontSize: "8px" }}>●</span>}
                        </div>

                        <div style={{ flex: 1 }}>
                          <div style={{
                            fontFamily: "var(--font-mono), monospace", fontSize: "11px",
                            fontWeight: status === "waiting" ? 400 : 600,
                            color: status === "done" ? "#9b9790" : status === "running" ? "#ede9e3" : "#2a2826",
                            letterSpacing: "0.04em",
                          }}>
                            {STAGE_LABELS[stage]}
                            {status === "running" && (
                              <span style={{ color: "#e36438" }}> …</span>
                            )}
                          </div>

                          {/* Analyst domains shown as they stream in */}
                          {stage === "analyst" && status === "done" && analystDomains.length > 0 && (
                            <div style={{ marginTop: "10px", display: "flex", flexDirection: "column", gap: "5px" }}>
                              {analystDomains.map((d, di) => (
                                <motion.div
                                  key={d.domain}
                                  initial={{ opacity: 0, x: -4 }}
                                  animate={{ opacity: 1, x: 0 }}
                                  transition={{ duration: 0.2, delay: di * 0.04 }}
                                  style={{ display: "flex", gap: "8px", alignItems: "baseline" }}
                                >
                                  <span style={{
                                    fontFamily: "var(--font-mono), monospace", fontSize: "8px",
                                    fontWeight: 700, color: d.relevance === "high" ? "#e36438" : "#5b9cf6",
                                    letterSpacing: "0.08em", flexShrink: 0,
                                  }}>
                                    {d.relevance.toUpperCase()}
                                  </span>
                                  <span style={{ fontSize: "11px", color: "#6b6865", lineHeight: 1.5 }}>
                                    <span style={{ color: "#9b9790" }}>{d.domain.split(" (")[0]}</span>
                                    {" — "}{d.mechanism.slice(0, 80)}{d.mechanism.length > 80 ? "…" : ""}
                                  </span>
                                </motion.div>
                              ))}
                            </div>
                          )}
                        </div>
                      </motion.div>
                    </div>
                  );
                })}
              </div>

              {pipelineError && (
                <div style={{
                  marginTop: "20px", padding: "12px 16px",
                  background: "#180a0a", border: "1px solid #3a1515",
                  borderRadius: "8px", fontSize: "11px", color: "#f87171",
                  fontFamily: "var(--font-mono), monospace",
                }}>{pipelineError}</div>
              )}
            </div>
          </motion.div>
        )}

        {/* ── Phase: RESULTS ──────────────────────────────────────────────── */}
        {phase === "results" && (
          <motion.div
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            transition={{ duration: 0.5 }}
            style={{ padding: "84px 32px 80px", maxWidth: "1280px", margin: "0 auto" }}
          >
            {/* Belief strip */}
            <div style={{
              background: "#0f0f0f", border: "1px solid #1c1c1c",
              borderRadius: "12px", padding: "14px 20px", marginBottom: "28px",
              display: "flex", alignItems: "flex-start", justifyContent: "space-between", gap: "16px",
            }}>
              <div>
                <div style={{
                  fontFamily: "var(--font-mono), monospace", fontSize: "9px",
                  fontWeight: 700, letterSpacing: "0.14em", textTransform: "uppercase",
                  color: "#3a3835", marginBottom: "5px",
                }}>Your belief</div>
                <div style={{ fontSize: "13px", color: "#9b9790", lineHeight: 1.6 }}>
                  {coreBelief}
                </div>
              </div>
              <button
                onClick={() => setShowChat(v => !v)}
                style={{
                  background: "transparent", border: "1px solid #1e1e1e",
                  borderRadius: "6px", padding: "5px 12px",
                  fontFamily: "var(--font-mono), monospace", fontSize: "9px",
                  color: "#3a3835", flexShrink: 0, transition: "all 0.15s",
                }}
                onMouseEnter={e => { e.currentTarget.style.color = "#6b6865"; e.currentTarget.style.borderColor = "#2a2a2a"; }}
                onMouseLeave={e => { e.currentTarget.style.color = "#3a3835"; e.currentTarget.style.borderColor = "#1e1e1e"; }}
              >
                {showChat ? "hide chat ▴" : "view chat ▾"}
              </button>
            </div>

            {/* Expandable chat transcript */}
            {showChat && (
              <motion.div
                initial={{ opacity: 0, height: 0 }}
                animate={{ opacity: 1, height: "auto" }}
                exit={{ opacity: 0, height: 0 }}
                style={{
                  background: "#0a0a0a", border: "1px solid #1a1a1a",
                  borderRadius: "12px", padding: "20px 24px", marginBottom: "24px",
                  maxHeight: "320px", overflowY: "auto",
                }}
              >
                {chatMsgs.map((msg, i) => (
                  <div key={i} style={{ marginBottom: "16px" }}>
                    <div style={{
                      fontFamily: "var(--font-mono), monospace", fontSize: "9px",
                      fontWeight: 700, letterSpacing: "0.12em", textTransform: "uppercase",
                      color: msg.role === "oracle" ? "#e36438" : "#3a3835", marginBottom: "4px",
                    }}>
                      {msg.role === "oracle" ? "Oracle" : "You"}
                    </div>
                    <div style={{ fontSize: "12px", color: "#6b6865", lineHeight: 1.7 }}>
                      {msg.content}
                    </div>
                  </div>
                ))}
              </motion.div>
            )}

            {/* Two-column: Domain Map | Markets */}
            <div style={{
              display: "grid",
              gridTemplateColumns: "340px 1fr",
              gap: "20px",
              alignItems: "start",
            }}>

              {/* LEFT — Domain Map */}
              <div style={{
                background: "#0f0f0f", border: "1px solid #1c1c1c",
                borderRadius: "16px", overflow: "hidden", position: "sticky", top: "76px",
              }}>
                <div style={{ height: "2px", background: "linear-gradient(90deg, #e36438, #5b9cf6 60%, transparent)" }} />
                <div style={{ padding: "20px" }}>
                  <SectionLabel dot="orange">Domain Map</SectionLabel>

                  <div style={{ display: "flex", flexDirection: "column", gap: "12px" }}>
                    {analystDomains.map((d, i) => (
                      <motion.div
                        key={d.domain}
                        initial={{ opacity: 0, x: -6 }}
                        animate={{ opacity: 1, x: 0 }}
                        transition={{ duration: 0.25, delay: i * 0.04 }}
                      >
                        <div style={{ display: "flex", gap: "8px", alignItems: "baseline", marginBottom: "3px" }}>
                          <span style={{
                            fontFamily: "var(--font-mono), monospace", fontSize: "8px",
                            fontWeight: 700, letterSpacing: "0.1em",
                            color: d.relevance === "high" ? "#e36438" : "#5b9cf6",
                            flexShrink: 0,
                          }}>
                            {d.relevance.toUpperCase()}
                          </span>
                          <span style={{
                            fontFamily: "var(--font-mono), monospace", fontSize: "10px",
                            fontWeight: 600, color: "#9b9790",
                          }}>
                            {d.domain.split(" (")[0]}
                          </span>
                        </div>
                        <div style={{ fontSize: "11px", color: "#6b6865", lineHeight: 1.6, paddingLeft: "32px" }}>
                          {d.mechanism}
                        </div>
                      </motion.div>
                    ))}
                  </div>

                  {analystInsight && (
                    <div style={{
                      marginTop: "20px", padding: "12px 14px",
                      background: "rgba(91,156,246,0.05)", border: "1px solid rgba(91,156,246,0.15)",
                      borderRadius: "8px",
                    }}>
                      <div style={{
                        fontFamily: "var(--font-mono), monospace", fontSize: "8px",
                        fontWeight: 700, letterSpacing: "0.12em", textTransform: "uppercase",
                        color: "#5b9cf6", marginBottom: "6px",
                      }}>Key Insight</div>
                      <div style={{ fontSize: "11px", color: "#9b9790", lineHeight: 1.65 }}>
                        {analystInsight}
                      </div>
                    </div>
                  )}
                </div>
              </div>

              {/* RIGHT — Market cards */}
              <div>
                <SectionLabel dot="orange" style={{ marginBottom: "14px" }}>
                  Recommended Markets ({recommendations.length})
                </SectionLabel>

                <div style={{ display: "flex", flexDirection: "column", gap: "10px" }}>
                  {recommendations.map((r, i) => (
                    <MarketCard
                      key={r.ticker}
                      rec={r}
                      index={i}
                      onForecast={() => router.push(
                        `/market/${r.event_ticker}?title=${encodeURIComponent(r.question)}&cat=Oracle`
                      )}
                    />
                  ))}
                </div>
              </div>
            </div>
          </motion.div>
        )}
      </div>
    </div>
  );
}

// ── Sub-components ─────────────────────────────────────────────────────────────

function SectionLabel({
  dot, children, style,
}: {
  dot: "orange" | "blue";
  children: React.ReactNode;
  style?: React.CSSProperties;
}) {
  return (
    <div style={{
      fontFamily: "var(--font-mono), monospace", fontSize: "9px", fontWeight: 700,
      textTransform: "uppercase", letterSpacing: "0.18em", color: "#9b9790",
      marginBottom: "16px", paddingBottom: "10px", borderBottom: "1px solid #1a1a1a",
      display: "flex", alignItems: "center", gap: "8px",
      ...style,
    }}>
      <span
        className="blink"
        style={{ fontSize: "6px", color: dot === "orange" ? "#e36438" : "#5b9cf6", animationDelay: dot === "blue" ? "0.7s" : "0s" }}
      >●</span>
      {children}
    </div>
  );
}

function MarketCard({
  rec, index, onForecast,
}: {
  rec: OracleRecommendation;
  index: number;
  onForecast: () => void;
}) {
  const [hovered, setHovered] = useState(false);
  const isYes = rec.direction === "YES";

  return (
    <motion.div
      initial={{ opacity: 0, y: 10 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.3, delay: index * 0.05 }}
      onMouseEnter={() => setHovered(true)}
      onMouseLeave={() => setHovered(false)}
      style={{
        background: hovered ? "#121212" : "#0f0f0f",
        border: `1px solid ${hovered ? "#252525" : "#1c1c1c"}`,
        borderRadius: "14px", overflow: "hidden",
        transition: "background 0.15s, border-color 0.15s",
      }}
    >
      <div style={{ height: "2px", background: isYes ? "rgba(74,222,128,0.4)" : "rgba(248,113,113,0.4)" }} />
      <div style={{ padding: "16px 18px" }}>

        {/* Top row: question + direction badge */}
        <div style={{ display: "flex", alignItems: "flex-start", justifyContent: "space-between", gap: "12px", marginBottom: "10px" }}>
          <div style={{ fontSize: "13px", fontWeight: 600, color: "#ede9e3", lineHeight: 1.5, flex: 1 }}>
            {rec.question}
          </div>
          <div style={{
            fontFamily: "var(--font-mono), monospace", fontSize: "9px", fontWeight: 700,
            letterSpacing: "0.1em", padding: "4px 10px", borderRadius: "5px", flexShrink: 0,
            background: isYes ? "rgba(74,222,128,0.12)" : "rgba(248,113,113,0.12)",
            border: `1px solid ${isYes ? "rgba(74,222,128,0.25)" : "rgba(248,113,113,0.25)"}`,
            color: isYes ? "#4ade80" : "#f87171",
          }}>
            BET {rec.direction}
          </div>
        </div>

        {/* Stats row */}
        <div style={{
          display: "flex", gap: "20px", marginBottom: "10px",
          fontFamily: "var(--font-mono), monospace", fontSize: "10px",
        }}>
          <span style={{ color: "#2a2826" }}>YES  <span style={{ color: "#ede9e3", fontWeight: 700 }}>{(rec.price * 100).toFixed(0)}¢</span></span>
          <span style={{ color: "#2a2826" }}>Closes  <span style={{ color: "#e36438" }}>{rec.close_date}</span></span>
          <span style={{ color: "#2a2826" }}>Score  <span style={{ color: "#9b9790" }}>{rec.score}/10</span></span>
        </div>

        {/* Rationale */}
        <div style={{ fontSize: "12px", color: "#6b6865", lineHeight: 1.65, marginBottom: "14px" }}>
          {rec.rationale}
        </div>

        {/* Footer: forecast button */}
        <button
          onClick={onForecast}
          style={{
            background: "transparent", border: "1px solid #1e1e1e",
            borderRadius: "7px", padding: "7px 14px",
            fontFamily: "var(--font-mono), monospace", fontSize: "10px",
            color: "#3a3835", transition: "all 0.15s",
          }}
          onMouseEnter={e => { e.currentTarget.style.color = "#e36438"; e.currentTarget.style.borderColor = "rgba(227,100,56,0.3)"; }}
          onMouseLeave={e => { e.currentTarget.style.color = "#3a3835"; e.currentTarget.style.borderColor = "#1e1e1e"; }}
        >
          forecast →
        </button>
      </div>
    </motion.div>
  );
}
