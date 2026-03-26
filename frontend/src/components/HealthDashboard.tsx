import { useState, useEffect, useCallback, useRef } from "react";

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
  sector_count?: number;
  exists?: boolean;
  detail?: string;
  [key: string]: unknown;
}

interface GapDetail {
  symbol_code: string;
  symbol_name: string;
  symbol_type: string;
  gap_count: number;
  missing_dates: string[];
}

interface GapsData {
  total_gaps: number;
  by_type: {
    STOCK: { symbols_with_gaps: number; total_missing_days: number };
    INDEX: { symbols_with_gaps: number; total_missing_days: number };
  };
  details: GapDetail[];
  calendar_coverage: {
    min_date: string;
    max_date: string;
    trading_days: number;
  };
}

interface FailureItem {
  id: number;
  update_type: string;
  symbol_type: string;
  timeframe: string;
  status: string;
  error_message: string | null;
  started_at: string | null;
}

interface FailuresData {
  failures: FailureItem[];
  count: number;
}

interface ConsistencyItem {
  symbol: string;
  is_consistent: boolean;
  details: string;
}

interface ConsistencyData {
  summary: {
    total_validated: number;
    total_inconsistencies: number;
    consistency_rate: number;
    is_healthy: boolean;
  };
  indexes: ConsistencyItem[];
  concepts: ConsistencyItem[];
  inconsistencies: ConsistencyItem[];
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

type ThresholdKey = "realtime" | "daily" | "qualitative" | "manual";

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
  manual: { yellow: 14 * 24 * 60, red: 30 * 24 * 60 },
};

function classifySource(key: string): ThresholdKey {
  if (key.startsWith("klines_") || key.startsWith("file_")) return "daily";
  if (
    key.includes("realtime") ||
    key === "crypto_ws"
  )
    return "realtime";
  if (key === "stock_sectors") return "manual";
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
    stock_sectors: "自选板块(19)",
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

function fireStatusChangeNotification(newStatus: string) {
  if (typeof Notification === 'undefined') return;
  if (Notification.permission !== 'granted') return;
  
  const statusText = newStatus === 'degraded' ? '部分数据过期' : '数据异常';
  new Notification('数据健康降级', {
    body: `系统状态已变更为: ${statusText}`,
    icon: '/favicon.ico'
  });
}

function getOverallStatus(
  unifiedStatus: string,
  gaps: GapsData | null,
  consistency: ConsistencyData | null
): string {
  // Start with unified status
  let status = unifiedStatus;
  
  // Check gaps - if significant gaps exist, downgrade to degraded
  if (gaps && gaps.total_gaps > 100) {
    if (status === "healthy") status = "degraded";
  }
  
  // Check consistency - if unhealthy, downgrade
  if (consistency && !consistency.summary.is_healthy) {
    if (status === "healthy") status = "degraded";
  }
  
  return status;
}

export function HealthDashboard() {
  const [data, setData] = useState<UnifiedHealth | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  
  // New state for additional health endpoints
  const [gaps, setGaps] = useState<GapsData | null>(null);
  const [gapsError, setGapsError] = useState<string | null>(null);
  const [gapsExpanded, setGapsExpanded] = useState<Record<string, boolean>>({});
  const [searchQuery, setSearchQuery] = useState("");
  
  const [failures, setFailures] = useState<FailuresData | null>(null);
  const [failuresError, setFailuresError] = useState<string | null>(null);
  
  const [consistency, setConsistency] = useState<ConsistencyData | null>(null);
  const [consistencyLoading, setConsistencyLoading] = useState(true);
  const [consistencyError, setConsistencyError] = useState<string | null>(null);
  
  // Track previous status for notification
  const previousStatus = useRef<string | null>(null);
  const notificationPermissionRequested = useRef(false);

  const fetchData = useCallback(async () => {
    try {
      const resp = await fetch("/api/health/unified");
      if (!resp.ok) throw new Error(`HTTP ${resp.status}`);
      const unifiedData = await resp.json();
      setData(unifiedData);
      setError(null);
      
      // Check for status transition and fire notification
      if (previousStatus.current === "healthy" && 
          (unifiedData.status === "degraded" || unifiedData.status === "unhealthy")) {
        fireStatusChangeNotification(unifiedData.status);
      }
      previousStatus.current = unifiedData.status;
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setLoading(false);
    }
  }, []);
  
  const fetchGaps = useCallback(async () => {
    try {
      const resp = await fetch("/api/health/gaps");
      if (!resp.ok) throw new Error(`HTTP ${resp.status}`);
      setGaps(await resp.json());
      setGapsError(null);
    } catch (e) {
      setGapsError((e as Error).message);
    }
  }, []);
  
  const fetchFailures = useCallback(async () => {
    try {
      const resp = await fetch("/api/health/failures");
      if (!resp.ok) throw new Error(`HTTP ${resp.status}`);
      setFailures(await resp.json());
      setFailuresError(null);
    } catch (e) {
      setFailuresError((e as Error).message);
    }
  }, []);
  
  const fetchConsistency = useCallback(async () => {
    setConsistencyLoading(true);
    try {
      const resp = await fetch("/api/health/consistency");
      if (!resp.ok) throw new Error(`HTTP ${resp.status}`);
      setConsistency(await resp.json());
      setConsistencyError(null);
    } catch (e) {
      setConsistencyError((e as Error).message);
    } finally {
      setConsistencyLoading(false);
    }
  }, []);

  // Request notification permission on first load
  useEffect(() => {
    if (!notificationPermissionRequested.current && typeof Notification !== 'undefined') {
      Notification.requestPermission();
      notificationPermissionRequested.current = true;
    }
  }, []);

  useEffect(() => {
    // Fetch all data on mount and every 60s
    fetchData();
    fetchGaps();
    fetchFailures();
    fetchConsistency();
    
    const id = setInterval(() => {
      fetchData();
      fetchGaps();
      fetchFailures();
      fetchConsistency();
    }, 60_000);
    
    return () => clearInterval(id);
  }, [fetchData, fetchGaps, fetchFailures, fetchConsistency]);

  if (loading && !data)
    return <div className="health-dashboard"><p>加载中...</p></div>;
  if (error && !data)
    return <div className="health-dashboard"><p style={{ color: "#f87171" }}>加载失败: {error}</p></div>;
  if (!data) return null;

  // Calculate overall status considering gaps and consistency
  const overallStatus = getOverallStatus(data.status, gaps, consistency);
  const overall = overallLabel(overallStatus);
  const quantEntries = Object.entries(data.quant);
  const qualEntries = Object.entries(data.qualitative).filter(
    ([k]) => k !== "service_status"
  );
  const serviceStatus = data.qualitative.service_status as string;
  
  // Filter gap details by search query
  const filteredGapDetails = gaps?.details.filter(detail => 
    detail.symbol_code.toLowerCase().includes(searchQuery.toLowerCase()) ||
    detail.symbol_name.toLowerCase().includes(searchQuery.toLowerCase())
  ) || [];

  return (
    <div className="health-dashboard">
      <div className={`health-overall ${overall.cls}`}>
        <span className="health-overall__text">{overall.text}</span>
        <span className="health-overall__ts">
          更新于 {new Date(data.timestamp).toLocaleTimeString("zh-CN")}
        </span>
      </div>

      {/* Trade Calendar Health Section */}
      <section className="health-section">
        <h2 className="health-section__title">📅 交易日历健康</h2>
        {gaps ? (
          <div className="health-calendar">
            <div className="health-calendar__item">
              <span className="health-calendar__label">日期范围:</span>
              <span className="health-calendar__value">
                {gaps.calendar_coverage.min_date} 至 {gaps.calendar_coverage.max_date}
              </span>
            </div>
            <div className="health-calendar__item">
              <span className="health-calendar__label">交易日总数:</span>
              <span className="health-calendar__value">{gaps.calendar_coverage.trading_days}</span>
            </div>
            <div className="health-calendar__item">
              <span className="health-calendar__label">状态:</span>
              <span className={`health-calendar__status ${gaps.calendar_coverage.trading_days >= 1300 ? 'health-calendar__status--ok' : 'health-calendar__status--warn'}`}>
                {gaps.calendar_coverage.trading_days >= 1300 ? '✓ 正常' : '⚠ 不完整'}
              </span>
            </div>
          </div>
        ) : gapsError ? (
          <p style={{ color: "#f87171", padding: "0.5rem 1rem" }}>加载失败: {gapsError}</p>
        ) : (
          <p style={{ padding: "0.5rem 1rem" }}>加载中...</p>
        )}
      </section>

      {/* Gap Detection Section */}
      <section className="health-section">
        <h2 className="health-section__title">🔍 数据缺口检测</h2>
        {gapsError ? (
          <p style={{ color: "#f87171", padding: "0.5rem 1rem" }}>加载失败: {gapsError}</p>
        ) : !gaps ? (
          <p style={{ padding: "0.5rem 1rem" }}>加载中...</p>
        ) : gaps.total_gaps === 0 ? (
          <p style={{ color: "#22c55e", padding: "0.5rem 1rem" }}>✓ 未发现数据缺口</p>
        ) : (
          <>
            <div className="health-gap-summary">
              <div className="health-gap-summary__item">
                <span className="health-gap-summary__label">总缺口数:</span>
                <span className="health-gap-summary__value health-gap-summary__value--total">{gaps.total_gaps}</span>
              </div>
              <div className="health-gap-summary__item">
                <span className="health-gap-summary__label">股票:</span>
                <span className="health-gap-summary__value">
                  {gaps.by_type.STOCK.symbols_with_gaps} 只 / {gaps.by_type.STOCK.total_missing_days} 缺失日
                </span>
              </div>
              <div className="health-gap-summary__item">
                <span className="health-gap-summary__label">指数:</span>
                <span className="health-gap-summary__value">
                  {gaps.by_type.INDEX.symbols_with_gaps} 只 / {gaps.by_type.INDEX.total_missing_days} 缺失日
                </span>
              </div>
            </div>
            <div className="health-gap-details">
              <h3 className="health-gap-details__title">缺口最多的前 {gaps.details.length} 个品种:</h3>
              {gaps.details.slice(0, 10).map(detail => (
                <div key={detail.symbol_code} className="health-gap-item">
                  <div 
                    className="health-gap-item__header"
                    onClick={() => setGapsExpanded(prev => ({
                      ...prev,
                      [detail.symbol_code]: !prev[detail.symbol_code]
                    }))}
                  >
                    <span className="health-gap-item__symbol">
                      {detail.symbol_code} - {detail.symbol_name}
                      <span className="health-gap-item__type">[{detail.symbol_type}]</span>
                    </span>
                    <span className="health-gap-item__count">
                      {detail.gap_count} 个缺口
                      <span className="health-gap-item__toggle">
                        {gapsExpanded[detail.symbol_code] ? ' ▼' : ' ▶'}
                      </span>
                    </span>
                  </div>
                  {gapsExpanded[detail.symbol_code] && (
                    <div className="health-gap-item__dates">
                      {detail.missing_dates.slice(0, 20).join(', ')}
                      {detail.missing_dates.length > 20 && ` ... (${detail.missing_dates.length - 20} more)`}
                    </div>
                  )}
                </div>
              ))}
            </div>
          </>
        )}
      </section>

      {/* Per-Stock Drill-Down Section */}
      <section className="health-section">
        <h2 className="health-section__title">📊 个股状态钻取</h2>
        {gapsError ? (
          <p style={{ color: "#f87171", padding: "0.5rem 1rem" }}>加载失败: {gapsError}</p>
        ) : !gaps ? (
          <p style={{ padding: "0.5rem 1rem" }}>加载中...</p>
        ) : (
          <>
            <div className="health-stock-search">
              <input
                type="text"
                placeholder="搜索股票代码或名称..."
                value={searchQuery}
                onChange={(e) => setSearchQuery(e.target.value)}
                className="health-stock-search__input"
              />
              <span className="health-stock-search__count">
                显示 {filteredGapDetails.length} / {gaps.details.length} 个品种
              </span>
            </div>
            <div className="health-stock-list">
              {filteredGapDetails.slice(0, 20).map(detail => (
                <div key={detail.symbol_code} className="health-stock-item">
                  <span className="health-stock-item__code">{detail.symbol_code}</span>
                  <span className="health-stock-item__name">{detail.symbol_name}</span>
                  <span className={`health-stock-item__indicator ${detail.gap_count === 0 ? 'health-stock-item__indicator--fresh' : detail.gap_count < 10 ? 'health-stock-item__indicator--stale' : 'health-stock-item__indicator--critical'}`}>
                    {detail.gap_count === 0 ? '✓' : detail.gap_count < 10 ? '⚠' : '✗'}
                  </span>
                  <span className="health-stock-item__gaps">{detail.gap_count} 缺口</span>
                </div>
              ))}
              {filteredGapDetails.length > 20 && (
                <p style={{ textAlign: 'center', color: 'rgba(230, 237, 247, 0.5)', fontSize: '0.8rem', padding: '0.5rem' }}>
                  仅显示前 20 个结果，请使用搜索框过滤
                </p>
              )}
            </div>
          </>
        )}
      </section>

      {/* Recent Failures Section */}
      <section className="health-section">
        <h2 className="health-section__title">⚠️ 近期更新失败</h2>
        {failuresError ? (
          <p style={{ color: "#f87171", padding: "0.5rem 1rem" }}>加载失败: {failuresError}</p>
        ) : !failures ? (
          <p style={{ padding: "0.5rem 1rem" }}>加载中...</p>
        ) : failures.count === 0 ? (
          <p style={{ color: "#22c55e", padding: "0.5rem 1rem" }}>✓ 近期无更新失败</p>
        ) : (
          <table className="health-table">
            <thead>
              <tr>
                <th>更新类型</th>
                <th>品种类型</th>
                <th>时间周期</th>
                <th>错误信息</th>
                <th>时间</th>
              </tr>
            </thead>
            <tbody>
              {failures.failures.slice(0, 20).map(failure => (
                <tr key={failure.id}>
                  <td className="health-table__name">{failure.update_type}</td>
                  <td>{failure.symbol_type || '—'}</td>
                  <td>{failure.timeframe || '—'}</td>
                  <td className="health-table__error">{failure.error_message || '—'}</td>
                  <td className="health-table__time">
                    {failure.started_at ? new Date(failure.started_at).toLocaleString("zh-CN") : '—'}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </section>

      {/* Data Consistency Section */}
      <section className="health-section">
        <h2 className="health-section__title">🔬 数据一致性检查</h2>
        {consistencyError ? (
          <p style={{ color: "#f87171", padding: "0.5rem 1rem" }}>加载失败: {consistencyError}</p>
        ) : consistencyLoading ? (
          <div className="health-consistency-loading">
            <span className="health-spinner">⏳</span>
            <span>正在检查数据一致性...</span>
          </div>
        ) : !consistency ? (
          <p style={{ padding: "0.5rem 1rem" }}>无数据</p>
        ) : (
          <>
            <div className="health-consistency-summary">
              <div className="health-consistency-summary__item">
                <span className="health-consistency-summary__label">一致性率:</span>
                <span className={`health-consistency-summary__value ${consistency.summary.is_healthy ? 'health-consistency-summary__value--ok' : 'health-consistency-summary__value--warn'}`}>
                  {(consistency.summary.consistency_rate * 100).toFixed(1)}%
                </span>
              </div>
              <div className="health-consistency-summary__item">
                <span className="health-consistency-summary__label">已验证:</span>
                <span className="health-consistency-summary__value">{consistency.summary.total_validated}</span>
              </div>
              <div className="health-consistency-summary__item">
                <span className="health-consistency-summary__label">不一致项:</span>
                <span className="health-consistency-summary__value">{consistency.summary.total_inconsistencies}</span>
              </div>
            </div>
            {consistency.inconsistencies.length > 0 && (
              <div className="health-consistency-issues">
                <h3 className="health-consistency-issues__title">不一致项详情:</h3>
                {consistency.inconsistencies.map((item, idx) => (
                  <div key={idx} className="health-consistency-issue">
                    <span className="health-consistency-issue__symbol">{item.symbol}</span>
                    <span className="health-consistency-issue__detail">{item.details}</span>
                  </div>
                ))}
              </div>
            )}
          </>
        )}
      </section>

      {/* Existing Aggregate Freshness Sections */}
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
                    {src.sector_count != null && ` / ${src.sector_count} 板块`}
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
