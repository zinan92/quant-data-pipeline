import { UIEvent, useEffect, useMemo, useState } from "react";
import { useQuery } from "@tanstack/react-query";
import type { MAConfig } from "../types/chartConfig";
import { MA_COLORS } from "../types/chartConfig";
import { WatchlistCard } from "./WatchlistCard";
import { useRealtimePrice } from "../hooks/useRealtimePrice";
import { StockFilterControls, FilterOptions } from "./StockFilterControls";
import { UpdateTimeIndicator } from "./UpdateTimeIndicator";
import { apiFetch, REFRESH_INTERVALS } from "../utils/api";

interface StockInfo {
  ticker: string;
  name: string;
  industryLv1: string | null;
  totalMv: number | null;
  circMv: number | null;
  peTtm: number | null;
  pb: number | null;
}

interface ConceptStocksResponse {
  concept: string;
  code: string;
  stocks: StockInfo[];
  total: number;
}

interface Props {
  conceptName: string;
  conceptCode: string;
  maConfig: MAConfig;
  onMAConfigChange: (config: MAConfig) => void;
  klineLimit?: number;
}

export function ConceptDetailView({ conceptName, conceptCode, maConfig, onMAConfigChange, klineLimit = 120 }: Props) {
  const [visibleCount, setVisibleCount] = useState(30);
  const [filterOptions, setFilterOptions] = useState<FilterOptions>({
    sortBy: "default",
    direction: "all",
    peMin: 0,
    peMax: 1000,
    focusOnly: false,
    mvMin: 0,
    mvMax: 100000
  });

  const { data: conceptStocks, isLoading } = useQuery({
    queryKey: ["concept-stocks", conceptName],
    queryFn: async (): Promise<ConceptStocksResponse> => {
      const response = await apiFetch(`/api/concepts/${encodeURIComponent(conceptName)}/stocks`);
      if (!response.ok) {
        throw new Error("Failed to load concept stocks");
      }
      return response.json();
    },
    staleTime: REFRESH_INTERVALS.boards,
    refetchInterval: REFRESH_INTERVALS.boards
  });

  useEffect(() => {
    // Reset to first batch whenever concept changes
    setVisibleCount(30);
  }, [conceptName]);

  // Get real-time prices for change calculations
  // 注意：实时价格API使用6位代码（无后缀），需要转换
  const tickersWithSuffix = useMemo(() => conceptStocks?.stocks?.map(s => s.ticker) ?? [], [conceptStocks]);
  const tickersWithoutSuffix = useMemo(() => tickersWithSuffix.map(t => t.split('.')[0]), [tickersWithSuffix]);

  const rawRealtimePrices = useRealtimePrice({
    tickers: tickersWithoutSuffix,
    interval: 60000,
    enabled: true
  });

  // 将6位代码的价格映射回带后缀的ticker
  const realtimePrices = useMemo(() => {
    const result = new Map();
    for (const tickerFull of tickersWithSuffix) {
      const tickerRaw = tickerFull.split('.')[0];
      const price = rawRealtimePrices.get(tickerRaw);
      if (price) {
        result.set(tickerFull, { ...price, ticker: tickerFull });
      }
    }
    return result;
  }, [tickersWithSuffix, rawRealtimePrices]);

  // 检查实时价格数据是否已加载
  const hasRealtimeData = realtimePrices.size > 0;

  // Apply filters and sorting
  const filteredSymbols = useMemo(() => {
    let result = [...(conceptStocks?.stocks ?? [])];

    // 只有在有实时数据时才进行涨跌筛选
    if (hasRealtimeData) {
      if (filterOptions.direction === "up") {
        result = result.filter(s => {
          const price = realtimePrices.get(s.ticker);
          return price ? price.change >= 0 : true;
        });
      } else if (filterOptions.direction === "down") {
        result = result.filter(s => {
          const price = realtimePrices.get(s.ticker);
          return price ? price.change < 0 : true;
        });
      }
    }

    // 市值筛选（输入为亿元，totalMv为万元，1亿=10000万）
    if (filterOptions.mvMin > 0 || filterOptions.mvMax < 100000) {
      const mvMinWan = filterOptions.mvMin * 10000;
      const mvMaxWan = filterOptions.mvMax * 10000;
      result = result.filter(s => {
        const mv = s.totalMv;
        if (mv === null || mv === undefined) return true;
        return mv >= mvMinWan && mv <= mvMaxWan;
      });
    }

    // Filter by PE range
    if (filterOptions.peMin > 0 || filterOptions.peMax < 1000) {
      result = result.filter(s => {
        const pe = s.peTtm;
        if (pe === null) return false;
        return pe >= filterOptions.peMin && pe <= filterOptions.peMax;
      });
    }

    // Sort
    switch (filterOptions.sortBy) {
      case "change_desc":
        result.sort((a, b) => {
          const priceA = realtimePrices.get(a.ticker);
          const priceB = realtimePrices.get(b.ticker);
          if (!priceA && !priceB) return 0;
          if (!priceA) return 1;
          if (!priceB) return -1;
          return priceB.changePercent - priceA.changePercent;
        });
        break;
      case "change_asc":
        result.sort((a, b) => {
          const priceA = realtimePrices.get(a.ticker);
          const priceB = realtimePrices.get(b.ticker);
          if (!priceA && !priceB) return 0;
          if (!priceA) return 1;
          if (!priceB) return -1;
          return priceA.changePercent - priceB.changePercent;
        });
        break;
      case "mv_desc":
        result.sort((a, b) => (b.totalMv ?? 0) - (a.totalMv ?? 0));
        break;
      case "mv_asc":
        result.sort((a, b) => (a.totalMv ?? 0) - (b.totalMv ?? 0));
        break;
      case "pe_desc":
        result.sort((a, b) => (b.peTtm ?? 0) - (a.peTtm ?? 0));
        break;
      case "pe_asc":
        result.sort((a, b) => (a.peTtm ?? 0) - (b.peTtm ?? 0));
        break;
      default:
        // default: by market cap (total MV)
        result.sort((a, b) => (b.totalMv ?? 0) - (a.totalMv ?? 0));
    }

    return result;
  }, [conceptStocks, filterOptions, realtimePrices, hasRealtimeData]);

  const items = useMemo(
    () => filteredSymbols.slice(0, visibleCount),
    [filteredSymbols, visibleCount]
  );

  if (isLoading || !conceptStocks) {
    return <div className="chart-grid__placeholder">加载概念板块成分股...</div>;
  }

  // Convert StockInfo to SymbolMeta format for WatchlistCard
  const symbolMetaItems = items.map(s => ({
    ticker: s.ticker.split('.')[0],  // WatchlistCard expects ticker without suffix
    name: s.name,
    industryLv1: s.industryLv1,
    industryLv2: null,
    industryLv3: null,
    totalMv: s.totalMv,
    circMv: s.circMv,
    peTtm: s.peTtm,
    pb: s.pb,
    listDate: null,
    superCategory: null,
    concepts: [conceptName],
    introduction: null,
    mainBusiness: null,
    businessScope: null,
    chairman: null,
    manager: null,
    regCapital: null,
    setupDate: null,
    province: null,
    city: null,
    website: null,
    lastUpdated: new Date().toISOString(),
    eastmoneyBoard: []
  }));

  function handleScroll(event: UIEvent<HTMLDivElement>) {
    const target = event.currentTarget;
    const isNearBottom =
      target.scrollTop + target.clientHeight >= target.scrollHeight - 200;
    if (isNearBottom) {
      setVisibleCount((prev) => Math.min(prev + 15, filteredSymbols.length));
    }
  }

  return (
    <>
      <div className="concept-detail__header">
        <h2 className="concept-detail__title">{conceptName}</h2>
        <span className="concept-detail__code">代码: {conceptCode}</span>
        <span className="concept-detail__count">共 {conceptStocks.total} 只成分股</span>
        <div className="concept-detail__ma-buttons">
          {(["ma5", "ma10", "ma20", "ma50"] as const).map((key) => (
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
      <StockFilterControls
        options={filterOptions}
        onChange={setFilterOptions}
        totalCount={conceptStocks.stocks.length}
        filteredCount={filteredSymbols.length}
      />
      <UpdateTimeIndicator section="concept" timeframe="both" />
      <div className="watchlist-grid" onScroll={handleScroll}>
        {symbolMetaItems.map((symbol, index) => (
          <WatchlistCard
            key={symbol.ticker}
            symbol={symbol}
            maConfig={maConfig}
            realtimePrice={rawRealtimePrices.get(symbol.ticker)}
            klineLimit={klineLimit}
          />
        ))}
      </div>
    </>
  );
}
