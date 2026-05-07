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
  const [oddsFilter, setOddsFilter] = useState<"all" | "low" | "mid" | "high">("all");
  const [eventResults, setEventResults] = useState<KalshiEvent[]>([]);
  const [eventMarkets, setEventMarkets] = useState<KalshiMarket[]>([]);
  const [manualTitle, setManualTitle] = useState("");
  const [manualSummary, setManualSummary] = useState("");
  const [manualTimeframe, setManualTimeframe] = useState("");
  const [manualHoldings, setManualHoldings] = useState<ManualBasketDraftHolding[]>([]);
  const [saveModalOpen, setSaveModalOpen] = useState(false);
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
                    oddsFilter={oddsFilter}
                    setOddsFilter={setOddsFilter}
                    eventResults={eventResults}
                    eventMarkets={eventMarkets}
                    onEventSearch={runEventSearch}
                    onAddMarket={(market) => {
                      addMarketToManualBasketDraft(market);
                      setManualHoldings(loadManualBasketDraft());
                    }}
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
  oddsFilter: "all" | "low" | "mid" | "high";
  setOddsFilter: (value: "all" | "low" | "mid" | "high") => void;
  eventResults: KalshiEvent[];
  eventMarkets: KalshiMarket[];
  onEventSearch: () => void;
  onAddMarket: (market: KalshiMarket) => void;
}) {
  const router = useRouter();
  const {
    eventQuery, setEventQuery, eventCategory, setEventCategory, eventCategories, eventPage, setEventPage, oddsFilter, setOddsFilter, eventResults, eventMarkets,
    onEventSearch, onAddMarket,
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
  const visibleCardCount = paginatedEvents.length;
  const marketsByEvent = new Map<string, KalshiMarket[]>();
  for (const market of eventMarkets) {
    const existing = marketsByEvent.get(market.event_ticker) ?? [];
    existing.push(market);
    marketsByEvent.set(market.event_ticker, existing);
  }
  return (
    <div style={{ display: "grid", gap: 16 }}>
      <div>
        <div style={{ color: "#e36438", fontSize: 11, textTransform: "uppercase", letterSpacing: "0.16em", fontFamily: "var(--font-mono), monospace", marginBottom: 12 }}>
          Manual ETF Builder
        </div>
        <h1 style={{ color: "#ede9e3", fontSize: "clamp(24px, 2.6vw, 34px)", lineHeight: 1.05, letterSpacing: "-0.04em", margin: 0 }}>
          Search events and open the ones you want to inspect.
        </h1>
      </div>

      <div style={{
        border: "1px solid rgba(255,255,255,0.08)",
        borderRadius: 18,
        padding: 18,
        background: "linear-gradient(180deg, rgba(16,16,16,0.98), rgba(10,10,10,0.98))",
        boxShadow: "0 18px 48px rgba(0,0,0,0.35)",
      }}>
        <div style={{ display: "grid", gridTemplateColumns: "minmax(0,1.9fr) repeat(2, minmax(0,0.9fr)) auto", gap: 10, alignItems: "stretch" }}>
          <input
            value={eventQuery}
            onChange={(e) => setEventQuery(e.target.value)}
            onKeyDown={(e) => {
              if (e.key === "Enter") onEventSearch();
            }}
            placeholder="Search themes, events, or keywords"
            style={{ ...inputStyle, height: 50, fontSize: 15, borderRadius: 12 }}
          />
          <select value={eventCategory} onChange={(e) => setEventCategory(e.target.value)} style={{ ...inputStyle, height: 50, borderRadius: 12 }}>
            <option value="">All categories</option>
            {eventCategories.map((category) => <option key={category} value={category}>{category}</option>)}
          </select>
          <select value={oddsFilter} onChange={(e) => setOddsFilter(e.target.value as "all" | "low" | "mid" | "high")} style={{ ...inputStyle, height: 50, borderRadius: 12 }}>
            <option value="all">All odds</option>
            <option value="low">Below 33%</option>
            <option value="mid">33% to 66%</option>
            <option value="high">Above 66%</option>
          </select>
          <button onClick={onEventSearch} style={{ ...primaryButtonStyle, minWidth: 120, height: 50, borderRadius: 12 }}>Search</button>
        </div>
      </div>

      <Card>
        <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 12 }}>
          <div>
            <div style={{ color: "#ede9e3", fontWeight: 600, marginBottom: 4 }}>Event scopes</div>
            <div style={{ color: "#7f776f", fontSize: 13 }}>Browse the event universe, then open one to inspect options and add the market you want.</div>
          </div>
          <div style={{ display: "grid", justifyItems: "end", gap: 2 }}>
            <div style={{ color: "#8f877e", fontSize: 12 }}>{browseEvents.length} events</div>
            <div style={{ color: "#6f6861", fontSize: 12 }}>
              {oddsFilter === "all" ? "Option previews load per page" : `Odds filter applies to the ${visibleCardCount} visible cards`}
            </div>
          </div>
        </div>
        <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(280px, 1fr))", gap: 14 }}>
          {paginatedEvents.map((event) => {
            const eventHref = `/market/${event.event_ticker}?title=${encodeURIComponent(event.title)}&cat=${encodeURIComponent(event.category)}&sub=${encodeURIComponent(event.sub_title)}&from=manual`;
            const eventMarketList = marketsByEvent.get(event.event_ticker) ?? [];
            return (
              <div
                key={event.event_ticker}
                style={{
                  border: "1px solid rgba(255,255,255,0.08)",
                  borderRadius: 18,
                  padding: 18,
                  minHeight: 250,
                  background: "linear-gradient(180deg, rgba(255,255,255,0.03), rgba(255,255,255,0.015))",
                }}
              >
                <EventScopeCard
                  event={event}
                  markets={eventMarketList}
                  onMoreDetails={() => router.push(eventHref)}
                  onAddToBasket={() => {
                    const primaryMarket = [...eventMarketList].sort((a, b) => b.mid_price - a.mid_price)[0];
                    if (!primaryMarket) return;
                    onAddMarket(primaryMarket);
                  }}
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
  onMoreDetails,
  onAddToBasket,
}: {
  event: KalshiEvent;
  markets: KalshiMarket[];
  onMoreDetails: () => void;
  onAddToBasket: () => void;
}) {
  const accent = categoryAccent(event.category || "");
  const sortedMarkets = [...markets].sort((a, b) => b.mid_price - a.mid_price);
  const isBinary = sortedMarkets.length === 1;
  const shownMarkets = isBinary ? sortedMarkets.slice(0, 1) : sortedMarkets.slice(0, 3);
  const extraMarkets = Math.max(0, sortedMarkets.length - shownMarkets.length);
  const deadline = sortedMarkets[0]?.close_date || event.sub_title;
  return (
    <div style={{ display: "grid", gridTemplateRows: "auto auto 1fr auto", gap: 14, height: "100%" }}>
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
        border: "1px solid rgba(255,255,255,0.06)",
        borderRadius: 14,
        padding: 14,
        background: "rgba(8,8,8,0.34)",
        display: "grid",
        alignContent: "start",
        gap: 8,
      }}>
        <div style={{ color: "#7f776f", fontSize: 11, textTransform: "uppercase", letterSpacing: "0.12em", fontFamily: "var(--font-mono), monospace" }}>
          Options
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

      <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 10 }}>
        <button
          onClick={onMoreDetails}
          style={{ ...ghostButtonStyle, width: "100%", textAlign: "center" }}
        >
          More details
        </button>
        <button
          onClick={onAddToBasket}
          disabled={!sortedMarkets.length}
          style={{
            ...primaryButtonStyle,
            width: "100%",
            opacity: sortedMarkets.length ? 1 : 0.45,
            cursor: sortedMarkets.length ? "pointer" : "default",
          }}
        >
          Add to basket
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
  return (
    <>
      <Card>
        <div style={{ color: "#e36438", fontSize: 11, textTransform: "uppercase", letterSpacing: "0.16em", fontFamily: "var(--font-mono), monospace", marginBottom: 10 }}>
          Basket Builder
        </div>
        <div style={{ color: "#ede9e3", fontSize: 22, fontWeight: 600, marginBottom: 8 }}>
          Your basket
        </div>
        <div style={{ color: "#948c84", fontSize: 14, lineHeight: 1.6, marginBottom: 16 }}>
          Open events, add the contracts you want, then name and describe the basket only when you are ready to save.
        </div>
      </Card>

      <Card>
        <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 12 }}>
          <div style={{ color: "#ede9e3", fontWeight: 600 }}>Selected holdings</div>
          <div style={{ color: "#8f877e", fontSize: 12 }}>
            ${manualHoldings.reduce((sum, holding) => sum + (holding.weight_dollars || 0), 0).toFixed(0)} draft
          </div>
        </div>
        <div style={{ display: "grid", gap: 10, maxHeight: "calc(100vh - 360px)", overflowY: "auto", paddingRight: 4 }}>
          {manualHoldings.map((holding) => (
            <ManualHoldingCard
              key={holding.ticker}
              holding={holding}
              onUpdate={(patch) => onUpdateHolding(holding.ticker, patch)}
              onRemove={() => onRemoveHolding(holding.ticker)}
            />
          ))}
          {!manualHoldings.length && <div style={{ color: "#7d756d", fontSize: 13 }}>No holdings yet. Add them from the market cards.</div>}
        </div>
        <div style={{ color: "#7f776f", fontSize: 13, lineHeight: 1.6, marginTop: 14, marginBottom: 14 }}>
          Weights will be normalized to a $100 basket when you save.
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
          Finalize the basket details
        </div>
        <div style={{ color: "#948c84", fontSize: 14, lineHeight: 1.6, marginBottom: 18 }}>
          Give this basket a name and short description before Prism saves it.
        </div>
        <div style={{ display: "grid", gap: 10 }}>
          <input value={manualTitle} onChange={(e) => setManualTitle(e.target.value)} placeholder="Basket title" style={inputStyle} />
          <textarea value={manualSummary} onChange={(e) => setManualSummary(e.target.value)} rows={4} placeholder="What is this basket trying to express?" style={{ ...textareaStyle, minHeight: 120 }} />
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
