"use client";

import { Suspense, useEffect, useMemo, useRef, useState } from "react";
import Link from "next/link";
import { useRouter, useSearchParams } from "next/navigation";
import Header from "@/components/Header";
import GridOverlay from "@/components/GridOverlay";
import { tradingChat, streamTradingAnalysis, listBaskets, getBasket } from "@/lib/api";
import type { BeliefAnalysis, BeliefSummary, PredictionBasket, SavedBasket } from "@/lib/types";

type Mode = "instant" | "thinking";
type Stage = "idle" | "chatting" | "analyzing" | "done" | "error";

interface ChatMsg {
  role: "user" | "assistant";
  content: string;
}

export default function TradingPage() {
  return <Suspense><TradingPageInner /></Suspense>;
}

function TradingPageInner() {
  const router = useRouter();
  const searchParams = useSearchParams();
  const initialBelief = searchParams.get("belief") ?? "";
  const basketParam = searchParams.get("basket");
  const [mode, setMode] = useState<Mode>("thinking");
  const [stage, setStage] = useState<Stage>("idle");
  const [input, setInput] = useState(initialBelief);
  const [chatMessages, setChatMessages] = useState<ChatMsg[]>([]);
  const [apiHistory, setApiHistory] = useState<Record<string, unknown>[]>([]);
  const [beliefSummary, setBeliefSummary] = useState<BeliefSummary | null>(null);
  const [analysis, setAnalysis] = useState<BeliefAnalysis | null>(null);
  const [basket, setBasket] = useState<PredictionBasket | null>(null);
  const [savedBaskets, setSavedBaskets] = useState<SavedBasket[]>([]);
  const [basketId, setBasketId] = useState<number | null>(basketParam ? Number(basketParam) : null);
  const [screenedCount, setScreenedCount] = useState(0);
  const [progressLabel, setProgressLabel] = useState("");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");
  const bootstrapped = useRef(false);

  useEffect(() => {
    listBaskets(20).then(setSavedBaskets).catch(() => {});
  }, []);

  useEffect(() => {
    if (!basketId) return;
    getBasket(basketId).then((saved) => {
      setBeliefSummary(JSON.parse(saved.belief_summary_json));
      setAnalysis(JSON.parse(saved.analysis_json));
      setBasket(JSON.parse(saved.basket_json));
      setMode(saved.mode);
      setStage("done");
    }).catch(() => {});
  }, [basketId]);

  useEffect(() => {
    if (!initialBelief.trim() || bootstrapped.current) return;
    bootstrapped.current = true;
    setStage("chatting");
    void sendMessage(initialBelief, []);
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [initialBelief]);

  const stepLabel = useMemo(() => {
    if (mode === "instant") return "1 follow-up max";
    return "up to 3 follow-ups";
  }, [mode]);

  function resetFlow() {
    setStage("idle");
    setInput("");
    setChatMessages([]);
    setApiHistory([]);
    setBeliefSummary(null);
    setAnalysis(null);
    setBasket(null);
    setBasketId(null);
    setScreenedCount(0);
    setProgressLabel("");
    setError("");
    router.replace("/trading", { scroll: false });
  }

  function startAnalysis(summary: BeliefSummary) {
    streamTradingAnalysis(summary, mode, (msg) => {
      if (msg.type === "progress") setProgressLabel(msg.label);
      else if (msg.type === "analyst_done") setAnalysis(msg.analysis);
      else if (msg.type === "screener_done") setScreenedCount(msg.count);
      else if (msg.type === "basket_done") {
        setBasket(msg.basket);
        setBasketId(msg.basket_id ?? null);
        setStage("done");
        setProgressLabel("");
        if (msg.basket_id) {
          router.replace(`/trading?basket=${msg.basket_id}`, { scroll: false });
        }
        listBaskets(20).then(setSavedBaskets).catch(() => {});
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
    setChatMessages((prev) => [...prev, { role: "user", content: message }]);
    try {
      const result = await tradingChat(history, message, mode);
      setApiHistory(result.history);
      if (result.status === "finalized" && result.belief_summary) {
        setBeliefSummary(result.belief_summary);
        setStage("analyzing");
        startAnalysis(result.belief_summary);
      } else if (result.agent_message) {
        setChatMessages((prev) => [...prev, { role: "assistant", content: result.agent_message! }]);
      }
    } catch (err) {
      setError(err instanceof Error ? err.message : "Request failed");
      setStage("error");
    } finally {
      setLoading(false);
    }
  }

  function onSubmitInitial() {
    if (!input.trim()) return;
    setStage("chatting");
    void sendMessage(input, []);
  }

  function onSubmitReply() {
    void sendMessage(input, apiHistory);
  }

  return (
    <div style={{ minHeight: "100vh", background: "#080808", position: "relative" }}>
      <Header />
      <GridOverlay />
      <div style={{ position: "relative", zIndex: 10, paddingTop: 56 }}>
        <div style={{ maxWidth: 1040, margin: "0 auto", padding: "40px 24px 80px" }}>
          <div style={{ display: "grid", gridTemplateColumns: "minmax(0, 1fr) 320px", gap: 24 }}>
            <div>
              {stage === "idle" && (
                <IdleComposer
                  mode={mode}
                  setMode={setMode}
                  input={input}
                  setInput={setInput}
                  stepLabel={stepLabel}
                  onSubmit={onSubmitInitial}
                />
              )}

              {stage !== "idle" && (
                <div style={{ display: "grid", gap: 18 }}>
                  <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center" }}>
                    <div>
                      <div style={{ color: "#e36438", fontSize: 11, textTransform: "uppercase", letterSpacing: "0.16em", fontFamily: "var(--font-mono), monospace" }}>
                        Prediction Market ETF Builder
                      </div>
                      <div style={{ color: "#ede9e3", fontSize: 28, fontWeight: 600, letterSpacing: "-0.03em" }}>
                        Build a shareable basket
                      </div>
                    </div>
                    <button onClick={resetFlow} style={ghostButtonStyle}>New basket</button>
                  </div>

                  <Card>
                    <div style={{ color: "#8f877e", fontSize: 13, marginBottom: 10 }}>
                      Mode: <span style={{ color: "#ede9e3" }}>{mode === "instant" ? "Instant" : "Thinking"}</span>
                    </div>
                    <ChatThread messages={chatMessages} />
                    {stage === "chatting" && (
                      <div style={{ display: "grid", gap: 10, marginTop: 16 }}>
                        <textarea
                          value={input}
                          onChange={(e) => setInput(e.target.value)}
                          rows={3}
                          placeholder="Answer the follow-up..."
                          style={textareaStyle}
                        />
                        <button onClick={onSubmitReply} style={primaryButtonStyle}>Continue</button>
                      </div>
                    )}
                  </Card>

                  {beliefSummary && <BeliefBrief summary={beliefSummary} />}

                  {analysis && <AnalysisSummary analysis={analysis} screenedCount={screenedCount} />}

                  {progressLabel && stage === "analyzing" && (
                    <Card>
                      <div style={{ color: "#e36438", fontSize: 12, textTransform: "uppercase", letterSpacing: "0.15em", fontFamily: "var(--font-mono), monospace", marginBottom: 10 }}>
                        Building Basket
                      </div>
                      <div style={{ color: "#ede9e3", fontSize: 20, fontWeight: 600, marginBottom: 8 }}>{progressLabel}</div>
                      <div style={{ color: "#8f877e", fontSize: 14 }}>Prism is mapping the theme, screening markets, and allocating a $100 basket.</div>
                    </Card>
                  )}

                  {basket && <BasketView basket={basket} basketId={basketId} />}

                  {error && (
                    <Card>
                      <div style={{ color: "#ff8f74", fontWeight: 600, marginBottom: 6 }}>Build failed</div>
                      <div style={{ color: "#d8d0c8" }}>{error}</div>
                    </Card>
                  )}
                </div>
              )}
            </div>

            <div style={{ display: "grid", gap: 18, alignSelf: "start", position: "sticky", top: 84 }}>
              <Card>
                <div style={{ color: "#e36438", fontSize: 11, textTransform: "uppercase", letterSpacing: "0.16em", fontFamily: "var(--font-mono), monospace", marginBottom: 10 }}>
                  How It Works
                </div>
                <div style={{ color: "#ede9e3", fontSize: 18, fontWeight: 600, marginBottom: 10 }}>From belief to basket</div>
                <ul style={{ margin: 0, paddingLeft: 18, color: "#9c948c", lineHeight: 1.7, fontSize: 14 }}>
                  <li>Clarify the future theme.</li>
                  <li>Map direct and indirect implications.</li>
                  <li>Screen prediction markets.</li>
                  <li>Build a weighted $100 ETF.</li>
                </ul>
              </Card>

              <Card>
                <div style={{ color: "#e36438", fontSize: 11, textTransform: "uppercase", letterSpacing: "0.16em", fontFamily: "var(--font-mono), monospace", marginBottom: 10 }}>
                  Saved ETFs
                </div>
                <div style={{ display: "grid", gap: 10 }}>
                  {savedBaskets.slice(0, 8).map((saved) => (
                    <Link
                      key={saved.id}
                      href={`/trading?basket=${saved.id}`}
                      style={{
                        display: "block",
                        textDecoration: "none",
                        border: "1px solid rgba(255,255,255,0.08)",
                        borderRadius: 14,
                        padding: 14,
                        background: "rgba(255,255,255,0.02)",
                      }}
                    >
                      <div style={{ color: "#ede9e3", fontWeight: 600, marginBottom: 6 }}>{saved.title}</div>
                      <div style={{ color: "#938b83", fontSize: 13, lineHeight: 1.5 }}>{saved.summary}</div>
                    </Link>
                  ))}
                  {!savedBaskets.length && <div style={{ color: "#7d756d", fontSize: 13 }}>No saved baskets yet.</div>}
                </div>
              </Card>
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}

function IdleComposer({
  mode, setMode, input, setInput, stepLabel, onSubmit,
}: {
  mode: Mode;
  setMode: (mode: Mode) => void;
  input: string;
  setInput: (value: string) => void;
  stepLabel: string;
  onSubmit: () => void;
}) {
  return (
    <div style={{ display: "grid", gap: 18 }}>
      <div>
        <div style={{ color: "#e36438", fontSize: 11, textTransform: "uppercase", letterSpacing: "0.16em", fontFamily: "var(--font-mono), monospace", marginBottom: 12 }}>
          Prediction Market ETFs
        </div>
        <h1 style={{ color: "#ede9e3", fontSize: "clamp(34px, 5vw, 58px)", lineHeight: 1.02, letterSpacing: "-0.05em", margin: "0 0 12px" }}>
          Turn a future theme into a weighted basket of prediction markets.
        </h1>
        <p style={{ color: "#948c84", fontSize: 18, lineHeight: 1.6, margin: 0, maxWidth: 700 }}>
          Describe a belief about the future. Prism will clarify it, map the implications, find tradable contracts, and build a shareable $100 thematic ETF.
        </p>
      </div>
      <Card>
        <div style={{ display: "flex", gap: 10, marginBottom: 18 }}>
          {(["instant", "thinking"] as Mode[]).map((value) => (
            <button
              key={value}
              onClick={() => setMode(value)}
              style={{
                ...ghostButtonStyle,
                borderColor: mode === value ? "rgba(227,100,56,0.6)" : "rgba(255,255,255,0.08)",
                color: mode === value ? "#ede9e3" : "#8d857d",
                background: mode === value ? "rgba(227,100,56,0.12)" : "transparent",
              }}
            >
              {value === "instant" ? "Instant" : "Thinking"}
            </button>
          ))}
        </div>
        <div style={{ color: "#9e968f", fontSize: 13, marginBottom: 12 }}>
          {mode === "instant" ? "Fastest path to a tradable basket." : "More clarification before Prism allocates the basket."} {stepLabel}.
        </div>
        <textarea
          value={input}
          onChange={(e) => setInput(e.target.value)}
          rows={6}
          placeholder="Example: I think renewed US-China export controls will reshape the AI hardware supply chain over the next 12 months."
          style={textareaStyle}
        />
        <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginTop: 14 }}>
          <div style={{ color: "#7f776f", fontSize: 13 }}>
            Output: a weighted basket with direct exposure, indirect implications, and optional hedge positions.
          </div>
          <button onClick={onSubmit} style={primaryButtonStyle}>Build basket</button>
        </div>
      </Card>
    </div>
  );
}

function ChatThread({ messages }: { messages: ChatMsg[] }) {
  return (
    <div style={{ display: "grid", gap: 12 }}>
      {messages.map((message, index) => (
        <div
          key={index}
          style={{
            padding: "14px 16px",
            borderRadius: 16,
            background: message.role === "user" ? "rgba(227,100,56,0.12)" : "rgba(255,255,255,0.03)",
            border: message.role === "user" ? "1px solid rgba(227,100,56,0.26)" : "1px solid rgba(255,255,255,0.06)",
            color: "#ede9e3",
          }}
        >
          <div style={{ color: message.role === "user" ? "#e36438" : "#8b837c", fontSize: 11, textTransform: "uppercase", letterSpacing: "0.16em", fontFamily: "var(--font-mono), monospace", marginBottom: 8 }}>
            {message.role === "user" ? "You" : "Prism"}
          </div>
          <div style={{ lineHeight: 1.65 }}>{message.content}</div>
        </div>
      ))}
    </div>
  );
}

function BeliefBrief({ summary }: { summary: BeliefSummary }) {
  return (
    <Card>
      <div style={{ color: "#e36438", fontSize: 11, textTransform: "uppercase", letterSpacing: "0.16em", fontFamily: "var(--font-mono), monospace", marginBottom: 10 }}>
        Basket Thesis
      </div>
      <div style={{ color: "#ede9e3", fontSize: 24, fontWeight: 600, letterSpacing: "-0.03em", marginBottom: 8 }}>
        {summary.core_belief}
      </div>
      <div style={{ color: "#9c948b", fontSize: 14, lineHeight: 1.7 }}>
        <strong style={{ color: "#d8d0c8" }}>Resolution target:</strong> {summary.resolution_target || "Not specified"}<br />
        <strong style={{ color: "#d8d0c8" }}>Time horizon:</strong> {summary.timeframe_start || "now"} → {summary.timeframe_end || summary.time_horizon}<br />
        <strong style={{ color: "#d8d0c8" }}>Mechanism:</strong> {summary.mechanism || "Not specified"}
      </div>
    </Card>
  );
}

function AnalysisSummary({ analysis, screenedCount }: { analysis: BeliefAnalysis; screenedCount: number }) {
  const topDomains = analysis.affected_domains.filter((d) => d.relevance !== "low").slice(0, 6);
  return (
    <Card>
      <div style={{ color: "#e36438", fontSize: 11, textTransform: "uppercase", letterSpacing: "0.16em", fontFamily: "var(--font-mono), monospace", marginBottom: 10 }}>
        Exposure Map
      </div>
      <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(220px, 1fr))", gap: 12 }}>
        {topDomains.map((domain) => (
          <div key={domain.domain} style={{ border: "1px solid rgba(255,255,255,0.07)", borderRadius: 14, padding: 14, background: "rgba(255,255,255,0.02)" }}>
            <div style={{ color: "#ede9e3", fontWeight: 600, marginBottom: 8 }}>{domain.domain}</div>
            <div style={{ color: "#928981", fontSize: 13, lineHeight: 1.55 }}>{domain.mechanism}</div>
          </div>
        ))}
      </div>
      {!!screenedCount && (
        <div style={{ color: "#938b83", fontSize: 13, marginTop: 14 }}>
          {screenedCount} relevant events screened from the Kalshi catalog.
        </div>
      )}
    </Card>
  );
}

function BasketView({ basket, basketId }: { basket: PredictionBasket; basketId: number | null }) {
  return (
    <Card>
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "flex-start", gap: 16, marginBottom: 18 }}>
        <div>
          <div style={{ color: "#e36438", fontSize: 11, textTransform: "uppercase", letterSpacing: "0.16em", fontFamily: "var(--font-mono), monospace", marginBottom: 10 }}>
            Prediction Market ETF
          </div>
          <div style={{ color: "#ede9e3", fontSize: 30, fontWeight: 600, letterSpacing: "-0.04em", marginBottom: 8 }}>
            {basket.basket_title}
          </div>
          <div style={{ color: "#958d86", fontSize: 15, lineHeight: 1.6, maxWidth: 700 }}>
            {basket.basket_summary}
          </div>
        </div>
        <div style={{ minWidth: 150, textAlign: "right" }}>
          <div style={{ color: "#8b837b", fontSize: 12, marginBottom: 4 }}>Total notional</div>
          <div style={{ color: "#ede9e3", fontSize: 34, fontWeight: 600 }}>${basket.total_notional.toFixed(0)}</div>
          {basketId && (
            <Link href={`/baskets/${basketId}`} style={{ color: "#e36438", fontSize: 13, textDecoration: "none" }}>
              Open share page
            </Link>
          )}
        </div>
      </div>

      <div style={{ display: "grid", gap: 10 }}>
        {basket.holdings.map((holding) => (
          <div key={holding.ticker} style={{ border: "1px solid rgba(255,255,255,0.08)", borderRadius: 16, padding: 16, background: "rgba(255,255,255,0.02)" }}>
            <div style={{ display: "grid", gridTemplateColumns: "minmax(0, 1fr) 120px", gap: 16, alignItems: "start" }}>
              <div>
                <div style={{ color: "#ede9e3", fontSize: 17, fontWeight: 600, marginBottom: 6 }}>{holding.question}</div>
                <div style={{ display: "flex", gap: 8, flexWrap: "wrap", marginBottom: 10 }}>
                  <Tag>{holding.side}</Tag>
                  <Tag>{holding.role}</Tag>
                  <Tag>{Math.round(holding.market_price * 100)}% market odds</Tag>
                </div>
                <div style={{ color: "#9b938c", fontSize: 14, lineHeight: 1.6, marginBottom: 6 }}>{holding.rationale}</div>
                <div style={{ color: "#7f776f", fontSize: 13, lineHeight: 1.5 }}>
                  Risk: {holding.main_risk}
                </div>
              </div>
              <div style={{ textAlign: "right" }}>
                <div style={{ color: "#8f877f", fontSize: 12, marginBottom: 6 }}>Weight</div>
                <div style={{ color: "#ede9e3", fontSize: 28, fontWeight: 600 }}>${holding.weight_dollars.toFixed(0)}</div>
              </div>
            </div>
          </div>
        ))}
      </div>

      <div style={{ marginTop: 18, color: "#8f877f", fontSize: 14, lineHeight: 1.6 }}>
        {basket.construction_notes}
      </div>
    </Card>
  );
}

function Card({ children }: { children: React.ReactNode }) {
  return (
    <div style={{
      background: "linear-gradient(180deg, rgba(18,18,18,0.97), rgba(12,12,12,0.98))",
      border: "1px solid rgba(255,255,255,0.08)",
      borderRadius: 22,
      padding: 22,
      boxShadow: "0 18px 48px rgba(0,0,0,0.35)",
    }}>
      {children}
    </div>
  );
}

function Tag({ children }: { children: React.ReactNode }) {
  return (
    <span style={{
      display: "inline-flex",
      alignItems: "center",
      padding: "5px 9px",
      borderRadius: 999,
      border: "1px solid rgba(255,255,255,0.08)",
      color: "#c9c0b7",
      fontSize: 12,
      background: "rgba(255,255,255,0.03)",
    }}>
      {children}
    </span>
  );
}

const textareaStyle: React.CSSProperties = {
  width: "100%",
  background: "rgba(255,255,255,0.03)",
  border: "1px solid rgba(255,255,255,0.09)",
  borderRadius: 16,
  padding: "16px 18px",
  color: "#ede9e3",
  fontSize: 16,
  lineHeight: 1.6,
  resize: "vertical",
  minHeight: 140,
  outline: "none",
};

const primaryButtonStyle: React.CSSProperties = {
  background: "#e36438",
  color: "#fff",
  border: "none",
  borderRadius: 12,
  padding: "12px 18px",
  fontWeight: 600,
  cursor: "pointer",
};

const ghostButtonStyle: React.CSSProperties = {
  background: "transparent",
  color: "#8d857d",
  border: "1px solid rgba(255,255,255,0.08)",
  borderRadius: 12,
  padding: "10px 14px",
  cursor: "pointer",
};
