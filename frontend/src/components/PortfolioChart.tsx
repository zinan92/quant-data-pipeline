import { useMemo } from "react";
import ReactECharts from "echarts-for-react";
import { useQuery } from "@tanstack/react-query";
import { apiFetch, REFRESH_INTERVALS } from "../utils/api";

interface PortfolioHistory {
  dates: string[];
  absolute_values: number[];
  normalized_values: number[];
  initial_investment: number;
  current_value: number;
  total_return: number;
  return_pct: number;
  stock_count: number;
}

async function fetchPortfolioHistory(): Promise<PortfolioHistory> {
  const response = await apiFetch("/api/watchlist/portfolio/history");
  if (!response.ok) {
    throw new Error("Failed to fetch portfolio history");
  }
  return response.json();
}

export function PortfolioChart() {
  const { data, isLoading, error } = useQuery({
    queryKey: ["portfolio-history"],
    queryFn: fetchPortfolioHistory,
    staleTime: REFRESH_INTERVALS.portfolio,
    refetchInterval: REFRESH_INTERVALS.portfolio
  });

  const option = useMemo(() => {
    if (!data || data.dates.length === 0) {
      return null;
    }

    return {
      backgroundColor: "transparent",
      tooltip: {
        trigger: "axis",
        axisPointer: { type: "cross" },
        formatter: (params: any) => {
          const date = params[0].axisValue;
          const value = params[0].value;
          return `<div style="font-size: 12px;"><strong>${date}</strong><br/>净值: ${value.toFixed(4)}</div>`;
        }
      },
      grid: {
        left: 45,
        right: 15,
        top: 10,
        bottom: 25
      },
      xAxis: {
        type: "category",
        data: data.dates,
        axisLabel: {
          color: "#8f9bbd",
          fontSize: 10,
          interval: Math.floor(data.dates.length / 5)
        },
        axisLine: { lineStyle: { color: "#55617d" } }
      },
      yAxis: {
        type: "value",
        axisLabel: {
          color: "#8f9bbd",
          fontSize: 10,
          formatter: (value: number) => value.toFixed(2)
        },
        splitLine: { lineStyle: { color: "rgba(255,255,255,0.05)" } }
      },
      series: [
        {
          type: "line",
          data: data.normalized_values,
          smooth: true,
          symbol: "none",
          lineStyle: { color: "#5fb0ff", width: 2 },
          areaStyle: {
            color: {
              type: "linear",
              x: 0, y: 0, x2: 0, y2: 1,
              colorStops: [
                { offset: 0, color: "rgba(95, 176, 255, 0.3)" },
                { offset: 1, color: "rgba(95, 176, 255, 0.05)" }
              ]
            }
          },
          markLine: {
            silent: true,
            symbol: "none",
            lineStyle: { color: "#8f9bbd", type: "dashed" },
            data: [{ yAxis: 1.0 }]
          }
        }
      ]
    };
  }, [data]);

  if (isLoading) {
    return <div className="portfolio-compact__loading">加载中...</div>;
  }

  if (error || !data || data.stock_count === 0) {
    return null;
  }

  const isProfit = data.total_return >= 0;

  return (
    <div className="portfolio-compact">
      <div className="portfolio-compact__header">
        <div className="portfolio-compact__title">投资组合</div>
        <div className="portfolio-compact__stats">
          <span className="portfolio-compact__stat">
            <span className="portfolio-compact__stat-label">持仓</span>
            <span className="portfolio-compact__stat-value">{data.stock_count}只</span>
          </span>
          <span className="portfolio-compact__stat">
            <span className="portfolio-compact__stat-label">投资</span>
            <span className="portfolio-compact__stat-value">¥{(data.initial_investment / 10000).toFixed(1)}万</span>
          </span>
          <span className="portfolio-compact__stat">
            <span className="portfolio-compact__stat-label">市值</span>
            <span className="portfolio-compact__stat-value">¥{(data.current_value / 10000).toFixed(2)}万</span>
          </span>
          <span className="portfolio-compact__stat">
            <span className="portfolio-compact__stat-label">收益</span>
            <span className={`portfolio-compact__stat-value portfolio-compact__stat-value--${isProfit ? 'profit' : 'loss'}`}>
              {isProfit ? '+' : ''}{data.return_pct.toFixed(2)}%
            </span>
          </span>
        </div>
      </div>
      {option && (
        <ReactECharts
          option={option}
          style={{ height: "120px", width: "100%" }}
          notMerge={true}
          lazyUpdate={true}
        />
      )}
    </div>
  );
}
