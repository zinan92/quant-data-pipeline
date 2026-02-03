/**
 * Multi-Asset Dashboard — A-Share Indexes, Commodities, Crypto
 * All-in-one market overview with real-time auto-refresh
 */
import { useDashboardData } from "../hooks/useDashboardData";
import type { AssetCardData } from "../types/dashboard";
import "./MultiAssetDashboard.css";

// ─── Mini Sparkline SVG ───

function Sparkline({ data, positive }: { data: number[]; positive: boolean }) {
  if (data.length < 2) return null;
  const min = Math.min(...data);
  const max = Math.max(...data);
  const range = max - min || 1;
  const w = 80;
  const h = 28;
  const step = w / (data.length - 1);

  const points = data
    .map((v, i) => `${i * step},${h - ((v - min) / range) * h}`)
    .join(" ");

  return (
    <svg width={w} height={h} className="sparkline" viewBox={`0 0 ${w} ${h}`}>
      <polyline
        fill="none"
        stroke={positive ? "var(--color-up)" : "var(--color-down)"}
        strokeWidth="1.5"
        points={points}
      />
    </svg>
  );
}

// ─── Asset Card ───

function AssetCard({ asset, showHiLo = true }: { asset: AssetCardData; showHiLo?: boolean }) {
  const positive = asset.changePct >= 0;
  const colorClass = positive ? "card--positive" : "card--negative";

  const formatPrice = (p: number) => {
    if (p === 0) return "—";
    if (p >= 10000) return p.toLocaleString("en-US", { minimumFractionDigits: 2, maximumFractionDigits: 2 });
    if (p >= 1) return p.toLocaleString("en-US", { minimumFractionDigits: 2, maximumFractionDigits: 4 });
    return p.toLocaleString("en-US", { minimumFractionDigits: 4, maximumFractionDigits: 6 });
  };

  return (
    <div className={`asset-card ${colorClass}`}>
      <div className="asset-card__header">
        <div className="asset-card__name">
          {asset.nameCn ? (
            <>
              <span className="asset-card__name-cn">{asset.nameCn}</span>
              <span className="asset-card__name-en">{asset.name}</span>
            </>
          ) : (
            <span className="asset-card__name-primary">{asset.name}</span>
          )}
        </div>
        <Sparkline data={asset.priceHistory} positive={positive} />
      </div>

      <div className="asset-card__price">{formatPrice(asset.price)}</div>

      <div className="asset-card__change">
        <span className={`asset-card__pct ${colorClass}`}>
          {positive ? "+" : ""}{asset.changePct.toFixed(2)}%
        </span>
        <span className={`asset-card__abs ${colorClass}`}>
          {positive ? "+" : ""}{formatPrice(Math.abs(asset.change))}
        </span>
      </div>

      {showHiLo && asset.high24h != null && asset.low24h != null && (asset.high24h > 0 || asset.low24h > 0) && (
        <div className="asset-card__hilo">
          <span className="hilo__label">H</span>
          <span className="hilo__val">{formatPrice(asset.high24h)}</span>
          <span className="hilo__label">L</span>
          <span className="hilo__val">{formatPrice(asset.low24h)}</span>
        </div>
      )}
    </div>
  );
}

// ─── Section ───

function DashboardSection({
  title,
  emoji,
  assets,
  showHiLo,
}: {
  title: string;
  emoji: string;
  assets: AssetCardData[];
  showHiLo?: boolean;
}) {
  return (
    <section className="dashboard-section">
      <h2 className="dashboard-section__title">
        <span className="dashboard-section__emoji">{emoji}</span>
        {title}
      </h2>
      <div className="dashboard-section__grid">
        {assets.length === 0 ? (
          <div className="dashboard-section__placeholder">Loading…</div>
        ) : (
          assets.map((a) => <AssetCard key={a.id} asset={a} showHiLo={showHiLo} />)
        )}
      </div>
    </section>
  );
}

// ─── Main Dashboard ───

export function MultiAssetDashboard() {
  const { indexes, commodities, crypto, loading, error, lastUpdate, refetch } =
    useDashboardData();

  return (
    <div className="multi-asset-dashboard">
      <div className="dashboard__header">
        <h1 className="dashboard__title">Market Overview</h1>
        <div className="dashboard__meta">
          {lastUpdate && (
            <span className="dashboard__update-time">Updated: {lastUpdate}</span>
          )}
          <button className="dashboard__refresh-btn" onClick={refetch} disabled={loading}>
            {loading ? "⏳" : "🔄"}
          </button>
        </div>
      </div>

      {error && (
        <div className="dashboard__error">
          ⚠️ {error}
          <button onClick={refetch} className="dashboard__retry-btn">Retry</button>
        </div>
      )}

      <DashboardSection
        title="A-Share Indexes"
        emoji="🇨🇳"
        assets={indexes}
        showHiLo={false}
      />

      <DashboardSection
        title="Commodities"
        emoji="🛢️"
        assets={commodities}
        showHiLo={true}
      />

      <DashboardSection
        title="Crypto"
        emoji="₿"
        assets={crypto}
        showHiLo={true}
      />
    </div>
  );
}
