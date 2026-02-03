/**
 * Multi-Asset Dashboard — All 30 charts on one scrollable page.
 * 10 assets × 3 timeframes (日线, 30分, 5分) side by side.
 * No price cards. No clicking to switch. Everything visible at once.
 */
import React, { useEffect, useRef, useState } from "react";
import {
  useDashboardKlines,
  ASSET_GROUPS,
  TIMEFRAMES,
} from "../hooks/useDashboardKlines";
import type { Asset, HealthStatus } from "../hooks/useDashboardKlines";
import { KlineChart } from "./charts/KlineChart";
import type { KlineDataPoint } from "./charts/KlineChart";
import "./MultiAssetDashboard.css";

// ─── Health Dot ───

function HealthDot({ health }: { health: HealthStatus }) {
  const colorMap: Record<string, string> = {
    healthy: "#22c55e",
    degraded: "#eab308",
    error: "#ef4444",
    loading: "#6b7280",
  };
  const color = colorMap[health.status] || "#6b7280";
  const label =
    health.status === "healthy"
      ? "All systems OK"
      : health.status === "degraded"
        ? "Some data sources degraded"
        : health.status === "error"
          ? "Data source errors"
          : "Checking...";

  return (
    <span className="health-dot" title={label}>
      <span
        className="health-dot__circle"
        style={{ backgroundColor: color }}
      />
      <span className="health-dot__label">{health.status}</span>
    </span>
  );
}

// ─── Loading Skeleton ───

function ChartSkeleton() {
  return (
    <div className="dashboard-chart-cell">
      <div className="dashboard-chart-skeleton">
        <div className="skeleton-pulse" />
      </div>
    </div>
  );
}

// ─── Lazy Chart Wrapper (IntersectionObserver) ───

const LazyChart = React.memo(function LazyChart({
  data,
  title,
}: {
  data: KlineDataPoint[];
  title: string;
}) {
  const containerRef = useRef<HTMLDivElement>(null);
  const [visible, setVisible] = useState(false);

  useEffect(() => {
    const el = containerRef.current;
    if (!el) return;

    const observer = new IntersectionObserver(
      ([entry]) => {
        if (entry.isIntersecting) {
          setVisible(true);
          observer.disconnect();
        }
      },
      { rootMargin: "200px" }
    );

    observer.observe(el);
    return () => observer.disconnect();
  }, []);

  return (
    <div className="dashboard-chart-cell" ref={containerRef}>
      {visible && data.length > 0 ? (
        <KlineChart
          data={data}
          height={280}
          showVolume={true}
          showMACD={true}
          compact={true}
          title={title}
        />
      ) : visible && data.length === 0 ? (
        <div className="dashboard-chart-empty">
          <span className="dashboard-chart-empty__title">{title}</span>
          <span>暂无数据</span>
        </div>
      ) : (
        <div className="dashboard-chart-skeleton">
          <span className="dashboard-chart-skeleton__title">{title}</span>
          <div className="skeleton-pulse" />
        </div>
      )}
    </div>
  );
});

// ─── Asset Row ───

const AssetRow = React.memo(function AssetRow({
  asset,
  dataForAsset,
}: {
  asset: Asset;
  dataForAsset: Record<string, KlineDataPoint[]> | undefined;
}) {
  return (
    <div className="dashboard-asset-row">
      <div className="dashboard-asset-label">
        <span className="dashboard-asset-label__name">{asset.name}</span>
        {asset.type === "index" && (
          <span className="dashboard-asset-label__code">{asset.id}</span>
        )}
      </div>
      <div className="dashboard-asset-charts">
        {TIMEFRAMES.map((tf) => {
          const data = dataForAsset?.[tf.id] || [];
          const title = `${asset.name} — ${tf.label}`;
          return <LazyChart key={tf.id} data={data} title={title} />;
        })}
      </div>
    </div>
  );
});

// ─── Main Dashboard ───

export function MultiAssetDashboard() {
  const { dataMap, loading, loadingCount, totalCount, errors, health, refresh } =
    useDashboardKlines();

  return (
    <div className="multi-asset-dashboard multi-asset-dashboard--grid">
      {/* Header */}
      <div className="dashboard__header">
        <h1 className="dashboard__title">Market Overview</h1>
        <div className="dashboard__meta">
          <HealthDot health={health} />
          <button
            className="dashboard__refresh-btn"
            onClick={refresh}
            disabled={loading}
            title="Refresh all data"
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
          <summary className="dashboard-errors__summary">
            ⚠️ {errors.length} chart(s) failed to load
          </summary>
          <ul className="dashboard-errors__list">
            {errors.map((e, i) => (
              <li key={i}>{e}</li>
            ))}
          </ul>
        </details>
      )}

      {/* Timeframe header row */}
      <div className="dashboard-tf-header">
        <div className="dashboard-tf-header__label" />
        {TIMEFRAMES.map((tf) => (
          <div key={tf.id} className="dashboard-tf-header__cell">
            {tf.label}
          </div>
        ))}
      </div>

      {/* Chart Grid */}
      <div className="dashboard-chart-grid">
        {ASSET_GROUPS.map((group) => (
          <div key={group.title} className="dashboard-group">
            <h2 className="dashboard-group__title">
              <span className="dashboard-group__emoji">{group.emoji}</span>
              {group.title}
            </h2>
            {group.assets.map((asset) => (
              <AssetRow
                key={asset.id}
                asset={asset}
                dataForAsset={dataMap[asset.id]}
              />
            ))}
          </div>
        ))}
      </div>
    </div>
  );
}
