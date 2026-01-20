import { UIEvent, useEffect, useMemo, useState } from "react";
import { useQuery } from "@tanstack/react-query";
import type { Timeframe } from "../types/timeframe";
import type { MAConfig } from "../types/chartConfig";
import { CandleCard } from "./CandleCard";
import { useRealtimePrice } from "../hooks/useRealtimePrice";
import { StockFilterControls, FilterOptions } from "./StockFilterControls";
import { apiFetch, REFRESH_INTERVALS } from "../utils/api";
import type { SymbolMeta } from "../types/symbol";

interface Props {
  trackName: string;
  timeframe: Timeframe;
  maConfig: MAConfig;
  onStockClick: (ticker: string) => void;
}

export function TrackChartGrid({ trackName, timeframe, maConfig, onStockClick }: Props) {
  const [visibleCount, setVisibleCount] = useState(60);
  const [filterOptions, setFilterOptions] = useState<FilterOptions>({
    sortBy: "default",
    direction: "all",
    peMin: 0,
    peMax: 1000,
    focusOnly: false,
    mvMin: 0,
    mvMax: 100000
  });

  const { data: trackSymbols } = useQuery({
    queryKey: ["track-symbols", trackName],
    queryFn: async (): Promise<SymbolMeta[]> => {
      const response = await apiFetch(`/api/tracks/${encodeURIComponent(trackName)}/symbols`);
      if (!response.ok) {
        throw new Error("Failed to load track symbols");
      }
      return response.json();
    },
    staleTime: REFRESH_INTERVALS.boards,
    refetchInterval: REFRESH_INTERVALS.boards
  });

  useEffect(() => {
    setVisibleCount(60);
  }, [timeframe, trackName]);

  const tickers = useMemo(() => trackSymbols?.map(s => s.ticker) ?? [], [trackSymbols]);
  const realtimePrices = useRealtimePrice({
    tickers,
    interval: 60000,
    enabled: true
  });

  // 检查实时价格数据是否已加载
  const hasRealtimeData = realtimePrices.size > 0;

  // Debug: 记录实时价格加载状态
  useEffect(() => {
    console.log(`[TrackChartGrid] 股票数量: ${tickers.length}, 实时价格数量: ${realtimePrices.size}`);
    if (realtimePrices.size > 0) {
      // 显示前3个价格作为样本
      let count = 0;
      for (const [ticker, price] of realtimePrices) {
        if (count < 3) {
          console.log(`  ${ticker}: ${price.changePercent >= 0 ? '+' : ''}${price.changePercent.toFixed(2)}%`);
          count++;
        }
      }
    }
  }, [tickers.length, realtimePrices.size]);

  const filteredSymbols = useMemo(() => {
    let result = [...(trackSymbols ?? [])];

    // 只有在有实时数据时才进行涨跌筛选
    if (hasRealtimeData) {
      if (filterOptions.direction === "up") {
        result = result.filter(s => {
          const price = realtimePrices.get(s.ticker);
          return price ? price.change >= 0 : true; // 没有价格数据的保留显示
        });
      } else if (filterOptions.direction === "down") {
        result = result.filter(s => {
          const price = realtimePrices.get(s.ticker);
          return price ? price.change < 0 : true; // 没有价格数据的保留显示
        });
      }
    }

    // 市值筛选（输入为亿元，totalMv为万元，1亿=10000万）
    if (filterOptions.mvMin > 0 || filterOptions.mvMax < 100000) {
      const mvMinWan = filterOptions.mvMin * 10000; // 转换为万元
      const mvMaxWan = filterOptions.mvMax * 10000;
      result = result.filter(s => {
        const mv = s.totalMv;
        // 没有市值数据的股票保留显示
        if (mv === null || mv === undefined) return true;
        return mv >= mvMinWan && mv <= mvMaxWan;
      });
    }

    // PE筛选
    if (filterOptions.peMin > 0 || filterOptions.peMax < 1000) {
      result = result.filter(s => {
        const pe = s.peTtm;
        if (pe === null) return false;
        return pe >= filterOptions.peMin && pe <= filterOptions.peMax;
      });
    }

    switch (filterOptions.sortBy) {
      case "change_desc":
        result.sort((a, b) => {
          const priceA = realtimePrices.get(a.ticker);
          const priceB = realtimePrices.get(b.ticker);
          // 没有价格数据的排在最后
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
          // 没有价格数据的排在最后
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
        result.sort((a, b) => (b.totalMv ?? 0) - (a.totalMv ?? 0));
    }

    return result;
  }, [trackSymbols, filterOptions, realtimePrices, hasRealtimeData]);

  const items = useMemo(
    () => filteredSymbols.slice(0, visibleCount),
    [filteredSymbols, visibleCount]
  );

  if (!trackSymbols) {
    return <div className="chart-grid__placeholder">加载赛道成分股...</div>;
  }

  return (
    <>
      <StockFilterControls
        options={filterOptions}
        onChange={setFilterOptions}
        totalCount={trackSymbols.length}
        filteredCount={filteredSymbols.length}
      />
      <div className="chart-grid" onScroll={handleScroll}>
        {items.map((symbol) => (
          <CandleCard
            key={symbol.ticker}
            symbol={symbol}
            timeframe={timeframe}
            maConfig={maConfig}
            onStockClick={onStockClick}
            realtimePrice={realtimePrices.get(symbol.ticker)}
          />
        ))}
      </div>
    </>
  );

  function handleScroll(event: UIEvent<HTMLDivElement>) {
    const target = event.currentTarget;
    const isNearBottom =
      target.scrollTop + target.clientHeight >= target.scrollHeight - 200;
    if (isNearBottom) {
      setVisibleCount((prev) => Math.min(prev + 30, filteredSymbols.length));
    }
  }
}
