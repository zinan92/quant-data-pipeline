import { UIEvent, useEffect, useMemo, useState } from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import type { SymbolMeta } from "../types/symbol";
import type { MAConfig } from "../types/chartConfig";
import { MA_COLORS } from "../types/chartConfig";
import { WatchlistCard } from "./WatchlistCard";
import { useRealtimePrice } from "../hooks/useRealtimePrice";
import { StockFilterControls, FilterOptions } from "./StockFilterControls";
import { SectorSummaryPanel } from "./SectorSummaryPanel";
import { UpdateTimeIndicator } from "./UpdateTimeIndicator";
import { ManageSectorsDialog } from "./ManageSectorsDialog";
import { apiFetch, REFRESH_INTERVALS, buildApiUrl } from "../utils/api";
import "./ManageSectorsDialog.css";

// 涨跌幅分布区间
interface DistributionBucket {
  label: string;
  count: number;
  color: string;
}

// 获取大盘指数实时行情
async function fetchIndexPrice(indexCode: string): Promise<{ changePercent: number } | null> {
  try {
    const url = buildApiUrl(`/api/realtime/prices?tickers=${indexCode}`);
    const response = await fetch(url);
    if (!response.ok) return null;
    const json = await response.json();

    // 解析新浪数据
    const match = json.data.match(/var hq_str_[^=]+="([^"]+)"/);
    if (!match) return null;
    const data = match[1].split(',');
    if (data.length < 4) return null;

    const currentPrice = parseFloat(data[3]);
    const prevClose = parseFloat(data[2]);
    if (currentPrice === 0) return { changePercent: 0 }; // 休市
    return { changePercent: ((currentPrice - prevClose) / prevClose) * 100 };
  } catch {
    return null;
  }
}


interface Props {
  maConfig: MAConfig;
  onMAConfigChange: (config: MAConfig) => void;
  onPortfolioClick?: () => void;
}

async function fetchWatchlist(): Promise<SymbolMeta[]> {
  const response = await apiFetch("/api/watchlist");
  if (!response.ok) {
    throw new Error("Failed to fetch watchlist");
  }
  return response.json();
}

export function WatchlistView({ maConfig, onMAConfigChange, onPortfolioClick }: Props) {
  const [visibleCount, setVisibleCount] = useState(30);
  const [isClearing, setIsClearing] = useState(false);
  const [klineLimit, setKlineLimit] = useState(120);
  const [filterOptions, setFilterOptions] = useState<FilterOptions>({
    sortBy: "default",
    direction: "all",
    peMin: 0,
    peMax: 1000,
    mvMin: 0,
    mvMax: 100000,
    focusOnly: false
  });
  const [selectedSectors, setSelectedSectors] = useState<Set<string>>(new Set());
  const [showManageSectorsDialog, setShowManageSectorsDialog] = useState(false);
  const queryClient = useQueryClient();

  // 处理赛道点击
  const handleSectorClick = (sector: string) => {
    setSelectedSectors(prev => {
      const newSet = new Set(prev);
      if (newSet.has(sector)) {
        newSet.delete(sector);
      } else {
        newSet.add(sector);
      }
      return newSet;
    });
    setVisibleCount(30); // 重置可见数量
  };

  const { data: symbols, isLoading, error } = useQuery({
    queryKey: ["watchlist"],
    queryFn: fetchWatchlist,
    staleTime: REFRESH_INTERVALS.watchlist,
    refetchInterval: REFRESH_INTERVALS.watchlist
  });

  // Get tickers for real-time price fetching (extract just the ticker code without exchange suffix)
  const tickers = useMemo(() => symbols?.map(s => s.ticker.split('.')[0]) ?? [], [symbols]);

  // 获取所有股票的赛道分类
  const { data: sectorsData } = useQuery({
    queryKey: ["sectors-all"],
    queryFn: async () => {
      const response = await apiFetch("/api/sectors/");
      if (!response.ok) return { sectors: {} };
      return response.json();
    },
    staleTime: 1000 * 60 * 60, // 1小时缓存
  });

  const sectorsMap = useMemo(() => {
    return new Map<string, string>(Object.entries(sectorsData?.sectors ?? {}));
  }, [sectorsData]);

  const positioningMap = useMemo(() => {
    return new Map<string, string>(Object.entries(sectorsData?.positioning ?? {}));
  }, [sectorsData]);

  // 股票名称映射
  const stockNamesMap = useMemo(() => {
    const map = new Map<string, string>();
    for (const s of symbols ?? []) {
      map.set(s.ticker.split('.')[0], s.name);
    }
    return map;
  }, [symbols]);

  // Fetch real-time prices (only during market hours, 60s interval)
  const realtimePrices = useRealtimePrice({
    tickers,
    interval: 60000,
    enabled: true
  });


  // 获取上证指数实时行情
  const { data: shIndexData } = useQuery({
    queryKey: ["index-realtime", "sh000001"],
    queryFn: () => fetchIndexPrice("sh000001"),
    staleTime: 60000,
    refetchInterval: 60000
  });

  // 计算自选股平均收益和分布
  const { avgChange, distribution, validCount } = useMemo(() => {
    const changes: number[] = [];

    for (const symbol of symbols ?? []) {
      const tickerCode = symbol.ticker.split('.')[0];
      const price = realtimePrices.get(tickerCode);
      if (price && price.changePercent !== undefined) {
        changes.push(price.changePercent);
      }
    }

    // 平均收益
    const avgChange = changes.length > 0
      ? changes.reduce((a, b) => a + b, 0) / changes.length
      : 0;

    // 分布统计
    const buckets: DistributionBucket[] = [
      { label: ">5%", count: 0, color: "#d32f2f" },
      { label: "3~5%", count: 0, color: "#ef5350" },
      { label: "0~3%", count: 0, color: "#ffcdd2" },
      { label: "-3~0%", count: 0, color: "#c8e6c9" },
      { label: "-5~-3%", count: 0, color: "#66bb6a" },
      { label: "<-5%", count: 0, color: "#2e7d32" },
    ];

    for (const change of changes) {
      if (change > 5) buckets[0].count++;
      else if (change > 3) buckets[1].count++;
      else if (change >= 0) buckets[2].count++;
      else if (change >= -3) buckets[3].count++;
      else if (change >= -5) buckets[4].count++;
      else buckets[5].count++;
    }

    return { avgChange, distribution: buckets, validCount: changes.length };
  }, [symbols, realtimePrices]);

  // 计算重点关注股票的统计数据
  const focusStats = useMemo(() => {
    const focusSymbols = (symbols ?? []).filter(s => s.isFocus);
    const changes: number[] = [];

    for (const symbol of focusSymbols) {
      const tickerCode = symbol.ticker.split('.')[0];
      const price = realtimePrices.get(tickerCode);
      if (price && price.changePercent !== undefined) {
        changes.push(price.changePercent);
      }
    }

    // 平均收益
    const avgChange = changes.length > 0
      ? changes.reduce((a, b) => a + b, 0) / changes.length
      : 0;

    // 分布统计
    const buckets: DistributionBucket[] = [
      { label: ">5%", count: 0, color: "#d32f2f" },
      { label: "3~5%", count: 0, color: "#ef5350" },
      { label: "0~3%", count: 0, color: "#ffcdd2" },
      { label: "-3~0%", count: 0, color: "#c8e6c9" },
      { label: "-5~-3%", count: 0, color: "#66bb6a" },
      { label: "<-5%", count: 0, color: "#2e7d32" },
    ];

    for (const change of changes) {
      if (change > 5) buckets[0].count++;
      else if (change > 3) buckets[1].count++;
      else if (change >= 0) buckets[2].count++;
      else if (change >= -3) buckets[3].count++;
      else if (change >= -5) buckets[4].count++;
      else buckets[5].count++;
    }

    return {
      avgChange,
      distribution: buckets,
      validCount: changes.length,
      totalCount: focusSymbols.length
    };
  }, [symbols, realtimePrices]);

  useEffect(() => {
    setVisibleCount(30);
  }, [filterOptions]);

  // 过滤和排序逻辑
  const filteredSymbols = useMemo(() => {
    if (!symbols) return [];

    let filtered = symbols.filter((s) => {
      // 重点关注筛选
      if (filterOptions.focusOnly && !s.isFocus) return false;

      // 赛道筛选
      if (selectedSectors.size > 0) {
        const tickerCode = s.ticker.split('.')[0];
        const sector = sectorsMap.get(tickerCode);
        if (!sector || !selectedSectors.has(sector)) return false;
      }

      const mvInYi = (s.totalMv ?? 0) / 1e4;
      if (mvInYi < filterOptions.mvMin || mvInYi > filterOptions.mvMax) return false;

      const pe = s.peTtm ?? 0;
      if (pe < filterOptions.peMin || pe > filterOptions.peMax) return false;

      if (filterOptions.direction !== "all") {
        const tickerCode = s.ticker.split('.')[0];
        const price = realtimePrices.get(tickerCode);
        if (price) {
          if (filterOptions.direction === "up" && price.changePercent < 0) return false;
          if (filterOptions.direction === "down" && price.changePercent >= 0) return false;
        }
      }

      return true;
    });

    if (filterOptions.sortBy !== "default") {
      filtered = [...filtered].sort((a, b) => {
        switch (filterOptions.sortBy) {
          case "change_desc":
          case "change_asc": {
            const tickerCodeA = a.ticker.split('.')[0];
            const tickerCodeB = b.ticker.split('.')[0];
            const priceA = realtimePrices.get(tickerCodeA);
            const priceB = realtimePrices.get(tickerCodeB);
            const changeA = priceA?.changePercent ?? 0;
            const changeB = priceB?.changePercent ?? 0;
            return filterOptions.sortBy === "change_desc" ? changeB - changeA : changeA - changeB;
          }
          case "mv_desc":
            return (b.totalMv ?? 0) - (a.totalMv ?? 0);
          case "mv_asc":
            return (a.totalMv ?? 0) - (b.totalMv ?? 0);
          case "pe_desc":
            return (b.peTtm ?? 0) - (a.peTtm ?? 0);
          case "pe_asc":
            return (a.peTtm ?? 0) - (b.peTtm ?? 0);
          default:
            return 0;
        }
      });
    }

    return filtered;
  }, [symbols, filterOptions, realtimePrices, selectedSectors, sectorsMap]);

  const items = useMemo(
    () => filteredSymbols.slice(0, visibleCount),
    [filteredSymbols, visibleCount]
  );

  if (isLoading) {
    return <div className="chart-grid__placeholder">加载自选股...</div>;
  }

  if (error) {
    return <div className="chart-grid__placeholder">加载失败: {(error as Error).message}</div>;
  }

  if (!symbols || symbols.length === 0) {
    return <div className="chart-grid__placeholder">暂无自选股，点击K线图下方的"➕ 自选"按钮添加</div>;
  }

  async function handleClearAll() {
    if (!confirm(`确定要清空所有 ${symbols?.length} 只自选股吗？此操作不可撤销。`)) {
      return;
    }
    setIsClearing(true);
    try {
      const response = await apiFetch("/api/watchlist", { method: "DELETE" });
      if (response.ok) {
        queryClient.invalidateQueries({ queryKey: ["watchlist"] });
        queryClient.invalidateQueries({ queryKey: ["portfolio-history"] });
        queryClient.invalidateQueries({ predicate: (query) => query.queryKey[0] === "watchlist-check" });
      }
    } catch (e) {
      console.error("Failed to clear watchlist:", e);
    } finally {
      setIsClearing(false);
    }
  }

  function handleScroll(event: UIEvent<HTMLDivElement>) {
    const target = event.currentTarget;
    const isNearBottom =
      target.scrollTop + target.clientHeight >= target.scrollHeight - 200;
    if (isNearBottom && filteredSymbols.length > 0) {
      setVisibleCount((prev) => Math.min(prev + 15, filteredSymbols.length));
    }
  }

  const maxBucketCount = Math.max(...distribution.map(b => b.count), 1);
  const indexChange = shIndexData?.changePercent ?? 0;
  const outperformance = avgChange - indexChange;

  return (
    <>
      {/* 统计面板 + 赛道统计 */}
      <div className="watchlist-stats-row">
        <div className="watchlist-stats">
          <div className="watchlist-stats__distribution">
            <div className="watchlist-stats__chart">
              {distribution.map((bucket) => (
                <div key={bucket.label} className="watchlist-stats__bar-group">
                  <div className="watchlist-stats__bar-label">{bucket.label}</div>
                  <div className="watchlist-stats__bar-container">
                    <div
                      className="watchlist-stats__bar"
                      style={{
                        height: `${(bucket.count / maxBucketCount) * 100}%`,
                        backgroundColor: bucket.color,
                      }}
                    />
                    <span className="watchlist-stats__bar-count">{bucket.count}</span>
                  </div>
                </div>
              ))}
            </div>
          </div>
          <div className="watchlist-stats__summary">
            <div className="watchlist-stats__item">
              <span className="watchlist-stats__label">自选平均</span>
              <span className={`watchlist-stats__value ${avgChange >= 0 ? 'watchlist-stats__value--up' : 'watchlist-stats__value--down'}`}>
                {avgChange >= 0 ? '+' : ''}{avgChange.toFixed(2)}%
              </span>
            </div>
            <div className="watchlist-stats__item">
              <span className="watchlist-stats__label">上证指数</span>
              <span className={`watchlist-stats__value ${indexChange >= 0 ? 'watchlist-stats__value--up' : 'watchlist-stats__value--down'}`}>
                {indexChange >= 0 ? '+' : ''}{indexChange.toFixed(2)}%
              </span>
            </div>
            <div className="watchlist-stats__item">
              <span className="watchlist-stats__label">超额收益</span>
              <span className={`watchlist-stats__value ${outperformance >= 0 ? 'watchlist-stats__value--up' : 'watchlist-stats__value--down'}`}>
                {outperformance >= 0 ? '+' : ''}{outperformance.toFixed(2)}%
              </span>
            </div>
            <div className="watchlist-stats__item watchlist-stats__item--count">
              <span className="watchlist-stats__label">统计样本</span>
              <span className="watchlist-stats__value">
                {validCount} / {symbols?.length ?? 0} 只
                {validCount < (symbols?.length ?? 0) && (
                  <span className="watchlist-stats__hint" title="部分股票（如北交所）无法获取实时行情">
                    *
                  </span>
                )}
              </span>
            </div>
          </div>

          {/* 重点关注统计 - 集成在同一面板内 */}
          {focusStats.totalCount > 0 && (
            <>
              <div className="watchlist-stats__divider"></div>
              <div className="watchlist-stats__distribution">
                <div className="watchlist-stats__section-label">★ 重点关注</div>
                <div className="watchlist-stats__chart">
                  {focusStats.distribution.map((bucket) => (
                    <div key={bucket.label} className="watchlist-stats__bar-group">
                      <div className="watchlist-stats__bar-label">{bucket.label}</div>
                      <div className="watchlist-stats__bar-container">
                        <div
                          className="watchlist-stats__bar"
                          style={{
                            height: `${(bucket.count / Math.max(...focusStats.distribution.map(b => b.count), 1)) * 100}%`,
                            backgroundColor: bucket.color,
                          }}
                        />
                        <span className="watchlist-stats__bar-count">{bucket.count}</span>
                      </div>
                    </div>
                  ))}
                </div>
              </div>
              <div className="watchlist-stats__summary">
                <div className="watchlist-stats__item">
                  <span className="watchlist-stats__label">平均涨幅</span>
                  <span className={`watchlist-stats__value ${focusStats.avgChange >= 0 ? 'watchlist-stats__value--up' : 'watchlist-stats__value--down'}`}>
                    {focusStats.avgChange >= 0 ? '+' : ''}{focusStats.avgChange.toFixed(2)}%
                  </span>
                </div>
                <div className="watchlist-stats__item">
                  <span className="watchlist-stats__label">跑赢自选</span>
                  <span className={`watchlist-stats__value ${(focusStats.avgChange - avgChange) >= 0 ? 'watchlist-stats__value--up' : 'watchlist-stats__value--down'}`}>
                    {(focusStats.avgChange - avgChange) >= 0 ? '+' : ''}{(focusStats.avgChange - avgChange).toFixed(2)}%
                  </span>
                </div>
                <div className="watchlist-stats__item">
                  <span className="watchlist-stats__label">跑赢大盘</span>
                  <span className={`watchlist-stats__value ${(focusStats.avgChange - indexChange) >= 0 ? 'watchlist-stats__value--up' : 'watchlist-stats__value--down'}`}>
                    {(focusStats.avgChange - indexChange) >= 0 ? '+' : ''}{(focusStats.avgChange - indexChange).toFixed(2)}%
                  </span>
                </div>
                <div className="watchlist-stats__item watchlist-stats__item--count">
                  <span className="watchlist-stats__label">关注数量</span>
                  <span className="watchlist-stats__value">{focusStats.totalCount} 只</span>
                </div>
              </div>
            </>
          )}
        </div>
        <SectorSummaryPanel
          sectorsMap={sectorsMap}
          realtimePrices={realtimePrices}
          stockNames={stockNamesMap}
          selectedSectors={selectedSectors}
          onSectorClick={handleSectorClick}
        />
      </div>

      <div className="watchlist-header">
        <div className="watchlist-header__left">
          <button
            className="watchlist-header__clear-btn"
            onClick={handleClearAll}
            disabled={isClearing}
          >
            {isClearing ? "清空中..." : "清空自选"}
          </button>
          <button
            className="watchlist-header__manage-sectors-btn"
            onClick={() => setShowManageSectorsDialog(true)}
          >
            管理赛道
          </button>
          <div className="watchlist-header__ma-buttons">
            {(["ma5", "ma10", "ma20", "ma30", "ma50"] as const).map((key) => (
              <button
                key={key}
                className={`watchlist-header__ma-btn ${maConfig[key] ? "watchlist-header__ma-btn--active" : ""}`}
                style={{ borderColor: maConfig[key] ? MA_COLORS[key] : undefined }}
                onClick={() => onMAConfigChange({ ...maConfig, [key]: !maConfig[key] })}
              >
                <span className="watchlist-header__ma-dot" style={{ backgroundColor: MA_COLORS[key] }} />
                {key.toUpperCase()}
              </button>
            ))}
          </div>
        </div>
        <div className="watchlist-header__center">
          <div className="watchlist-header__kline-control">
            <span className="watchlist-header__kline-label">K线数量:</span>
            <input
              type="range"
              min="50"
              max="300"
              step="10"
              value={klineLimit}
              onChange={(e) => setKlineLimit(parseInt(e.target.value))}
              className="watchlist-header__kline-slider"
            />
            <span className="watchlist-header__kline-value">{klineLimit}</span>
          </div>
        </div>
        <div className="watchlist-header__right">
          {onPortfolioClick && (
            <button
              className="watchlist-header__nav-btn"
              onClick={onPortfolioClick}
            >
              持仓
            </button>
          )}
        </div>
      </div>
      <StockFilterControls
        options={filterOptions}
        onChange={setFilterOptions}
        totalCount={symbols.length}
        filteredCount={filteredSymbols.length}
      />
      <UpdateTimeIndicator section="watchlist" timeframe="both" />
      <div className="watchlist-grid" onScroll={handleScroll}>
        {items.map((symbol) => {
          const tickerCode = symbol.ticker.split('.')[0];
          const price = realtimePrices.get(tickerCode);

          return (
            <WatchlistCard
              key={symbol.ticker}
              symbol={symbol}
              maConfig={maConfig}
              realtimePrice={price}
              klineLimit={klineLimit}
              sector={sectorsMap.get(tickerCode)}
              positioning={positioningMap.get(tickerCode)}
              onSectorChange={() => {
                queryClient.invalidateQueries({ queryKey: ["sectors-all"] });
              }}
            />
          );
        })}
      </div>

      <ManageSectorsDialog
        isOpen={showManageSectorsDialog}
        onClose={() => setShowManageSectorsDialog(false)}
      />
    </>
  );
}
