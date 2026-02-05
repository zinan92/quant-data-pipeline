/**
 * 美股板块卡片面板 — A股对标21板块
 * 展示：ETF涨跌、K线迷你图、个股统计、领涨领跌
 */
import { useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { apiFetch } from "../utils/api";
import { KlineChart, type KlineDataPoint } from "./charts/KlineChart";
import "./USSectorCards.css";

// ── Types ──

interface StockInfo {
  symbol: string;
  name: string;
  change_pct: number;
  price: number;
}

interface SectorCard {
  key: string;
  name_cn: string;
  etf_symbol: string | null;
  etf_quote: {
    price: number;
    change: number;
    change_pct: number;
    [k: string]: any;
  } | null;
  stock_count: number;
  up_count: number;
  down_count: number;
  flat_count: number;
  top_gainer: StockInfo | null;
  top_loser: StockInfo | null;
  change_pct: number;
}

interface SectorCardDetail extends SectorCard {
  etf_kline: KlineDataPoint[] | null;
  stocks: Array<{
    symbol: string;
    cn_name: string;
    price: number;
    change: number;
    change_pct: number;
    [k: string]: any;
  }>;
}

// ── Mini sparkline from price history (fetched per card) ──

function MiniSparkline({ data, positive }: { data: number[]; positive: boolean }) {
  if (data.length < 2) return null;
  const min = Math.min(...data);
  const max = Math.max(...data);
  const range = max - min || 1;
  const w = 72;
  const h = 24;
  const step = w / (data.length - 1);
  const points = data
    .map((v, i) => `${i * step},${h - ((v - min) / range) * h}`)
    .join(" ");

  return (
    <svg width={w} height={h} viewBox={`0 0 ${w} ${h}`} className="us-sector-sparkline">
      <polyline
        fill="none"
        stroke={positive ? "var(--color-up, #ef5f7c)" : "var(--color-down, #23c19f)"}
        strokeWidth="1.5"
        points={points}
      />
    </svg>
  );
}

// ── Sector Card Component ──

function SectorCardItem({
  card,
  onClick,
  selected,
}: {
  card: SectorCard;
  onClick: () => void;
  selected: boolean;
}) {
  const positive = card.change_pct >= 0;
  const colorClass = positive ? "us-sector-card--up" : "us-sector-card--down";

  return (
    <div
      className={`us-sector-card ${colorClass} ${selected ? "us-sector-card--selected" : ""}`}
      onClick={onClick}
    >
      {/* Header: name + ETF */}
      <div className="us-sector-card__header">
        <span className="us-sector-card__name">{card.name_cn}</span>
        {card.etf_symbol && (
          <span className="us-sector-card__etf">{card.etf_symbol}</span>
        )}
      </div>

      {/* Change % */}
      <div className="us-sector-card__change">
        {positive ? "+" : ""}{card.change_pct.toFixed(2)}%
      </div>

      {/* Up/Down stats */}
      <div className="us-sector-card__stats">
        <span className="us-sector-card__stat us-sector-card__stat--up">
          ↑{card.up_count}
        </span>
        <span className="us-sector-card__stat us-sector-card__stat--down">
          ↓{card.down_count}
        </span>
        <span className="us-sector-card__stat us-sector-card__stat--total">
          {card.stock_count}只
        </span>
      </div>

      {/* Top gainer */}
      {card.top_gainer && card.top_gainer.change_pct > 0 && (
        <div className="us-sector-card__extreme">
          <span className="us-sector-card__extreme-label">领涨</span>
          <span className="us-sector-card__extreme-name">{card.top_gainer.name}</span>
          <span className="us-sector-card__extreme-value us-sector-card__extreme-value--up">
            +{card.top_gainer.change_pct.toFixed(2)}%
          </span>
        </div>
      )}

      {/* Top loser */}
      {card.top_loser && card.top_loser.change_pct < 0 && (
        <div className="us-sector-card__extreme">
          <span className="us-sector-card__extreme-label">领跌</span>
          <span className="us-sector-card__extreme-name">{card.top_loser.name}</span>
          <span className="us-sector-card__extreme-value us-sector-card__extreme-value--down">
            {card.top_loser.change_pct.toFixed(2)}%
          </span>
        </div>
      )}
    </div>
  );
}

// ── Sector Detail Panel (K-line + stocks table) ──

function SectorDetailPanel({ sectorKey }: { sectorKey: string }) {
  const { data, isLoading, error } = useQuery<SectorCardDetail>({
    queryKey: ["us-sector-detail", sectorKey],
    queryFn: async () => {
      const resp = await apiFetch(`/api/us-stock/sectors/cards/${sectorKey}`);
      if (!resp.ok) throw new Error("Failed to load sector detail");
      return resp.json();
    },
    staleTime: 60_000,
  });

  if (isLoading) return <div className="us-sector-detail__loading">加载中...</div>;
  if (error || !data) return <div className="us-sector-detail__error">加载失败</div>;

  // Transform kline data for chart component
  const klineData: KlineDataPoint[] = (data.etf_kline || []).map((k: any) => ({
    date: k.time || k.date,
    open: k.open,
    high: k.high,
    low: k.low,
    close: k.close,
    volume: k.volume || 0,
  }));

  return (
    <div className="us-sector-detail">
      <div className="us-sector-detail__header">
        <h3>{data.name_cn} — {data.etf_symbol}</h3>
        {data.etf_quote && (
          <span className={`us-sector-detail__price ${data.change_pct >= 0 ? "up" : "down"}`}>
            ${data.etf_quote.price.toFixed(2)}{" "}
            {data.change_pct >= 0 ? "+" : ""}{data.change_pct.toFixed(2)}%
          </span>
        )}
      </div>

      {/* K-line chart */}
      {klineData.length > 0 && (
        <div className="us-sector-detail__chart">
          <KlineChart
            data={klineData}
            height={320}
            showVolume={true}
            showMACD={false}
            maConfig={{ ma5: true, ma10: true, ma20: true, ma30: false, ma50: false }}
            title={`${data.etf_symbol} 日K`}
            compact={false}
          />
        </div>
      )}

      {/* Stocks table */}
      {data.stocks && data.stocks.length > 0 && (
        <div className="us-sector-detail__stocks">
          <table className="us-sector-detail__table">
            <thead>
              <tr>
                <th>代码</th>
                <th>名称</th>
                <th>价格</th>
                <th>涨跌幅</th>
              </tr>
            </thead>
            <tbody>
              {data.stocks.map((s) => (
                <tr key={s.symbol}>
                  <td className="us-sector-detail__symbol">{s.symbol}</td>
                  <td>{s.cn_name}</td>
                  <td>${s.price?.toFixed(2) ?? "—"}</td>
                  <td className={s.change_pct >= 0 ? "up" : "down"}>
                    {s.change_pct >= 0 ? "+" : ""}{s.change_pct?.toFixed(2) ?? 0}%
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}

// ── Main Panel ──

export function USSectorCards() {
  const [selectedSector, setSelectedSector] = useState<string | null>(null);

  const { data, isLoading, error, refetch } = useQuery<{ count: number; cards: SectorCard[] }>({
    queryKey: ["us-sector-cards"],
    queryFn: async () => {
      const resp = await apiFetch("/api/us-stock/sectors/cards");
      if (!resp.ok) throw new Error("Failed to load sector cards");
      return resp.json();
    },
    staleTime: 60_000,
    refetchInterval: 60_000,
  });

  const cards = data?.cards ?? [];

  return (
    <div className="us-sectors-panel">
      <div className="us-sectors-panel__header">
        <h2 className="us-sectors-panel__title">
          🇺🇸 美股板块 <span className="us-sectors-panel__subtitle">A股对标 · {cards.length}个板块</span>
        </h2>
        <button
          className="us-sectors-panel__refresh"
          onClick={() => refetch()}
          disabled={isLoading}
        >
          {isLoading ? "⏳" : "🔄"}
        </button>
      </div>

      {error && (
        <div className="us-sectors-panel__error">
          ⚠️ 加载失败 <button onClick={() => refetch()}>重试</button>
        </div>
      )}

      {/* Card Grid */}
      <div className="us-sectors-panel__grid">
        {isLoading && cards.length === 0 ? (
          <div className="us-sectors-panel__loading">加载板块数据...</div>
        ) : (
          cards.map((card) => (
            <SectorCardItem
              key={card.key}
              card={card}
              selected={selectedSector === card.key}
              onClick={() =>
                setSelectedSector(selectedSector === card.key ? null : card.key)
              }
            />
          ))
        )}
      </div>

      {/* Detail Panel (when a card is clicked) */}
      {selectedSector && (
        <div className="us-sectors-panel__detail">
          <SectorDetailPanel sectorKey={selectedSector} />
        </div>
      )}
    </div>
  );
}
