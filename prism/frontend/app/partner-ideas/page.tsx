import Link from "next/link";
import Header from "@/components/Header";
import GridOverlay from "@/components/GridOverlay";

const basketMatches = [
  { id: 34, basket: "Regional U.S. housing permits rebound", person: "Robert Dietz", fit: "NAHB chief economist; housing supply and builder conditions", source: "https://www.nahb.org/news-and-economics/press-releases/2026/02/2026-housing-outlook-ongoing-challenges-cautious-optimism-and-incremental-gains" },
  { id: 33, basket: "Tesla scales vehicles, energy, and Semi", person: "Cathie Wood", fit: "ARK founder; ARK has published detailed Tesla forecasts", source: "https://www.ark-invest.com/articles/valuation-models/arks-tesla-model" },
  { id: 32, basket: "U.S. tariff escalation broadens", person: "Scott Lincicome", fit: "Trade-policy scholar who analyzes tariffs", source: "https://www.cato.org/multimedia/power-problems/trouble-tariffs-future-trade" },
  { id: 31, basket: "Bitcoin rebound and institutional acceptance", person: "Michael Saylor", fit: "Strategy executive chairman and public Bitcoin advocate", source: "https://www.strategy.com/investor-relations/executive-team/michael-saylor" },
  { id: 30, basket: "U.S. growth stalls in winter 2026–27", person: "Claudia Sahm", fit: "Economist who developed a closely followed recession indicator", source: "https://claudiasahm.com/about/" },
  { id: 29, basket: "Federal Reserve stays higher for longer", person: "Mohamed El-Erian", fit: "Macroeconomic commentator on Federal Reserve policy", source: "https://www.allianz.com/en/mediacenter/news/articles/250407-us-tariffs-understanding-a-new-trading-landscape.html" },
  { id: 28, basket: "Frontier AI accelerates into 2027", person: "Dario Amodei", fit: "Anthropic CEO who writes about frontier AI trajectories", source: "https://www.anthropic.com/news/anthropic-s-recommendations-ostp-u-s-ai-action-plan" },
  { id: 27, basket: "Heat records and climate targets missed", person: "Katharine Hayhoe", fit: "Climate scientist focused on impacts and communication", source: "https://www.katharinehayhoe.com/biography/" },
  { id: 26, basket: "San Antonio Spurs 2026–27 title run", person: "Tony Parker", fit: "Retired Spurs star and Hall of Fame inductee", source: "https://www.nba.com/spurs/tonyhof" },
  { id: 25, basket: "Hormuz disruption and Iran standoff persist", person: "Ian Bremmer", fit: "Geopolitical analyst with Middle East expertise", source: "https://www.eurasiagroup.net/people/ibremmer" },
];

const showSponsors = [
  { person: "Bill Maher", show: "Club Random", idea: "Culture, media, and political narratives", source: "https://podcasts.apple.com/au/podcast/scott-galloway-club-random-with-bill-maher/id1613459129?i=1000785423890" },
  { person: "Bobby Lee", show: "TigerBelly", idea: "Comedy, entertainment, and audience trends", source: "https://podcasts.apple.com/us/podcast/tigerbelly/id1041201977" },
  { person: "Ben Shapiro", show: "The Ben Shapiro Show", idea: "Elections and policy outcomes", source: "https://podcasts.apple.com/us/podcast/ep-2402-note-to-america-haters-sorry-were-busy-kicking-a/id1047335260?i=1000760066333" },
  { person: "Konstantin Kisin & Francis Foster", show: "TRIGGERnometry", idea: "Politics, media, and public debate", source: "https://podcasts.apple.com/ca/podcast/civil-servants-triggered-by-british-flag-is-trump-getting/id1375568988?i=1000786540766" },
  { person: "Patrick Bet-David", show: "PBD Podcast", idea: "Business, tech, and IPOs", source: "https://valuetainment.com/openai-spacex-ipos-bitcoins-big-sell-off-pbd-815/" },
];

const topicProspects = [
  { person: "Guillermo del Toro", idea: "Genre films and the Oscars", source: "https://awardsdatabase.oscars.org/" },
  { person: "Tainy", idea: "Latin singles and production", source: "https://www.grammy.com/video/reggaeton-latin-pop-pioneer-producer-tainy-working-j-balvin-more-behind-board/" },
  { person: "Edgar Barrera", idea: "Latin albums and crossover hits", source: "https://www.grammy.com/news/edgar-barrera-interview-border-town-latin-hits-2024-grammys/" },
  { person: "Steven Bartlett", idea: "Long-form podcast guests", source: "https://stevenbartlett.com/doac/" },
  { person: "Ben Gilbert", idea: "Tech companies and IPOs", source: "https://www.acquired.fm/about" },
];

const card: React.CSSProperties = { background: "#fff", border: "1px solid rgba(0,0,0,0.08)", borderRadius: 16, padding: 20 };
const grid: React.CSSProperties = { display: "grid", gridTemplateColumns: "repeat(auto-fill, minmax(280px, 1fr))", gap: 14 };
const sourceStyle: React.CSSProperties = { color: "#4f46e5", fontSize: 12, textDecoration: "none" };

export default function PartnerIdeasPage() {
  return (
    <div style={{ minHeight: "100vh", background: "#f8f6f2", position: "relative" }}>
      <Header />
      <GridOverlay />
      <main style={{ position: "relative", zIndex: 10, maxWidth: 1140, margin: "0 auto", padding: "112px 24px 80px" }}>
        <div style={{ color: "#4f46e5", fontSize: 11, fontWeight: 700, textTransform: "uppercase", letterSpacing: "0.15em" }}>Prism editorial research</div>
        <h1 style={{ color: "#1c1814", fontSize: "clamp(36px, 5vw, 60px)", letterSpacing: "-0.05em", lineHeight: 1.05, margin: "12px 0 16px" }}>Partner ideas &amp; thesis matches</h1>
        <p style={{ color: "#6e675f", fontSize: 16, lineHeight: 1.7, maxWidth: 810, marginBottom: 16 }}>
          These are Prism&apos;s editorial suggestions for people whose public work fits a topic. None of the people below authored, approved, endorsed, or necessarily agrees with a basket or its positions. Show sponsorships are labeled separately from personal partnerships.
        </p>
        <Link href="/users/prism_editorial" style={{ ...sourceStyle, fontWeight: 700 }}>Explore Prism&apos;s hypothetical editorial baskets →</Link>

        <section style={{ marginTop: 56 }}>
          <h2 style={{ color: "#1c1814", fontSize: 25, letterSpacing: "-0.03em" }}>Who could speak to the current ten?</h2>
          <p style={{ color: "#6e675f", lineHeight: 1.6 }}>Topic fit only. These live baskets retain their actual attribution.</p>
          <div style={grid}>
            {basketMatches.map(item => <div key={item.id} style={card}>
              <Link href={`/baskets/${item.id}`} style={{ color: "#1c1814", fontWeight: 700, textDecoration: "none", lineHeight: 1.45 }}>{item.basket} →</Link>
              <div style={{ color: "#4f46e5", fontWeight: 700, marginTop: 12 }}>{item.person}</div>
              <p style={{ color: "#6e675f", fontSize: 13, lineHeight: 1.6 }}>{item.fit}</p>
              <a href={item.source} target="_blank" rel="noopener noreferrer" style={sourceStyle}>Why this topic fits ↗</a>
            </div>)}
          </div>
        </section>

        <section style={{ marginTop: 56 }}>
          <h2 style={{ color: "#1c1814", fontSize: 25, letterSpacing: "-0.03em" }}>Additional non-sports names with Kalshi show sponsorships</h2>
          <p style={{ color: "#6e675f", lineHeight: 1.6 }}>A sponsor mention on a show does not establish a personal ambassador agreement or approval of any Prism basket.</p>
          <div style={grid}>
            {showSponsors.map(item => <div key={item.person} style={card}>
              <div style={{ color: "#1c1814", fontWeight: 700 }}>{item.person}</div>
              <div style={{ color: "#9b9390", fontSize: 12, marginTop: 4 }}>{item.show} · show-level sponsor evidence</div>
              <p style={{ color: "#6e675f", fontSize: 13, lineHeight: 1.6 }}>{item.idea}</p>
              <a href={item.source} target="_blank" rel="noopener noreferrer" style={sourceStyle}>Sponsor evidence ↗</a>
            </div>)}
          </div>
        </section>

        <section style={{ marginTop: 56 }}>
          <h2 style={{ color: "#1c1814", fontSize: 25, letterSpacing: "-0.03em" }}>Other topic-fit prospects</h2>
          <p style={{ color: "#6e675f", lineHeight: 1.6 }}>These names have relevant public work; no Kalshi tie or Prism involvement has been verified.</p>
          <div style={grid}>
            {topicProspects.map(item => <div key={item.person} style={card}>
              <div style={{ color: "#1c1814", fontWeight: 700 }}>{item.person}</div>
              <p style={{ color: "#6e675f", fontSize: 13, lineHeight: 1.6 }}>{item.idea}</p>
              <a href={item.source} target="_blank" rel="noopener noreferrer" style={sourceStyle}>Background ↗</a>
            </div>)}
          </div>
        </section>
      </main>
    </div>
  );
}
