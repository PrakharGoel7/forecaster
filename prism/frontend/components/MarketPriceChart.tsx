import type { MarketHistory } from "@/lib/types";

export default function MarketPriceChart({ history }: { history: MarketHistory }) {
  const points = history.points;
  if (!points.length) return <div style={{ color: "#9b938b", fontSize: 13 }}>No historical Kalshi quotes for this period.</div>;

  const W = 700, H = 210, PL = 42, PR = 16, PT = 14, PB = 30;
  const times = points.map((p) => new Date(p.timestamp).getTime());
  const first = times[0], last = times[times.length - 1];
  const span = Math.max(last - first, 1);
  const prices = points.map((p) => p.yes_price);
  const low = Math.max(0, Math.min(...prices) - 0.05);
  const high = Math.min(1, Math.max(...prices) + 0.05);
  const range = Math.max(high - low, 0.01);
  const x = (time: number) => PL + ((time - first) / span) * (W - PL - PR);
  const y = (price: number) => H - PB - ((price - low) / range) * (H - PT - PB);
  const gap = history.period_minutes * 60_000 * 2.5;
  const lines: string[][] = [];
  points.forEach((point, i) => {
    if (i === 0 || times[i] - times[i - 1] > gap) lines.push([]);
    lines[lines.length - 1].push(`${x(times[i])},${y(point.yes_price)}`);
  });
  const dateLabel = (time: number) => new Date(time).toLocaleDateString(undefined, { month: "short", day: "numeric" });

  return (
    <svg viewBox={`0 0 ${W} ${H}`} role="img" aria-label={`Kalshi YES price history for ${history.ticker}`} style={{ display: "block", width: "100%", height: "auto" }}>
      {[low, (low + high) / 2, high].map((price) => (
        <g key={price}>
          <line x1={PL} x2={W - PR} y1={y(price)} y2={y(price)} stroke="rgba(255,255,255,0.09)" />
          <text x={PL - 6} y={y(price) + 4} textAnchor="end" fontSize="10" fill="#8c8680">{Math.round(price * 100)}%</text>
        </g>
      ))}
      {lines.map((line, i) => <polyline key={i} points={line.join(" ")} fill="none" stroke="#d9f471" strokeWidth="2.5" strokeLinejoin="round" strokeLinecap="round" />)}
      {points.length === 1 && <circle cx={x(first)} cy={y(points[0].yes_price)} r="4" fill="#d9f471" />}
      <circle cx={x(last)} cy={y(points[points.length - 1].yes_price)} r="4" fill="#d9f471">
        <title>{`${(points[points.length - 1].yes_price * 100).toFixed(1)}% · ${points[points.length - 1].timestamp}`}</title>
      </circle>
      <text x={PL} y={H - 7} fontSize="10" fill="#8c8680">{dateLabel(first)}</text>
      <text x={W - PR} y={H - 7} textAnchor="end" fontSize="10" fill="#8c8680">{dateLabel(last)}</text>
    </svg>
  );
}
