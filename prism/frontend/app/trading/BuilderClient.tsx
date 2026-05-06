"use client";

import { useEffect, useMemo, useRef, useState } from "react";
import Link from "next/link";
import { useRouter, useSearchParams } from "next/navigation";
import GridOverlay from "@/components/GridOverlay";
import Header from "@/components/Header";
import { getBasket, getMarkets, listBaskets, saveManualBasket, searchEvents, streamTradingAnalysis, tradingChat } from "@/lib/api";
import type { BeliefAnalysis, BeliefSummary, KalshiEvent, KalshiMarket, ManualBasketDraftHolding, PredictionBasket, SavedBasket } from "@/lib/types";

type Mode = "instant" | "thinking";
type BuildPath = "ai" | "manual";
type Stage = "idle" | "chatting" | "analyzing" | "done" | "error";

interface ChatMsg {
  role: "user" | "assistant";
  content: string;
}

export default function BuilderClient({ buildPath }: { buildPath: BuildPath }) {
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
  const [eventQuery, setEventQuery] = useState("");
  const [eventResults, setEventResults] = useState<KalshiEvent[]>([]);
  const [selectedEvent, setSelectedEvent] = useState<KalshiEvent | null>(null);
  const [eventMarkets, setEventMarkets] = useState<KalshiMarket[]>([]);
  const [manualTitle, setManualTitle] = useState("");
  const [manualSummary, setManualSummary] = useState("");
  const [manualTimeframe, setManualTimeframe] = useState("");
  const [manualHoldings, setManualHoldings] = useState<ManualBasketDraftHolding[]>([]);
  const [screenedCount, setScreenedCount] = useState(0);
  const [progressLabel, setProgressLabel] = useState("");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");
  const bootstrapped = useRef(false);

  useEffect(() => {
    listBaskets(20).then(setSavedBaskets).catch(() => {});
    if (buildPath === "manual") {
      searchEvents("", 12).then(setEventResults).catch(() => {});
    }
  }, [buildPath]);

  useEffect(() => {
    if (!basketId) return;
    getBasket(basketId).then((saved) => {
      setBeliefSummary(JSON.parse(saved.belief_summary_json));
      setAnalysis(JSON.parse(saved.analysis_json));
      setBasket(JSON.parse(saved.basket_json));
      setMode(saved.mode === "manual" ? "thinking" : saved.mode);
      setStage("done");
    }).catch(() => {});
  }, [basketId]);

  useEffect(() => {
    if (buildPath !== "ai") return;
    if (!initialBelief.trim() || bootstrapped.current) return;
    bootstrapped.current = true;
    setStage("chatting");
    void sendMessage(initialBelief, []);
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [initialBelief, buildPath]);

  const stepLabel = useMemo(() => (
    mode === "instant" ? "1 follow-up max" : "up to 3 follow-ups"
  ), [mode]);

  const routeBase = buildPath === "manual" ? "/trading/manual" : "/trading";

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
    setSelectedEvent(null);
    setEventMarkets([]);
    setManualHoldings([]);
    setManualTitle("");
    setManualSummary("");
    setManualTimeframe("");
    setProgressLabel("");
    setError("");
    router.replace(routeBase, { scroll: false });
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
        if (msg.basket_id) router.replace(`${routeBase}?basket=${msg.basket_id}`, { scroll: false });
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

  async function runEventSearch() {
    setEventResults(await searchEvents(eventQuery, 24));
  }

  async function pickEvent(event: KalshiEvent) {
    setSelectedEvent(event);
    setEventMarkets(await getMarkets(event.event_ticker));
  }

  function addManualHolding(market: KalshiMarket) {
    setManualHoldings((prev) => {
      if (prev.some((holding) => holding.ticker === market.ticker)) return prev;
      return [...prev, {
        ticker: market.ticker,
        event_ticker: market.event_ticker,
        question: market.question,
        market_price: market.mid_price,
        close_date: market.close_date,
        side: "YES",
        role: "direct",
        weight_dollars: 10,
        rationale: "",
        main_risk: "",
        rules_summary: market.rules_primary,
      }];
    });
  }

  function updateManualHolding(ticker: string, patch: Partial<ManualBasketDraftHolding>) {
    setManualHoldings((prev) => prev.map((holding) => holding.ticker === ticker ? { ...holding, ...patch } : holding));
  }

  function removeManualHolding(ticker: string) {
    setManualHoldings((prev) => prev.filter((holding) => holding.ticker !== ticker));
  }

  async function saveManual() {
    if (!manualTitle.trim() || !manualHoldings.length) {
      setError("Add a basket title and at least one holding.");
      setStage("error");
      return;
    }
    setLoading(true);
    setError("");
    try {
      const result = await saveManualBasket({
        title: manualTitle.trim(),
        summary: manualSummary.trim() || manualTitle.trim(),
        timeframe: manualTimeframe.trim(),
        holdings: manualHoldings,
      });
      setBasket(JSON.parse(result.basket.basket_json));
      setBeliefSummary(JSON.parse(result.basket.belief_summary_json));
      setAnalysis(JSON.parse(result.basket.analysis_json));
      setBasketId(result.basket_id);
      setStage("done");
      router.replace(`${routeBase}?basket=${result.basket_id}`, { scroll: false });
      listBaskets(20).then(setSavedBaskets).catch(() => {});
    } catch (err) {
      setError(err instanceof Error ? err.message : "Could not save basket");
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
                buildPath === "ai" ? (
                  <AIBuildComposer
                    mode={mode}
                    setMode={setMode}
                    input={input}
                    setInput={setInput}
                    stepLabel={stepLabel}
                    onSubmit={onSubmitInitial}
                  />
                ) : (
                  <ManualBuildComposer
                    eventQuery={eventQuery}
                    setEventQuery={setEventQuery}
                    eventResults={eventResults}
                    selectedEvent={selectedEvent}
                    eventMarkets={eventMarkets}
                    manualTitle={manualTitle}
                    setManualTitle={setManualTitle}
                    manualSummary={manualSummary}
                    setManualSummary={setManualSummary}
                    manualTimeframe={manualTimeframe}
                    setManualTimeframe={setManualTimeframe}
                    manualHoldings={manualHoldings}
                    onEventSearch={runEventSearch}
                    onPickEvent={pickEvent}
                    onAddHolding={addManualHolding}
                    onUpdateHolding={updateManualHolding}
                    onRemoveHolding={removeManualHolding}
                    onSaveManual={saveManual}
                  />
                )
              )}

              {stage !== "idle" && (
                <div style={{ display: "grid", gap: 18 }}>
                  <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center" }}>
                    <div>
                      <div style={{ color: "#e36438", fontSize: 11, textTransform: "uppercase", letterSpacing: "0.16em", fontFamily: "var(--font-mono), monospace" }}>
                        Prediction Market ETF Builder
                      </div>
                      <div style={{ color: "#ede9e3", fontSize: 28, fontWeight: 600, letterSpacing: "-0.03em" }}>
                        {buildPath === "ai" ? "Build with AI" : "Build manually"}
                      </div>
                    </div>
                    <button onClick={resetFlow} style={ghostButtonStyle}>New basket</button>
                  </div>

                  {buildPath === "ai" && (
                    <Card>
                      <div style={{ color: "#8f877e", fontSize: 13, marginBottom: 10 }}>
                        Mode: <span style={{ color: "#ede9e3" }}>{mode === "instant" ? "Instant" : "Thinking"}</span>
                      </div>
                      <ChatThread messages={chatMessages} />
                      {stage === "chatting" && (
                        <div style={{ display: "grid", gap: 10, marginTop: 16 }}>
                          <textarea value={input} onChange={(e) => setInput(e.target.value)} rows={3} placeholder="Answer the follow-up..." style={textareaStyle} />
                          <button onClick={onSubmitReply} style={primaryButtonStyle}>Continue</button>
                        </div>
                      )}
                    </Card>
                  )}

                  {beliefSummary && <BeliefBrief summary={beliefSummary} />}
                  {analysis && <AnalysisSummary analysis={analysis} screenedCount={screenedCount} />}

                  {progressLabel && stage === "analyzing" && (
                    <Card>
                      <div style={{ color: "#e36438", fontSize: 12, textTransform: "uppercase", letterSpacing: "0.15em", fontFamily: "var(--font-mono), monospace", marginBottom: 10 }}>
                        Building Basket
                      </div>
                      <div style={{ color: "#ede9e3", fontSize: 20, fontWeight: 600, marginBottom: 8 }}>{progressLabel}</div>
                      <div style={{ color: "#8f877e", fontSize: 14 }}>
                        {buildPath === "ai" ? "Prism is mapping the theme, screening markets, and allocating a $100 basket." : "Saving your manual basket."}
                      </div>
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
                <div style={{ color: "#ede9e3", fontSize: 18, fontWeight: 600, marginBottom: 10 }}>
                  {buildPath === "ai" ? "From belief to basket" : "From market picker to basket"}
                </div>
                <ul style={{ margin: 0, paddingLeft: 18, color: "#9c948c", lineHeight: 1.7, fontSize: 14 }}>
                  {buildPath === "ai" ? (
                    <>
                      <li>Clarify the future theme.</li>
                      <li>Map direct and indirect implications.</li>
                      <li>Screen prediction markets.</li>
                      <li>Build a weighted $100 ETF.</li>
                    </>
                  ) : (
                    <>
                      <li>Search the market catalog.</li>
                      <li>Select the contracts you want.</li>
                      <li>Choose sides, roles, and weights.</li>
                      <li>Save a weighted $100 ETF.</li>
                    </>
                  )}
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
                      href={`${saved.mode === "manual" ? "/trading/manual" : "/trading"}?basket=${saved.id}`}
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

function AIBuildComposer({ mode, setMode, input, setInput, stepLabel, onSubmit }: {
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
          AI ETF Builder
        </div>
        <h1 style={{ color: "#ede9e3", fontSize: "clamp(34px, 5vw, 58px)", lineHeight: 1.02, letterSpacing: "-0.05em", margin: "0 0 12px" }}>
          Explain the future. Prism builds the basket.
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
        <textarea value={input} onChange={(e) => setInput(e.target.value)} rows={6} placeholder="Example: I think renewed US-China export controls will reshape the AI hardware supply chain over the next 12 months." style={textareaStyle} />
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

function ManualBuildComposer(props: {
  eventQuery: string;
  setEventQuery: (value: string) => void;
  eventResults: KalshiEvent[];
  selectedEvent: KalshiEvent | null;
  eventMarkets: KalshiMarket[];
  manualTitle: string;
  setManualTitle: (value: string) => void;
  manualSummary: string;
  setManualSummary: (value: string) => void;
  manualTimeframe: string;
  setManualTimeframe: (value: string) => void;
  manualHoldings: ManualBasketDraftHolding[];
  onEventSearch: () => void;
  onPickEvent: (event: KalshiEvent) => void;
  onAddHolding: (market: KalshiMarket) => void;
  onUpdateHolding: (ticker: string, patch: Partial<ManualBasketDraftHolding>) => void;
  onRemoveHolding: (ticker: string) => void;
  onSaveManual: () => void;
}) {
  const {
    eventQuery, setEventQuery, eventResults, selectedEvent, eventMarkets,
    manualTitle, setManualTitle, manualSummary, setManualSummary, manualTimeframe, setManualTimeframe,
    manualHoldings, onEventSearch, onPickEvent, onAddHolding, onUpdateHolding, onRemoveHolding, onSaveManual,
  } = props;
  return (
    <div style={{ display: "grid", gap: 18 }}>
      <div>
        <div style={{ color: "#e36438", fontSize: 11, textTransform: "uppercase", letterSpacing: "0.16em", fontFamily: "var(--font-mono), monospace", marginBottom: 12 }}>
          Manual ETF Builder
        </div>
        <h1 style={{ color: "#ede9e3", fontSize: "clamp(34px, 5vw, 58px)", lineHeight: 1.02, letterSpacing: "-0.05em", margin: "0 0 12px" }}>
          Pick the markets yourself.
        </h1>
        <p style={{ color: "#948c84", fontSize: 18, lineHeight: 1.6, margin: 0, maxWidth: 700 }}>
          Search the Kalshi catalog, select contracts, set sides and weights, and save a shareable $100 ETF.
        </p>
      </div>
      <Card>
        <div style={{ color: "#9e968f", fontSize: 13, marginBottom: 16 }}>
          Build your basket title and summary first, then add market holdings below.
        </div>
        <input value={manualTitle} onChange={(e) => setManualTitle(e.target.value)} placeholder="Basket title" style={inputStyle} />
        <textarea value={manualSummary} onChange={(e) => setManualSummary(e.target.value)} rows={3} placeholder="Basket summary" style={{ ...textareaStyle, minHeight: 100 }} />
        <input value={manualTimeframe} onChange={(e) => setManualTimeframe(e.target.value)} placeholder="Timeframe (optional)" style={inputStyle} />
      </Card>

      <Card>
        <div style={{ display: "grid", gridTemplateColumns: "minmax(0,1fr) auto", gap: 10 }}>
          <input value={eventQuery} onChange={(e) => setEventQuery(e.target.value)} placeholder="Search events or themes" style={inputStyle} />
          <button onClick={onEventSearch} style={primaryButtonStyle}>Search</button>
        </div>
      </Card>

      <div style={{ display: "grid", gridTemplateColumns: "minmax(0,1fr) minmax(0,1fr)", gap: 14 }}>
        <Card>
          <div style={{ color: "#ede9e3", fontWeight: 600, marginBottom: 12 }}>Events</div>
          <div style={{ display: "grid", gap: 10 }}>
            {eventResults.slice(0, 10).map((event) => (
              <button
                key={event.event_ticker}
                onClick={() => onPickEvent(event)}
                style={{
                  textAlign: "left",
                  background: selectedEvent?.event_ticker === event.event_ticker ? "linear-gradient(180deg, rgba(227,100,56,0.16), rgba(227,100,56,0.08))" : "rgba(255,255,255,0.02)",
                  border: "1px solid rgba(255,255,255,0.08)",
                  borderRadius: 16,
                  padding: 14,
                  color: "#ede9e3",
                  cursor: "pointer",
                }}
              >
                <div style={{ fontWeight: 600, marginBottom: 6 }}>{event.title}</div>
                <div style={{ fontSize: 12, color: "#8f877e", marginBottom: 6 }}>{event.category}</div>
                {event.sub_title && <div style={{ fontSize: 12, color: "#6f6861", lineHeight: 1.45 }}>{event.sub_title}</div>}
              </button>
            ))}
          </div>
        </Card>

        <Card>
          <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 12 }}>
            <div style={{ color: "#ede9e3", fontWeight: 600 }}>Markets</div>
            {selectedEvent && <div style={{ color: "#7f776f", fontSize: 12 }}>{selectedEvent.title}</div>}
          </div>
          <div style={{ display: "grid", gap: 10 }}>
            {eventMarkets.slice(0, 16).map((market) => (
              <ManualMarketCard key={market.ticker} market={market} onAdd={() => onAddHolding(market)} />
            ))}
            {!eventMarkets.length && <div style={{ color: "#7d756d", fontSize: 13 }}>Select an event to load contracts.</div>}
          </div>
        </Card>
      </div>

      <Card>
        <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 12 }}>
          <div style={{ color: "#ede9e3", fontWeight: 600 }}>Selected holdings</div>
          <div style={{ color: "#8f877e", fontSize: 12 }}>
            ${manualHoldings.reduce((sum, holding) => sum + (holding.weight_dollars || 0), 0).toFixed(0)} draft notional
          </div>
        </div>
        <div style={{ display: "grid", gap: 10 }}>
          {manualHoldings.map((holding) => (
            <ManualHoldingCard
              key={holding.ticker}
              holding={holding}
              onUpdate={(patch) => onUpdateHolding(holding.ticker, patch)}
              onRemove={() => onRemoveHolding(holding.ticker)}
            />
          ))}
          {!manualHoldings.length && <div style={{ color: "#7d756d", fontSize: 13 }}>No holdings yet.</div>}
        </div>
      </Card>

      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center" }}>
        <div style={{ color: "#7f776f", fontSize: 13 }}>
          Weights will be normalized to a $100 basket when you save.
        </div>
        <button onClick={onSaveManual} style={primaryButtonStyle}>Save manual basket</button>
      </div>
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

function ManualMarketCard({ market, onAdd }: { market: KalshiMarket; onAdd: () => void }) {
  return (
    <div style={{ border: "1px solid rgba(255,255,255,0.08)", borderRadius: 16, padding: 14, background: "linear-gradient(180deg, rgba(255,255,255,0.03), rgba(255,255,255,0.015))" }}>
      <div style={{ color: "#ede9e3", fontWeight: 600, marginBottom: 6, lineHeight: 1.45 }}>{market.question}</div>
      <div style={{ display: "flex", gap: 8, flexWrap: "wrap", marginBottom: 10 }}>
        <Tag>{Math.round(market.mid_price * 100)}% market odds</Tag>
        <Tag>{market.close_date}</Tag>
      </div>
      <button onClick={onAdd} style={ghostButtonStyle}>Add to basket</button>
    </div>
  );
}

function ManualHoldingCard({ holding, onUpdate, onRemove }: {
  holding: ManualBasketDraftHolding;
  onUpdate: (patch: Partial<ManualBasketDraftHolding>) => void;
  onRemove: () => void;
}) {
  return (
    <div style={{ border: "1px solid rgba(255,255,255,0.08)", borderRadius: 16, padding: 14, background: "linear-gradient(180deg, rgba(255,255,255,0.03), rgba(255,255,255,0.015))" }}>
      <div style={{ color: "#ede9e3", fontWeight: 600, marginBottom: 10, lineHeight: 1.45 }}>{holding.question}</div>
      <div style={{ display: "grid", gridTemplateColumns: "repeat(4, minmax(0,1fr)) auto", gap: 8, marginBottom: 8 }}>
        <select value={holding.side} onChange={(e) => onUpdate({ side: e.target.value as "YES" | "NO" })} style={inputStyle}>
          <option value="YES">YES</option>
          <option value="NO">NO</option>
        </select>
        <select value={holding.role} onChange={(e) => onUpdate({ role: e.target.value as ManualBasketDraftHolding["role"] })} style={inputStyle}>
          <option value="direct">direct</option>
          <option value="mechanism">mechanism</option>
          <option value="indirect">indirect</option>
          <option value="hedge">hedge</option>
        </select>
        <input value={holding.weight_dollars} type="number" min={1} onChange={(e) => onUpdate({ weight_dollars: Number(e.target.value) })} style={inputStyle} />
        <input value={`${Math.round(holding.market_price * 100)}%`} disabled style={inputStyle} />
        <button onClick={onRemove} style={ghostButtonStyle}>Remove</button>
      </div>
      <input value={holding.rationale} onChange={(e) => onUpdate({ rationale: e.target.value })} placeholder="Why this belongs in the basket" style={{ ...inputStyle, marginBottom: 8 }} />
      <input value={holding.main_risk} onChange={(e) => onUpdate({ main_risk: e.target.value })} placeholder="Main risk" style={inputStyle} />
    </div>
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

const inputStyle: React.CSSProperties = {
  width: "100%",
  background: "rgba(255,255,255,0.03)",
  border: "1px solid rgba(255,255,255,0.09)",
  borderRadius: 12,
  padding: "12px 14px",
  color: "#ede9e3",
  fontSize: 14,
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
