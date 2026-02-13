import { useState, useEffect, useCallback } from "react";

interface SourceStatus {
  status?: string;
  last_update?: string;
  latest_date?: string;
  latest_time?: string;
  last_modified?: string;
  last_collected_at?: string;
  latest_published_at?: string;
  articles_last_24h?: number;
  count?: number;
  symbols?: number;
  stale?: number;
  record_count?: number;
  exists?: boolean;
  detail?: string;
  [key: string]: unknown;
}

interface UnifiedHealth {
  status: "healthy" | "degraded" | "unhealthy";
  timestamp: string;
  quant: Record<string, SourceStatus>;
  qualitative: Record<string, SourceStatus | string>;
}

type Freshness = "fresh" | "stale" | "critical" | "unconfigured";

function getTimestamp(src: SourceStatus): string | null {
  return (
    src.last_update ||
    src.latest_time ||
    src.latest_date ||
    src.last_modified ||
    src.last_collected_at ||
    null
  );
}

function parseTime(ts: string | null): Date | null {
  if (!ts) return null;
  // Handle date-only strings (e.g. "2026-02-13")
  if (/^\d{4}-\d{2}-\d{2}$/.test(ts)) {
    return new Date(ts + "T23:59:59");
  }
  // Handle time-only strings (e.g. "00:29:46") — assume today
  if (/^\d{2}:\d{2}:\d{2}$/.test(ts)) {
    const today = new Date().toISOString().slice(0, 10);
    return new Date(`${today}T${ts}`);
  }
  // Handle "YYYY-MM-DD HH:MM:SS UTC" format
  const normalized = ts.replace(" UTC", "Z").replace(" ", "T");
  const d = new Date(normalized);
  return isNaN(d.getTime()) ? null : d;
}

function getAgeMinutes(ts: string | null): number | null {
  const d = parseTime(ts);
  if (!d) return null;
  return (Date.now() - d.getTime()) / 60000;
}

type ThresholdKey = "realtime" | "daily" | "qualitative";

/** Check if a date falls on a weekend or is followed by weekend days. */
function getDailyThresholds(): { yellow: number; red: number } {
  const now = new Date();
  const day = now.getDay(); // 0=Sun, 6=Sat
  // On weekends or Monday before market open, relax daily thresholds
  if (day === 0 || day === 6 || day === 1) {
    return { yellow: 50 * 60, red: 72 * 60 }; // 50h yellow, 72h red
  }
  return { yellow: 26 * 60, red: 48 * 60 };
}

const THRESHOLDS: Record<ThresholdKey, { yellow: number; red: number }> = {
  realtime: { yellow: 5, red: 30 },
  daily: getDailyThresholds(),
  qualitative: { yellow: 24 * 60, red: 72 * 60 },
};

function classifySource(key: string): ThresholdKey {
  if (key.startsWith("klines_") || key.startsWith("file_")) return "daily";
  if (
    key.includes("realtime") ||
    key === "crypto_ws"
  )
    return "realtime";
  return "daily";
}

function getFreshness(key: string, src: SourceStatus, isQualitative: boolean): Freshness {
  if (src.status === "unconfigured" || src.status === "no_data" || src.status === "missing")
    return "unconfigured";
  if (src.status === "error")
    return "critical";
  const ts = getTimestamp(src);
  const age = getAgeMinutes(ts);
  // If backend says "ok" but we can't parse a timestamp, trust the status
  if (age === null) return src.status === "ok" ? "fresh" : "critical";
  const thresholdKey = isQualitative ? "qualitative" : classifySource(key);
  const { yellow, red } = THRESHOLDS[thresholdKey];
  if (age > red) return "critical";
  if (age > yellow) return "stale";
  return "fresh";
}

function freshnessIcon(f: Freshness): string {
  if (f === "fresh") return "\u{1F7E2}";
  if (f === "stale") return "\u{1F7E1}";
  if (f === "unconfigured") return "\u26AA";
  return "\u{1F534}";
}

function formatAge(ts: string | null): string {
  const age = getAgeMinutes(ts);
  if (age === null) return "N/A";
  if (age < 1) return "刚刚";
  if (age < 60) return `${Math.round(age)}分钟前`;
  if (age < 1440) return `${Math.round(age / 60)}小时前`;
  return `${Math.round(age / 1440)}天前`;
}

function prettyName(key: string): string {
  const MAP: Record<string, string> = {
    index_realtime: "A股指数实时",
    commodities_realtime: "商品实时",
    crypto_ws: "加密货币WebSocket",
    klines_stock_DAY: "股票日K",
    klines_index_DAY: "指数日K",
    klines_concept_DAY: "概念日K",
    klines_stock_MINS_30: "股票30分K",
    klines_index_MINS_30: "指数30分K",
    klines_concept_MINS_30: "概念30分K",
    file_hot_concept_categories: "热门概念分类",
    file_concept_to_tickers: "概念→个股映射",
    file_ticker_to_concepts: "个股→概念映射",
    file_monitor_cache: "监控缓存",
    file_momentum_signals: "动量信号",
    twitter: "Twitter",
    hackernews: "Hacker News",
    substack: "Substack",
    youtube: "YouTube",
    xueqiu: "雪球",
  };
  return MAP[key] || key;
}

function overallLabel(status: string): { text: string; cls: string } {
  if (status === "healthy") return { text: "所有活跃数据源正常", cls: "health-overall--ok" };
  if (status === "degraded") return { text: "部分数据可能过期", cls: "health-overall--warn" };
  return { text: "数据异常", cls: "health-overall--error" };
}

export function HealthDashboard() {
  const [data, setData] = useState<UnifiedHealth | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const fetchData = useCallback(async () => {
    try {
      const resp = await fetch("/api/health/unified");
      if (!resp.ok) throw new Error(`HTTP ${resp.status}`);
      setData(await resp.json());
      setError(null);
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    fetchData();
    const id = setInterval(fetchData, 60_000);
    return () => clearInterval(id);
  }, [fetchData]);

  if (loading && !data)
    return <div className="health-dashboard"><p>加载中...</p></div>;
  if (error && !data)
    return <div className="health-dashboard"><p style={{ color: "#f87171" }}>加载失败: {error}</p></div>;
  if (!data) return null;

  const overall = overallLabel(data.status);
  const quantEntries = Object.entries(data.quant);
  const qualEntries = Object.entries(data.qualitative).filter(
    ([k]) => k !== "service_status"
  );
  const serviceStatus = data.qualitative.service_status as string;

  return (
    <div className="health-dashboard">
      <div className={`health-overall ${overall.cls}`}>
        <span className="health-overall__text">{overall.text}</span>
        <span className="health-overall__ts">
          更新于 {new Date(data.timestamp).toLocaleTimeString("zh-CN")}
        </span>
      </div>

      <section className="health-section">
        <h2 className="health-section__title">定量数据源</h2>
        <table className="health-table">
          <thead>
            <tr>
              <th>数据源</th>
              <th>状态</th>
              <th>最后更新</th>
              <th>新鲜度</th>
              <th>详情</th>
            </tr>
          </thead>
          <tbody>
            {quantEntries.map(([key, src]) => {
              const f = getFreshness(key, src, false);
              const ts = getTimestamp(src);
              return (
                <tr key={key}>
                  <td className="health-table__name">{prettyName(key)}</td>
                  <td>{freshnessIcon(f)}</td>
                  <td className="health-table__time">
                    {ts || "—"}
                  </td>
                  <td className="health-table__age">{formatAge(ts)}</td>
                  <td className="health-table__detail">
                    {src.record_count != null && `${src.record_count.toLocaleString()} 条`}
                    {src.symbols != null && `${src.symbols} 品种`}
                    {src.stale ? ` (${src.stale} stale)` : ""}
                    {src.detail || ""}
                  </td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </section>

      <section className="health-section">
        <h2 className="health-section__title">
          定性数据源
          {serviceStatus === "unavailable" && (
            <span className="health-badge health-badge--error">park-intel 不可用</span>
          )}
        </h2>
        {serviceStatus === "unavailable" ? (
          <p style={{ color: "#f87171", padding: "0.5rem 1rem" }}>
            park-intel 服务 (port 8001) 无法连接
          </p>
        ) : (
          <table className="health-table">
            <thead>
              <tr>
                <th>数据源</th>
                <th>状态</th>
                <th>最后采集</th>
                <th>新鲜度</th>
                <th>24h 文章数</th>
              </tr>
            </thead>
            <tbody>
              {qualEntries.map(([key, src]) => {
                const s = src as SourceStatus;
                const f = getFreshness(key, s, true);
                return (
                  <tr key={key}>
                    <td className="health-table__name">{prettyName(key)}</td>
                    <td>{freshnessIcon(f)}</td>
                    <td className="health-table__time">
                      {s.last_collected_at || "—"}
                    </td>
                    <td className="health-table__age">{formatAge(s.last_collected_at || null)}</td>
                    <td className="health-table__detail">{s.articles_last_24h ?? "—"}</td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        )}
      </section>
    </div>
  );
}
