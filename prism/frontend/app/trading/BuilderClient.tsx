"use client";

import { useEffect, useMemo, useRef, useState } from "react";
import Link from "next/link";
import { useRouter, useSearchParams } from "next/navigation";
import GridOverlay from "@/components/GridOverlay";
import Header from "@/components/Header";
import { getBasket, getMarkets, listBaskets, listEventCategories, saveManualBasket, searchEvents, streamTradingAnalysis, tradingChat } from "@/lib/api";
import { addMarketToManualBasketDraft, clearManualBasketDraft, loadManualBasketDraft, saveManualBasketDraft } from "@/lib/manualBasketDraft";
import type { BeliefAnalysis, BeliefSummary, KalshiEvent, KalshiMarket, ManualBasketDraftHolding, PredictionBasket, SavedBasket } from "@/lib/types";

type Mode = "instant" | "thinking";
type BuildPath = "ai" | "manual";
type Stage = "idle" | "chatting" | "analyzing" | "done" | "error";

interface ChatMsg {
  role: "user" | "assistant";
  content: string;
}

interface ManualEventModalState {
  event: KalshiEvent;
  mode: "details" | "add";
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
  const [eventCategory, setEventCategory] = useState("");
  const [eventCategories, setEventCategories] = useState<string[]>([]);
  const [eventPage, setEventPage] = useState(1);
  const [eventResults, setEventResults] = useState<KalshiEvent[]>([]);
  const [eventMarkets, setEventMarkets] = useState<KalshiMarket[]>([]);
  const [manualTitle, setManualTitle] = useState("");
  const [manualSummary, setManualSummary] = useState("");
  const [manualTimeframe, setManualTimeframe] = useState("");
  const [manualHoldings, setManualHoldings] = useState<ManualBasketDraftHolding[]>([]);
  const [saveModalOpen, setSaveModalOpen] = useState(false);
  const [manualEventModal, setManualEventModal] = useState<ManualEventModalState | null>(null);
  const [manualEventModalMarkets, setManualEventModalMarkets] = useState<KalshiMarket[]>([]);
  const [manualEventModalLoading, setManualEventModalLoading] = useState(false);
  const [manualEventModalNotice, setManualEventModalNotice] = useState("");
  const [screenedCount, setScreenedCount] = useState(0);
  const [progressLabel, setProgressLabel] = useState("");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");
  const bootstrapped = useRef(false);

  useEffect(() => {
    listBaskets(20).then(setSavedBaskets).catch(() => {});
    if (buildPath === "manual") {
      listEventCategories().then(setEventCategories).catch(() => {});
      void runEventSearch();
    }
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [buildPath]);

  useEffect(() => {
    if (buildPath !== "manual") return;
    void runEventSearch();
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [eventCategory]);

  useEffect(() => {
    if (buildPath !== "manual") return;
    if (!eventResults.length) {
      setEventMarkets([]);
      return;
    }
    void loadVisiblePageMarkets();
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [buildPath, eventResults, eventPage]);

  useEffect(() => {
    if (buildPath !== "manual") return;
    setManualHoldings(loadManualBasketDraft());
  }, [buildPath]);

  useEffect(() => {
    if (buildPath !== "manual") return;
    saveManualBasketDraft(manualHoldings);
  }, [buildPath, manualHoldings]);

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
    setEventMarkets([]);
    setEventPage(1);
    setManualHoldings([]);
    clearManualBasketDraft();
    setManualTitle("");
    setManualSummary("");
    setManualTimeframe("");
    setSaveModalOpen(false);
    setManualEventModal(null);
    setManualEventModalMarkets([]);
    setManualEventModalLoading(false);
    setManualEventModalNotice("");
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
    const events = await searchEvents(eventQuery, 120, eventCategory);
    setEventResults(events);
    setEventPage(1);
    if (!events.length) {
      setEventMarkets([]);
      return;
    }
  }

  async function loadVisiblePageMarkets() {
    const pageSize = 12;
    const start = (eventPage - 1) * pageSize;
    const visibleEvents = eventResults.slice(start, start + pageSize);
    const marketsByEvent = await Promise.all(visibleEvents.map(async (event) => ({
      event,
      markets: await getMarkets(event.event_ticker),
    })));
    setEventMarkets(
      marketsByEvent.flatMap(({ event, markets }) =>
        markets.map((market) => ({
          ...market,
          event_title: event.title,
          category: event.category,
        }))
      )
    );
  }

  async function openManualEventModal(event: KalshiEvent, mode: "details" | "add", seedMarkets: KalshiMarket[] = []) {
    setManualEventModal({ event, mode });
    setManualEventModalNotice("");
    if (seedMarkets.length) {
      setManualEventModalMarkets(seedMarkets);
      return;
    }
    setManualEventModalLoading(true);
    try {
      const markets = await getMarkets(event.event_ticker);
      setManualEventModalMarkets(
        markets.map((market) => ({
          ...market,
          event_title: event.title,
          category: event.category,
        }))
      );
    } catch (err) {
      setManualEventModalMarkets([]);
      setManualEventModalNotice(err instanceof Error ? err.message : "Could not load markets.");
    } finally {
      setManualEventModalLoading(false);
    }
  }

  function addSelectionToManualBasket(
    market: KalshiMarket,
    selection: { side: "YES" | "NO"; label?: string; price?: number; contractLabel?: string },
  ) {
    addMarketToManualBasketDraft(market, {
      side: selection.side,
      question: selection.label ?? market.question,
      marketPrice: selection.price,
      contractLabel: selection.contractLabel,
      eventTitle: market.event_title,
    });
    setManualHoldings(loadManualBasketDraft());
    setManualEventModal(null);
    setManualEventModalMarkets([]);
    setManualEventModalLoading(false);
    setManualEventModalNotice("");
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
      return;
    }
    const totalPercent = manualHoldings.reduce((sum, holding) => sum + Math.max(0, holding.weight_percent || 0), 0);
    if (totalPercent <= 0) {
      setError("Set portfolio composition above 0% for at least one holding.");
      return;
    }
    setLoading(true);
    setError("");
    try {
      const result = await saveManualBasket({
        title: manualTitle.trim(),
        summary: manualSummary.trim() || manualTitle.trim(),
        timeframe: manualTimeframe.trim(),
        holdings: manualHoldings.map((holding) => ({
          ...holding,
          weight_dollars: Number((((holding.weight_percent || 0) / totalPercent) * 100).toFixed(2)),
          role: "direct",
        })),
      });
      setBasket(JSON.parse(result.basket.basket_json));
      setBeliefSummary(JSON.parse(result.basket.belief_summary_json));
      setAnalysis(JSON.parse(result.basket.analysis_json));
      setBasketId(result.basket_id);
      setStage("done");
      clearManualBasketDraft();
      setManualHoldings([]);
      setSaveModalOpen(false);
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
        <div style={{ maxWidth: buildPath === "manual" ? 1560 : 1040, margin: "0 auto", padding: buildPath === "manual" ? "24px 20px 72px" : "40px 24px 80px" }}>
          <div style={{ display: "grid", gridTemplateColumns: buildPath === "manual" ? "minmax(0, 1fr) 420px" : "minmax(0, 1fr) 320px", gap: buildPath === "manual" ? 20 : 24, alignItems: "start" }}>
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
                    eventCategory={eventCategory}
                    setEventCategory={setEventCategory}
                    eventCategories={eventCategories}
                    eventPage={eventPage}
                    setEventPage={setEventPage}
                    eventResults={eventResults}
                    eventMarkets={eventMarkets}
                    onEventSearch={runEventSearch}
                    onOpenEvent={(event, mode, markets) => void openManualEventModal(event, mode, markets)}
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
              {buildPath === "manual" && stage === "idle" ? (
                <ManualBasketSidebar
                  manualHoldings={manualHoldings}
                  onUpdateHolding={updateManualHolding}
                  onRemoveHolding={removeManualHolding}
                  onOpenSaveModal={() => {
                    if (!manualHoldings.length) {
                      setError("Add at least one holding before saving.");
                      return;
                    }
                    setSaveModalOpen(true);
                  }}
                  loading={loading}
                />
              ) : (
                <HowItWorksSidebar buildPath={buildPath} savedBaskets={savedBaskets} />
              )}
            </div>
          </div>
        </div>
      </div>
      {buildPath === "manual" && saveModalOpen && stage === "idle" && (
        <SaveManualBasketModal
          manualTitle={manualTitle}
          setManualTitle={setManualTitle}
          manualSummary={manualSummary}
          setManualSummary={setManualSummary}
          manualTimeframe={manualTimeframe}
          setManualTimeframe={setManualTimeframe}
          loading={loading}
          onClose={() => setSaveModalOpen(false)}
          onSave={saveManual}
        />
      )}
      {buildPath === "manual" && manualEventModal && stage === "idle" && (
        <ManualEventModal
          event={manualEventModal.event}
          markets={manualEventModalMarkets}
          mode={manualEventModal.mode}
          loading={manualEventModalLoading}
          notice={manualEventModalNotice}
          onClose={() => {
            setManualEventModal(null);
            setManualEventModalMarkets([]);
            setManualEventModalLoading(false);
            setManualEventModalNotice("");
          }}
                  onAddSelection={addSelectionToManualBasket}
        />
      )}
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
  eventCategory: string;
  setEventCategory: (value: string) => void;
  eventCategories: string[];
  eventPage: number;
  setEventPage: (value: number) => void;
  eventResults: KalshiEvent[];
  eventMarkets: KalshiMarket[];
  onEventSearch: () => void;
  onOpenEvent: (event: KalshiEvent, mode: "details" | "add", markets: KalshiMarket[]) => void;
}) {
  const {
    eventQuery, setEventQuery, eventCategory, setEventCategory, eventCategories, eventPage, setEventPage, eventResults, eventMarkets,
    onEventSearch, onOpenEvent,
  } = props;
  const pageSize = 12;
  const normalizedQuery = eventQuery.trim().toLowerCase();
  const filteredEvents = eventResults.filter((event) => {
    if (eventCategory && event.category !== eventCategory) return false;
    if (!normalizedQuery) return true;
    const haystack = [event.title, event.category, event.event_ticker].filter(Boolean).join(" ").toLowerCase();
    return haystack.includes(normalizedQuery);
  });
  const browseEvents = filteredEvents;
  const totalPages = Math.max(1, Math.ceil(browseEvents.length / pageSize));
  const currentPage = Math.min(eventPage, totalPages);
  const paginatedEvents = browseEvents.slice((currentPage - 1) * pageSize, currentPage * pageSize);
  const marketsByEvent = new Map<string, KalshiMarket[]>();
  for (const market of eventMarkets) {
    const existing = marketsByEvent.get(market.event_ticker) ?? [];
    existing.push(market);
    marketsByEvent.set(market.event_ticker, existing);
  }
  return (
    <div style={{ display: "grid", gap: 20 }}>
      <div>
        <div style={{ color: "#e36438", fontSize: 11, textTransform: "uppercase", letterSpacing: "0.16em", fontFamily: "var(--font-mono), monospace", marginBottom: 12 }}>
          Basket Studio
        </div>
        <h1 style={{ color: "#ede9e3", fontSize: "clamp(28px, 3vw, 40px)", lineHeight: 1.04, letterSpacing: "-0.045em", margin: "0 0 10px" }}>
          Build a basket around your market convictions.
        </h1>
        <p style={{ color: "#9b938b", fontSize: 16, lineHeight: 1.7, margin: 0, maxWidth: 760 }}>
          Search markets, choose contracts, size your exposure, and save a themed prediction-market basket.
        </p>
      </div>

      <div style={{
        border: "1px solid rgba(255,255,255,0.07)",
        borderRadius: 24,
        padding: 20,
        background: "linear-gradient(180deg, rgba(18,18,18,0.96), rgba(11,11,11,0.98))",
        boxShadow: "0 22px 56px rgba(0,0,0,0.34)",
        display: "grid",
        gap: 16,
      }}>
        <div style={{ display: "grid", gridTemplateColumns: "minmax(0,1fr) auto", gap: 10, alignItems: "stretch" }}>
          <input
            value={eventQuery}
            onChange={(e) => setEventQuery(e.target.value)}
            onKeyDown={(e) => {
              if (e.key === "Enter") onEventSearch();
            }}
            placeholder="Search markets, themes, or events..."
            style={{ ...inputStyle, height: 54, fontSize: 15, borderRadius: 16 }}
          />
          <button onClick={onEventSearch} style={{ ...primaryButtonStyle, minWidth: 132, height: 54, borderRadius: 16 }}>Search</button>
        </div>
        <div style={{
          display: "flex",
          gap: 10,
          overflowX: "auto",
          paddingBottom: 4,
          scrollbarWidth: "thin",
        }}>
          {["All", ...eventCategories].map((chip) => {
            const isActive = chip === "All" ? !eventCategory : eventCategory === chip;
            return (
              <button
                key={chip}
                onClick={() => setEventCategory(chip === "All" ? "" : chip)}
                style={{
                  borderRadius: 999,
                  border: `1px solid ${isActive ? "rgba(227,100,56,0.42)" : "rgba(255,255,255,0.08)"}`,
                  background: isActive ? "rgba(227,100,56,0.13)" : "rgba(255,255,255,0.02)",
                  color: isActive ? "#f3e8df" : "#a79f97",
                  padding: "9px 14px",
                  fontSize: 13,
                  fontWeight: 600,
                  cursor: "pointer",
                  whiteSpace: "nowrap",
                  flexShrink: 0,
                }}
              >
                {chip}
              </button>
            );
          })}
        </div>
      </div>

      <Card>
        <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", gap: 16, marginBottom: 16 }}>
          <div style={{ color: "#ede9e3", fontSize: 20, fontWeight: 600 }}>Browse markets</div>
          <div style={{ color: "#8f877e", fontSize: 13 }}>{browseEvents.length} events</div>
        </div>
        <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(300px, 1fr))", gap: 18 }}>
          {paginatedEvents.map((event) => {
            const eventMarketList = marketsByEvent.get(event.event_ticker) ?? [];
            return (
              <div
                key={event.event_ticker}
                style={{
                  border: "1px solid rgba(255,255,255,0.08)",
                  borderRadius: 22,
                  padding: 20,
                  minHeight: 276,
                  background: "linear-gradient(180deg, rgba(255,255,255,0.035), rgba(255,255,255,0.015))",
                  boxShadow: "0 18px 42px rgba(0,0,0,0.22)",
                }}
              >
                <EventScopeCard
                  event={event}
                  markets={eventMarketList}
                  onAddToBasket={() => onOpenEvent(event, "add", eventMarketList)}
                />
              </div>
            );
          })}
        </div>
        {browseEvents.length > pageSize && (
          <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", gap: 12, marginTop: 16 }}>
            <div style={{ color: "#7f776f", fontSize: 13 }}>
              Page {currentPage} of {totalPages}
            </div>
            <div style={{ display: "flex", gap: 10 }}>
              <button
                onClick={() => setEventPage(Math.max(1, currentPage - 1))}
                disabled={currentPage === 1}
                style={{ ...ghostButtonStyle, opacity: currentPage === 1 ? 0.45 : 1, cursor: currentPage === 1 ? "default" : "pointer" }}
              >
                Previous
              </button>
              <button
                onClick={() => setEventPage(Math.min(totalPages, currentPage + 1))}
                disabled={currentPage === totalPages}
                style={{ ...ghostButtonStyle, opacity: currentPage === totalPages ? 0.45 : 1, cursor: currentPage === totalPages ? "default" : "pointer" }}
              >
                Next
              </button>
            </div>
          </div>
        )}
        {!browseEvents.length && <div style={{ color: "#7d756d", fontSize: 13 }}>No events match the current search and filters.</div>}
      </Card>
    </div>
  );
}

function EventScopeCard({
  event,
  markets,
  onAddToBasket,
}: {
  event: KalshiEvent;
  markets: KalshiMarket[];
  onAddToBasket: () => void;
}) {
  const accent = categoryAccent(event.category || "");
  const sortedMarkets = [...markets].sort((a, b) => b.mid_price - a.mid_price);
  const isBinary = sortedMarkets.length === 1;
  const shownMarkets = isBinary ? sortedMarkets.slice(0, 1) : sortedMarkets.slice(0, 3);
  const extraMarkets = Math.max(0, sortedMarkets.length - shownMarkets.length);
  const deadline = sortedMarkets[0]?.close_date || event.sub_title;
  return (
    <div style={{ display: "grid", gridTemplateRows: "auto auto 1fr auto", gap: 16, height: "100%" }}>
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "start", gap: 10 }}>
        <div style={{
          fontFamily: "var(--font-mono), monospace",
          fontSize: 10,
          fontWeight: 700,
          textTransform: "uppercase",
          letterSpacing: "0.14em",
          color: accent,
          border: `1px solid ${accent}33`,
          borderRadius: 999,
          padding: "4px 8px",
          width: "fit-content",
        }}>
          {event.category || "Event"}
        </div>
        <div style={{ color: "#8f877e", fontSize: 12, textAlign: "right", lineHeight: 1.4 }}>
          {deadline ? `Closes ${deadline}` : event.event_ticker}
        </div>
      </div>

      <div style={{ color: "#ede9e3", fontWeight: 600, lineHeight: 1.35, fontSize: 18, letterSpacing: "-0.02em" }}>
        {event.title}
      </div>

      <div style={{
        border: "1px solid rgba(255,255,255,0.05)",
        borderRadius: 16,
        padding: 14,
        background: "rgba(8,8,8,0.26)",
        display: "grid",
        alignContent: "start",
        gap: 10,
      }}>
        <div style={{ color: "#7f776f", fontSize: 11, textTransform: "uppercase", letterSpacing: "0.12em", fontFamily: "var(--font-mono), monospace" }}>
          Contract preview
        </div>
        {shownMarkets.length > 0 ? (
          isBinary ? (
            <>
              <EventOptionLine label="Yes" price={shownMarkets[0].mid_price} />
              <EventOptionLine label="No" price={1 - shownMarkets[0].mid_price} />
            </>
          ) : (
            <>
              {shownMarkets.map((market) => (
                <EventOptionLine key={market.ticker} label={market.yes_sub_title || market.ticker} price={market.mid_price} />
              ))}
              {extraMarkets > 0 && (
                <div style={{ fontFamily: "var(--font-mono), monospace", fontSize: 10, color: "#6f6861", marginTop: 2 }}>
                  +{extraMarkets} more options
                </div>
              )}
            </>
          )
        ) : (
          <div style={{ color: "#6f6861", fontSize: 12 }}>Open the event to inspect its markets.</div>
        )}
      </div>

      <div>
        <button
          onClick={onAddToBasket}
          disabled={!sortedMarkets.length}
          style={{
            ...primaryButtonStyle,
            width: "100%",
            padding: "13px 16px",
            opacity: sortedMarkets.length ? 1 : 0.45,
            cursor: sortedMarkets.length ? "pointer" : "default",
          }}
        >
          View contracts
        </button>
      </div>
    </div>
  );
}

function EventOptionLine({ label, price }: { label: string; price: number }) {
  return (
    <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", gap: 10 }}>
      <div style={{
        fontSize: 12,
        color: "#b8b0a8",
        lineHeight: 1.35,
        overflow: "hidden",
        textOverflow: "ellipsis",
        whiteSpace: "nowrap",
      }}>
        {label}
      </div>
      <div style={{
        fontFamily: "var(--font-mono), monospace",
        fontSize: 12,
        fontWeight: 700,
        color: priceColor(price),
        flexShrink: 0,
      }}>
        {(price * 100).toFixed(0)}%
      </div>
    </div>
  );
}

function categoryAccent(category: string): string {
  const c = category.toLowerCase();
  if (c.includes("polit") || c.includes("elect") || c.includes("govern")) return "#5b9cf6";
  if (c.includes("crypto") || c.includes("bitcoin") || c.includes("coin") || c.includes("eth")) return "#f59e0b";
  if (c.includes("sport") || c.includes("nba") || c.includes("nfl") || c.includes("mlb") || c.includes("soccer")) return "#4ade80";
  if (c.includes("econ") || c.includes("financ") || c.includes("fed") || c.includes("rate")) return "#a78bfa";
  if (c.includes("tech") || c.includes("ai") || c.includes("sci")) return "#2dd4bf";
  if (c.includes("weather") || c.includes("climate")) return "#7dd3fc";
  if (c.includes("entertain") || c.includes("award") || c.includes("oscar") || c.includes("music")) return "#f472b6";
  return "#e36438";
}

function priceColor(price: number): string {
  if (price >= 0.65) return "#4ade80";
  if (price <= 0.35) return "#f87171";
  return "#9b9790";
}

function ManualEventModal(props: {
  event: KalshiEvent;
  markets: KalshiMarket[];
  mode: "details" | "add";
  loading: boolean;
  notice: string;
  onClose: () => void;
  onAddSelection: (market: KalshiMarket, selection: { side: "YES" | "NO"; label?: string; price?: number; contractLabel?: string }) => void;
}) {
  const {
    event, markets, mode, loading, notice, onClose, onAddSelection,
  } = props;
  const sortedMarkets = [...markets].sort((a, b) => b.mid_price - a.mid_price);
  const isBinary = sortedMarkets.length === 1;
  const leadMarket = sortedMarkets[0] ?? null;
  const closeLabel = leadMarket?.close_date || event.sub_title;

  return (
    <div style={{
      position: "fixed",
      inset: 0,
      zIndex: 140,
      background: "rgba(3,3,3,0.78)",
      backdropFilter: "blur(12px)",
      WebkitBackdropFilter: "blur(12px)",
      display: "flex",
      alignItems: "center",
      justifyContent: "center",
      padding: 24,
    }} onClick={onClose}>
      <div style={{
        width: "min(100%, 1120px)",
        maxHeight: "calc(100vh - 48px)",
        overflowY: "auto",
        borderRadius: 28,
        border: "1px solid rgba(255,255,255,0.08)",
        background: "linear-gradient(180deg, rgba(18,18,18,0.98), rgba(9,9,9,0.99))",
        boxShadow: "0 36px 110px rgba(0,0,0,0.56)",
        padding: 28,
      }} onClick={(e) => e.stopPropagation()}>
        <div style={{ display: "flex", justifyContent: "space-between", gap: 16, alignItems: "start", marginBottom: 20 }}>
          <div>
            <div style={{ color: "#ede9e3", fontSize: "clamp(28px, 4vw, 40px)", fontWeight: 600, lineHeight: 1.05, letterSpacing: "-0.04em", maxWidth: 760 }}>
              {event.title}
            </div>
          </div>
          <button
            onClick={onClose}
            aria-label="Close"
            style={{
              background: "transparent",
              border: "1px solid rgba(255,255,255,0.08)",
              color: "#9b938b",
              width: 38,
              height: 38,
              borderRadius: 999,
              fontSize: 18,
              lineHeight: 1,
              cursor: "pointer",
            }}
          >
            ×
          </button>
        </div>

        <div style={{ display: "grid", gridTemplateColumns: "minmax(0,1fr) minmax(340px,0.92fr)", gap: 20, alignItems: "start" }}>
          <section style={{
            border: "1px solid rgba(255,255,255,0.08)",
            borderRadius: 22,
            padding: 22,
            background: "rgba(255,255,255,0.02)",
            display: "grid",
            gap: 18,
          }}>
            <div style={{ color: "#ede9e3", fontSize: 19, fontWeight: 600 }}>
              Event details
            </div>
            <div style={{ display: "grid", gridTemplateColumns: "repeat(2, minmax(0,1fr))", gap: 12 }}>
              <DetailRow label="Category" value={event.category || "Uncategorized"} />
              <DetailRow label="Deadline" value={closeLabel || "Not listed"} />
            </div>
            {leadMarket?.rules_primary && (
              <div style={{
                borderTop: "1px solid rgba(255,255,255,0.08)",
                paddingTop: 18,
              }}>
                <div style={{ color: "#ede9e3", fontSize: 17, fontWeight: 600, marginBottom: 10 }}>
                  Resolution rule
                </div>
                <div style={{ color: "#9b938b", fontSize: 14, lineHeight: 1.75 }}>
                  {leadMarket.rules_primary}
                </div>
              </div>
            )}
          </section>

          <section style={{
            border: "1px solid rgba(255,255,255,0.08)",
            borderRadius: 22,
            padding: 22,
            background: "rgba(255,255,255,0.02)",
          }}>
            <div style={{ color: "#ede9e3", fontSize: 21, fontWeight: 600, marginBottom: 8 }}>
              Choose contract
            </div>
            <div style={{ color: "#8f877e", fontSize: 14, lineHeight: 1.6, marginBottom: 18 }}>
              Pick the expression of this market conviction you want in your basket.
            </div>

            {loading ? (
              <div style={{ color: "#8f877e", fontSize: 14 }}>Loading options...</div>
            ) : !sortedMarkets.length ? (
              <div style={{ color: "#8f877e", fontSize: 14 }}>No markets available for this event.</div>
            ) : isBinary && leadMarket ? (
              <div style={{ display: "grid", gap: 12 }}>
                <ContractChoiceCard
                  title="Yes"
                  probability={leadMarket.mid_price}
                  actionLabel="Add to basket"
                  onChoose={() => onAddSelection(leadMarket, {
                    side: "YES",
                    label: leadMarket.question,
                    price: leadMarket.mid_price,
                    contractLabel: "Yes",
                  })}
                />
                <ContractChoiceCard
                  title="No"
                  probability={1 - leadMarket.mid_price}
                  actionLabel="Add to basket"
                  onChoose={() => onAddSelection(leadMarket, {
                    side: "NO",
                    label: leadMarket.question,
                    price: 1 - leadMarket.mid_price,
                    contractLabel: "No",
                  })}
                />
              </div>
            ) : (
              <div style={{ display: "grid", gap: 12 }}>
                {sortedMarkets.map((market) => (
                  <ContractChoiceCard
                    key={market.ticker}
                    title={market.yes_sub_title || market.question}
                    probability={market.mid_price}
                    actionLabel="Add to basket"
                    onChoose={() => onAddSelection(market, {
                      side: "YES",
                      label: market.yes_sub_title || market.question,
                      price: market.mid_price,
                      contractLabel: market.yes_sub_title || market.question,
                    })}
                  />
                ))}
              </div>
            )}
          </section>
        </div>
      </div>
    </div>
  );
}

function ContractChoiceCard({
  title,
  probability,
  actionLabel,
  onChoose,
}: {
  title: string;
  probability: number;
  actionLabel: string;
  onChoose: () => void;
}) {
  return (
    <div style={{
      border: "1px solid rgba(255,255,255,0.08)",
      borderRadius: 18,
      padding: "14px 16px",
      background: "linear-gradient(180deg, rgba(255,255,255,0.03), rgba(255,255,255,0.015))",
    }}>
      <div style={{ display: "grid", gridTemplateColumns: "minmax(0,1fr) auto auto", gap: 14, alignItems: "center" }}>
        <div>
          <div style={{ color: "#ede9e3", fontSize: 17, fontWeight: 600, lineHeight: 1.3 }}>
            {title}
          </div>
        </div>
        <div style={{ color: priceColor(probability), fontFamily: "var(--font-mono), monospace", fontSize: 18, fontWeight: 700, justifySelf: "end" }}>
          {(probability * 100).toFixed(0)}%
        </div>
        <button onClick={onChoose} style={{ ...primaryButtonStyle, padding: "10px 14px", whiteSpace: "nowrap" }}>
          {actionLabel}
        </button>
      </div>
    </div>
  );
}

function DetailRow({ label, value }: { label: string; value: string }) {
  return (
    <div>
      <div style={{ color: "#7b746d", fontSize: "11px", textTransform: "uppercase", letterSpacing: "0.12em", fontFamily: "var(--font-mono), monospace", marginBottom: "5px" }}>
        {label}
      </div>
      <div style={{ color: "#e1dbd3", fontSize: "14px", lineHeight: 1.6 }}>
        {value}
      </div>
    </div>
  );
}

function ManualBasketSidebar(props: {
  manualHoldings: ManualBasketDraftHolding[];
  onUpdateHolding: (ticker: string, patch: Partial<ManualBasketDraftHolding>) => void;
  onRemoveHolding: (ticker: string) => void;
  onOpenSaveModal: () => void;
  loading: boolean;
}) {
  const {
    manualHoldings, onUpdateHolding, onRemoveHolding, onOpenSaveModal, loading,
  } = props;
  const [holdingMarkets, setHoldingMarkets] = useState<Record<string, KalshiMarket[]>>({});

  useEffect(() => {
    const missingEventTickers = [...new Set(manualHoldings.map((holding) => holding.event_ticker))]
      .filter((eventTicker) => !holdingMarkets[eventTicker]);
    if (!missingEventTickers.length) return;

    let cancelled = false;
    void Promise.all(missingEventTickers.map(async (eventTicker) => {
      const markets = await getMarkets(eventTicker);
      return [eventTicker, markets] as const;
    }))
      .then((entries) => {
        if (cancelled) return;
        setHoldingMarkets((prev) => {
          const next = { ...prev };
          for (const [eventTicker, markets] of entries) {
            next[eventTicker] = markets;
          }
          return next;
        });
      })
      .catch(() => {});

    return () => {
      cancelled = true;
    };
  }, [manualHoldings, holdingMarkets]);

  return (
    <>
      <Card>
        <div style={{ color: "#e36438", fontSize: 11, textTransform: "uppercase", letterSpacing: "0.16em", fontFamily: "var(--font-mono), monospace", marginBottom: 10 }}>
          Basket draft
        </div>
        <div style={{ color: "#ede9e3", fontSize: 22, fontWeight: 600, marginBottom: 8 }}>
          Your basket
        </div>
        <div style={{ color: "#948c84", fontSize: 14, lineHeight: 1.6, marginBottom: 16 }}>
          Curate positions, size your exposure, and save when the basket reflects your thesis.
        </div>
      </Card>

      <Card>
        <div style={{ display: "flex", justifyContent: "space-between", alignItems: "start", gap: 12, marginBottom: 14 }}>
          <div>
            <div style={{ color: "#ede9e3", fontWeight: 600, marginBottom: 4 }}>Your Basket</div>
            <div style={{ color: "#8f877e", fontSize: 13 }}>
              {manualHoldings.length} {manualHoldings.length === 1 ? "position" : "positions"} · {manualHoldings.reduce((sum, holding) => sum + (holding.weight_percent || 0), 0).toFixed(0)}% drafted
            </div>
          </div>
        </div>
        <div style={{ display: "grid", gap: 10, maxHeight: "calc(100vh - 360px)", overflowY: "auto", paddingRight: 4 }}>
          {manualHoldings.map((holding) => (
            <ManualHoldingCard
              key={holding.event_ticker}
              holding={holding}
              onUpdate={(patch) => onUpdateHolding(holding.ticker, patch)}
              onRemove={() => onRemoveHolding(holding.ticker)}
              markets={holdingMarkets[holding.event_ticker] ?? []}
            />
          ))}
          {!manualHoldings.length && (
            <div style={{
              border: "1px dashed rgba(255,255,255,0.10)",
              borderRadius: 18,
              padding: 18,
              color: "#8c847c",
              fontSize: 14,
              lineHeight: 1.6,
              background: "rgba(255,255,255,0.015)",
            }}>
              No positions yet. Inspect a market and add a contract to start your basket.
            </div>
          )}
        </div>
        <button onClick={onOpenSaveModal} style={{ ...primaryButtonStyle, width: "100%", opacity: loading ? 0.7 : 1 }}>
          {loading ? "Saving..." : "Save basket"}
        </button>
      </Card>
    </>
  );
}

function SaveManualBasketModal(props: {
  manualTitle: string;
  setManualTitle: (value: string) => void;
  manualSummary: string;
  setManualSummary: (value: string) => void;
  manualTimeframe: string;
  setManualTimeframe: (value: string) => void;
  loading: boolean;
  onClose: () => void;
  onSave: () => void;
}) {
  const {
    manualTitle, setManualTitle, manualSummary, setManualSummary, manualTimeframe, setManualTimeframe,
    loading, onClose, onSave,
  } = props;
  return (
    <div style={{
      position: "fixed",
      inset: 0,
      zIndex: 120,
      background: "rgba(4,4,4,0.78)",
      backdropFilter: "blur(10px)",
      WebkitBackdropFilter: "blur(10px)",
      display: "flex",
      alignItems: "center",
      justifyContent: "center",
      padding: 24,
    }}>
      <div style={{
        width: "min(100%, 560px)",
        borderRadius: 24,
        border: "1px solid rgba(255,255,255,0.08)",
        background: "linear-gradient(180deg, rgba(17,17,17,0.98), rgba(10,10,10,0.99))",
        boxShadow: "0 30px 90px rgba(0,0,0,0.55)",
        padding: 24,
      }}>
        <div style={{ color: "#e36438", fontSize: 11, textTransform: "uppercase", letterSpacing: "0.16em", fontFamily: "var(--font-mono), monospace", marginBottom: 10 }}>
          Save Basket
        </div>
        <div style={{ color: "#ede9e3", fontSize: 28, fontWeight: 600, letterSpacing: "-0.04em", marginBottom: 8 }}>
          Save your basket
        </div>
        <div style={{ color: "#948c84", fontSize: 14, lineHeight: 1.6, marginBottom: 18 }}>
          Give your basket a title and capture the thesis behind it before saving.
        </div>
        <div style={{ display: "grid", gap: 10 }}>
          <input value={manualTitle} onChange={(e) => setManualTitle(e.target.value)} placeholder="Basket title" style={inputStyle} />
          <textarea value={manualSummary} onChange={(e) => setManualSummary(e.target.value)} rows={4} placeholder="What bet on the future is this basket representing?" style={{ ...textareaStyle, minHeight: 120 }} />
          <input value={manualTimeframe} onChange={(e) => setManualTimeframe(e.target.value)} placeholder="Timeframe (optional)" style={inputStyle} />
        </div>
        <div style={{ display: "flex", justifyContent: "flex-end", gap: 10, marginTop: 18 }}>
          <button onClick={onClose} style={ghostButtonStyle}>Cancel</button>
          <button onClick={onSave} style={{ ...primaryButtonStyle, opacity: loading ? 0.7 : 1 }}>
            {loading ? "Saving..." : "Save basket"}
          </button>
        </div>
      </div>
    </div>
  );
}

function HowItWorksSidebar({ buildPath, savedBaskets }: { buildPath: BuildPath; savedBaskets: SavedBasket[] }) {
  return (
    <>
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
              <li>Choose contracts and portfolio weights.</li>
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
    </>
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
    <div style={{ border: "1px solid rgba(255,255,255,0.08)", borderRadius: 18, padding: 16, background: "linear-gradient(180deg, rgba(255,255,255,0.03), rgba(255,255,255,0.015))" }}>
      <div style={{ display: "grid", gridTemplateColumns: "minmax(0,1fr) auto", gap: 16, alignItems: "start" }}>
        <div>
          <div style={{ color: "#7f776f", fontSize: 11, textTransform: "uppercase", letterSpacing: "0.14em", fontFamily: "var(--font-mono), monospace", marginBottom: 8 }}>
            {market.category || "Market"}{market.event_title ? ` · ${market.event_title}` : ""}
          </div>
          <div style={{ color: "#ede9e3", fontWeight: 600, marginBottom: 8, lineHeight: 1.45, fontSize: 16 }}>{market.question}</div>
          <div style={{ display: "flex", gap: 8, flexWrap: "wrap", marginBottom: 10 }}>
            <Tag>{Math.round(market.mid_price * 100)}% market odds</Tag>
            <Tag>{market.close_date}</Tag>
            <Tag>${Math.round(market.volume).toLocaleString()} vol</Tag>
          </div>
          {market.rules_primary && (
            <div style={{ color: "#8c847c", fontSize: 13, lineHeight: 1.55 }}>
              {market.rules_primary.length > 180 ? `${market.rules_primary.slice(0, 180)}...` : market.rules_primary}
            </div>
          )}
        </div>
        <div style={{ display: "grid", justifyItems: "end", gap: 10, minWidth: 132 }}>
          <div style={{ color: "#9f978f", fontSize: 12 }}>Ticker {market.ticker}</div>
          <button onClick={onAdd} style={{ ...ghostButtonStyle, minWidth: 132 }}>Add to basket</button>
        </div>
      </div>
    </div>
  );
}

function ManualHoldingCard({ holding, onUpdate, onRemove, markets }: {
  holding: ManualBasketDraftHolding;
  onUpdate: (patch: Partial<ManualBasketDraftHolding>) => void;
  onRemove: () => void;
  markets: KalshiMarket[];
}) {
  const sortedMarkets = [...markets].sort((a, b) => b.mid_price - a.mid_price);
  const isBinary = sortedMarkets.length === 1;
  const optionChoices = isBinary && sortedMarkets[0]
    ? [
      {
        value: `${sortedMarkets[0].ticker}:YES`,
        label: "Yes",
        patch: {
          ticker: sortedMarkets[0].ticker,
          side: "YES" as const,
          contract_label: "Yes",
          question: sortedMarkets[0].question,
          market_price: sortedMarkets[0].mid_price,
        },
      },
      {
        value: `${sortedMarkets[0].ticker}:NO`,
        label: "No",
        patch: {
          ticker: sortedMarkets[0].ticker,
          side: "NO" as const,
          contract_label: "No",
          question: sortedMarkets[0].question,
          market_price: 1 - sortedMarkets[0].mid_price,
        },
      },
    ]
    : sortedMarkets.map((market) => ({
      value: `${market.ticker}:YES`,
      label: market.yes_sub_title || market.question,
      patch: {
        ticker: market.ticker,
        side: "YES" as const,
        contract_label: market.yes_sub_title || market.question,
        question: market.yes_sub_title || market.question,
        market_price: market.mid_price,
      },
    }));
  const selectedChoice = `${holding.ticker}:${holding.side}`;

  return (
    <div style={{ border: "1px solid rgba(255,255,255,0.08)", borderRadius: 16, padding: 14, background: "linear-gradient(180deg, rgba(255,255,255,0.03), rgba(255,255,255,0.015))" }}>
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "start", gap: 12, marginBottom: 10 }}>
        <div>
          <div style={{ color: "#ede9e3", fontWeight: 600, lineHeight: 1.45, marginBottom: 4 }}>{holding.event_title || holding.question}</div>
          <div style={{ color: "#8f877e", fontSize: 13 }}>
            Current price {Math.round(holding.market_price * 100)}%
          </div>
        </div>
        <button
          onClick={onRemove}
          aria-label="Remove holding"
          style={{
            background: "transparent",
            border: "none",
            color: "#8f877e",
            fontSize: 18,
            lineHeight: 1,
            cursor: "pointer",
            padding: 0,
            flexShrink: 0,
          }}
        >
          ×
        </button>
      </div>
      <div style={{ display: "grid", gridTemplateColumns: "minmax(0,1.2fr) minmax(0,1fr)", gap: 8, marginBottom: 8 }}>
        <div>
          <div style={miniLabelStyle}>Contract</div>
          <select
            value={selectedChoice}
            onChange={(e) => {
              const next = optionChoices.find((choice) => choice.value === e.target.value);
              if (!next) return;
              onUpdate(next.patch);
            }}
            style={inputStyle}
          >
            {optionChoices.map((choice) => (
              <option key={choice.value} value={choice.value}>{choice.label}</option>
            ))}
          </select>
        </div>
        <div>
          <div style={miniLabelStyle}>% of basket</div>
          <input
            value={holding.weight_percent}
            type="number"
            min={1}
            onChange={(e) => onUpdate({ weight_percent: Number(e.target.value) })}
            style={inputStyle}
          />
        </div>
      </div>
      <input
        value={holding.rationale}
        onChange={(e) => onUpdate({ rationale: e.target.value, main_risk: "" })}
        placeholder="Notes (optional)"
        style={inputStyle}
      />
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

const miniLabelStyle: React.CSSProperties = {
  color: "#7b746d",
  fontSize: 11,
  textTransform: "uppercase",
  letterSpacing: "0.12em",
  fontFamily: "var(--font-mono), monospace",
  marginBottom: 6,
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
