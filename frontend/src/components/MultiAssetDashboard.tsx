/**
 * Multi-Asset Dashboard — All charts on one scrollable page.
 * 2 assets per row, collapsible groups, MA toggles.
 */
import React, { useEffect, useRef, useState, useCallback } from "react";
import {
  useDashboardKlines,
  ASSET_GROUPS,
  TIMEFRAMES,
} from "../hooks/useDashboardKlines";
import type { Asset, HealthStatus } from "../hooks/useDashboardKlines";
import { KlineChart } from "./charts/KlineChart";
import type { KlineDataPoint, KlineChartProps } from "./charts/KlineChart";
import type { MAConfig } from "../types/chartConfig";
import "./MultiAssetDashboard.css";

// ─── MA Toggle Bar ───

const MA_KEYS: { key: keyof MAConfig; label: string }[] = [
  { key: "ma5", label: "MA5" },
  { key: "ma10", label: "MA10" },
  { key: "ma20", label: "MA20" },
  { key: "ma30", label: "MA30" },
  { key: "ma50", label: "MA50" },
];

function MAToggle({ config, onChange }: { config: MAConfig; onChange: (c: MAConfig) => void }) {
  return (
    <div className="ma-toggle-bar">
      {MA_KEYS.map(({ key, label }) => (
        <button
          key={key}
          className={`ma-toggle-btn ${config[key] ? "ma-toggle-btn--active" : ""} ma-toggle-btn--${key}`}
          onClick={() => onChange({ ...config, [key]: !config[key] })}
        >
          {label}
        </button>
      ))}
    </div>
  );
}

// ─── Health Dot ───

function HealthDot({ health }: { health: HealthStatus }) {
  const colorMap: Record<string, string> = {
    healthy: "#22c55e",
    degraded: "#eab308",
    error: "#ef4444",
    loading: "#6b7280",
  };
  const color = colorMap[health.status] || "#6b7280";

  return (
    <span className="health-dot" title={health.status}>
      <span className="health-dot__circle" style={{ backgroundColor: color }} />
      <span className="health-dot__label">{health.status}</span>
    </span>
  );
}

// ─── Single Chart Cell ───

const ChartCell = React.memo(function ChartCell({
  data,
  title,
  maConfig,
}: {
  data: KlineDataPoint[];
  title: string;
  maConfig: MAConfig;
}) {
  const ref = useRef<HTMLDivElement>(null);
  const [visible, setVisible] = useState(false);

  useEffect(() => {
    const el = ref.current;
    if (!el) return;
    const obs = new IntersectionObserver(
      ([e]) => { if (e.isIntersecting) { setVisible(true); obs.disconnect(); } },
      { rootMargin: "300px" }
    );
    obs.observe(el);
    return () => obs.disconnect();
  }, []);

  return (
    <div className="chart-cell" ref={ref}>
      {visible && data.length > 0 ? (
        <KlineChart
          data={data}
          height={240}
          showVolume={true}
          showMACD={true}
          compact={true}
          title={title}
          maConfig={maConfig}
        />
      ) : visible ? (
        <div className="chart-cell__empty">
          <span className="chart-cell__title">{title}</span>
          <span className="chart-cell__msg">暂无数据</span>
        </div>
      ) : (
        <div className="chart-cell__skeleton">
          <span className="chart-cell__title">{title}</span>
          <div className="chart-cell__pulse" />
        </div>
      )}
    </div>
  );
});

// ─── Asset Card (3 timeframe charts) ───

const AssetCard = React.memo(function AssetCard({
  asset,
  dataForAsset,
  maConfig,
}: {
  asset: Asset;
  dataForAsset: Record<string, KlineDataPoint[]> | undefined;
  maConfig: MAConfig;
}) {
  return (
    <div className="asset-card">
      <div className="asset-card__header">
        <span className="asset-card__name">{asset.name}</span>
        {asset.type === "index" && <span className="asset-card__code">{asset.id}</span>}
      </div>
      <div className="asset-card__charts">
        {TIMEFRAMES.map((tf) => (
          <ChartCell
            key={tf.id}
            data={dataForAsset?.[tf.id] || []}
            title={`${asset.name} — ${tf.label}`}
            maConfig={maConfig}
          />
        ))}
      </div>
    </div>
  );
});

// ─── Collapsible Group ───

function AssetGroupSection({
  title,
  emoji,
  assets,
  dataMap,
  maConfig,
  defaultOpen,
}: {
  title: string;
  emoji: string;
  assets: Asset[];
  dataMap: Record<string, Record<string, KlineDataPoint[]>>;
  maConfig: MAConfig;
  defaultOpen: boolean;
}) {
  const [open, setOpen] = useState(defaultOpen);

  // Pair assets into rows of 2
  const rows: Asset[][] = [];
  for (let i = 0; i < assets.length; i += 2) {
    rows.push(assets.slice(i, i + 2));
  }

  return (
    <div className="asset-group">
      <div className="asset-group__header" onClick={() => setOpen(!open)}>
        <span className="asset-group__toggle">{open ? "▼" : "▶"}</span>
        <h2 className="asset-group__title">
          <span>{emoji}</span> {title}
        </h2>
        <span className="asset-group__count">{assets.length} assets</span>
      </div>
      {open && (
        <div className="asset-group__body">
          {rows.map((row, ri) => (
            <div key={ri} className="asset-row-pair">
              {row.map((asset) => (
                <AssetCard
                  key={asset.id}
                  asset={asset}
                  dataForAsset={dataMap[asset.id]}
                  maConfig={maConfig}
                />
              ))}
              {/* Spacer if odd number */}
              {row.length === 1 && <div className="asset-card asset-card--spacer" />}
            </div>
          ))}
        </div>
      )}
    </div>
  );
}

// ─── Main Dashboard ───

export function MultiAssetDashboard() {
  const { dataMap, loading, loadingCount, totalCount, errors, health, refresh } =
    useDashboardKlines();

  const [maConfig, setMAConfig] = useState<MAConfig>({
    ma5: true,
    ma10: true,
    ma20: true,
    ma30: true,
    ma50: true,
  });

  return (
    <div className="multi-asset-dashboard">
      {/* Header */}
      <div className="dashboard__header">
        <h1 className="dashboard__title">Market Overview</h1>
        <div className="dashboard__controls">
          <MAToggle config={maConfig} onChange={setMAConfig} />
          <HealthDot health={health} />
          <button
            className="dashboard__refresh-btn"
            onClick={refresh}
            disabled={loading}
            title="Refresh"
          >
            {loading ? "⏳" : "🔄"}
          </button>
        </div>
      </div>

      {/* Loading progress */}
      {loading && (
        <div className="dashboard-progress">
          <div className="dashboard-progress__bar">
            <div
              className="dashboard-progress__fill"
              style={{ width: `${(loadingCount / totalCount) * 100}%` }}
            />
          </div>
          <span className="dashboard-progress__text">
            Loading {loadingCount}/{totalCount} charts…
          </span>
        </div>
      )}

      {/* Errors */}
      {errors.length > 0 && (
        <details className="dashboard-errors">
          <summary>⚠️ {errors.length} chart(s) failed</summary>
          <ul>
            {errors.map((e, i) => (
              <li key={i}>{e}</li>
            ))}
          </ul>
        </details>
      )}

      {/* Timeframe labels header */}
      <div className="tf-labels-row">
        <div className="tf-labels-row__spacer" />
        <div className="tf-labels-row__labels">
          {TIMEFRAMES.map((tf) => (
            <span key={tf.id} className="tf-label">{tf.label}</span>
          ))}
        </div>
        <div className="tf-labels-row__labels">
          {TIMEFRAMES.map((tf) => (
            <span key={tf.id + "2"} className="tf-label">{tf.label}</span>
          ))}
        </div>
      </div>

      {/* Groups */}
      <div className="dashboard-groups">
        {ASSET_GROUPS.map((group) => (
          <AssetGroupSection
            key={group.title}
            title={group.title}
            emoji={group.emoji}
            assets={group.assets}
            dataMap={dataMap}
            maConfig={maConfig}
            defaultOpen={true}
          />
        ))}
      </div>
    </div>
  );
}
