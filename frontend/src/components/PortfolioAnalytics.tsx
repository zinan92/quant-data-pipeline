import { useMemo } from "react";
import ReactECharts from "echarts-for-react";
import { useQuery } from "@tanstack/react-query";
import { apiFetch, REFRESH_INTERVALS } from "../utils/api";

interface AnalyticsData {
  overview: {
    total_stocks: number;
    up_count: number;
    down_count: number;
    flat_count: number;
    up_pct: number;
    down_pct: number;
  };
  industry_allocation: Array<{
    name: string;
    market_value: number;
    count: number;
    percentage: number;
  }>;
  industry_performance: Array<{
    name: string;
    return_pct: number;
    count: number;
    profit: number;
  }>;
  top_gainers: Array<{
    ticker: string;
    name: string;
    industry: string;
    profit_pct: number;
    profit: number;
    current_price: number;
  }>;
  top_losers: Array<{
    ticker: string;
    name: string;
    industry: string;
    profit_pct: number;
    profit: number;
    current_price: number;
  }>;
  style_allocation: Array<{
    style: string;
    market_value: number;
    percentage: number;
  }>;
  profit_distribution: Array<{
    range: string;
    count: number;
  }>;
  market_value_tree: Array<{
    name: string;
    value: number;
    children: Array<{
      name: string;
      value: number;
      profit_pct: number;
    }>;
  }>;
}

async function fetchAnalytics(): Promise<AnalyticsData> {
  const response = await apiFetch("/api/watchlist/analytics");
  if (!response.ok) {
    throw new Error("Failed to fetch analytics");
  }
  return response.json();
}

export function PortfolioAnalytics() {
  const { data, isLoading, error } = useQuery({
    queryKey: ["watchlist-analytics"],
    queryFn: fetchAnalytics,
    staleTime: REFRESH_INTERVALS.portfolio,
    refetchInterval: REFRESH_INTERVALS.portfolio
  });

  const industryPieOption = useMemo(() => {
    if (!data || data.industry_allocation.length === 0) return null;

    return {
      backgroundColor: "transparent",
      tooltip: {
        trigger: "item",
        formatter: (params: any) => `${params.name}: ${params.percent.toFixed(1)}%`
      },
      legend: {
        type: "scroll",
        orient: "vertical",
        right: 5,
        top: 5,
        bottom: 5,
        textStyle: { color: "#b8c2e1", fontSize: 10 },
        itemWidth: 10,
        itemHeight: 10
      },
      series: [{
        type: "pie",
        radius: ["35%", "65%"],
        center: ["35%", "50%"],
        itemStyle: { borderRadius: 4, borderColor: "#12182a", borderWidth: 1 },
        label: { show: false },
        data: data.industry_allocation.slice(0, 8).map((item) => ({
          value: item.market_value,
          name: item.name
        }))
      }]
    };
  }, [data]);

  const industryPerformanceOption = useMemo(() => {
    if (!data || data.industry_performance.length === 0) return null;
    const top8 = data.industry_performance.slice(0, 8);

    return {
      backgroundColor: "transparent",
      tooltip: {
        trigger: "axis",
        formatter: (params: any) => `${params[0].name}: ${params[0].value >= 0 ? "+" : ""}${params[0].value.toFixed(2)}%`
      },
      grid: { left: 5, right: 35, top: 5, bottom: 5, containLabel: true },
      xAxis: {
        type: "value",
        axisLabel: { color: "#8f9bbd", fontSize: 9, formatter: (v: number) => v.toFixed(0) + "%" },
        splitLine: { lineStyle: { color: "rgba(255,255,255,0.05)" } }
      },
      yAxis: {
        type: "category",
        data: top8.map((item) => item.name),
        axisLabel: { color: "#8f9bbd", fontSize: 9 },
        axisLine: { lineStyle: { color: "#55617d" } }
      },
      series: [{
        type: "bar",
        data: top8.map((item) => ({
          value: item.return_pct,
          itemStyle: { color: item.return_pct >= 0 ? "#23c19f" : "#ef5f7c" }
        })),
        barWidth: "50%",
        label: {
          show: true,
          position: "right",
          formatter: (p: any) => (p.value >= 0 ? "+" : "") + p.value.toFixed(1) + "%",
          color: "#e6edf7",
          fontSize: 9
        }
      }]
    };
  }, [data]);

  const profitDistributionOption = useMemo(() => {
    if (!data || data.profit_distribution.length === 0) return null;

    return {
      backgroundColor: "transparent",
      tooltip: { trigger: "axis" },
      grid: { left: 5, right: 5, top: 15, bottom: 5, containLabel: true },
      xAxis: {
        type: "category",
        data: data.profit_distribution.map((item) => item.range),
        axisLabel: { color: "#8f9bbd", fontSize: 8, rotate: 25 },
        axisLine: { lineStyle: { color: "#55617d" } }
      },
      yAxis: {
        type: "value",
        axisLabel: { color: "#8f9bbd", fontSize: 9 },
        splitLine: { lineStyle: { color: "rgba(255,255,255,0.05)" } }
      },
      series: [{
        type: "bar",
        data: data.profit_distribution.map((item, index) => ({
          value: item.count,
          itemStyle: { color: index < 3 ? "#ef5f7c" : "#23c19f" }
        })),
        barWidth: "50%",
        label: { show: true, position: "top", color: "#e6edf7", fontSize: 10 }
      }]
    };
  }, [data]);

  const treemapOption = useMemo(() => {
    if (!data || data.market_value_tree.length === 0) return null;

    return {
      backgroundColor: "transparent",
      tooltip: {
        formatter: (params: any) => {
          if (params.treePathInfo.length === 2) {
            return `${params.name}: ¥${(params.value / 10000).toFixed(1)}万`;
          }
          return `${params.name}: ${params.data.profit_pct >= 0 ? "+" : ""}${params.data.profit_pct.toFixed(1)}%`;
        }
      },
      series: [{
        type: "treemap",
        width: "100%",
        height: "100%",
        roam: false,
        nodeClick: false,
        breadcrumb: { show: false },
        label: {
          show: true,
          formatter: (params: any) => params.name,
          fontSize: 10,
          color: "#e6edf7"
        },
        itemStyle: { borderColor: "#12182a", borderWidth: 1, gapWidth: 1 },
        levels: [
          { itemStyle: { borderWidth: 0, gapWidth: 2 } },
          { itemStyle: { borderWidth: 2, gapWidth: 1 } },
          { colorSaturation: [0.35, 0.5], itemStyle: { borderWidth: 2, gapWidth: 1 } }
        ],
        data: data.market_value_tree
      }]
    };
  }, [data]);

  if (isLoading) return <div className="portfolio-analytics-compact__loading">加载中...</div>;
  if (error || !data || data.overview.total_stocks === 0) return null;

  return (
    <div className="portfolio-analytics-compact">
      {/* Stats Row */}
      <div className="analytics-compact-stats">
        <div className="analytics-compact-stats__item">
          <span className="analytics-compact-stats__value">{data.overview.total_stocks}</span>
          <span className="analytics-compact-stats__label">总数</span>
        </div>
        <div className="analytics-compact-stats__item analytics-compact-stats__item--profit">
          <span className="analytics-compact-stats__value">{data.overview.up_count}</span>
          <span className="analytics-compact-stats__label">盈利 ({data.overview.up_pct}%)</span>
        </div>
        <div className="analytics-compact-stats__item analytics-compact-stats__item--loss">
          <span className="analytics-compact-stats__value">{data.overview.down_count}</span>
          <span className="analytics-compact-stats__label">亏损 ({data.overview.down_pct}%)</span>
        </div>
      </div>

      {/* Charts Grid - 3 columns */}
      <div className="analytics-compact-grid">
        {/* Industry Pie */}
        <div className="analytics-compact-card">
          <div className="analytics-compact-card__title">行业配置</div>
          {industryPieOption && (
            <ReactECharts option={industryPieOption} style={{ height: "140px" }} notMerge lazyUpdate />
          )}
        </div>

        {/* Industry Performance */}
        <div className="analytics-compact-card">
          <div className="analytics-compact-card__title">行业表现</div>
          {industryPerformanceOption && (
            <ReactECharts option={industryPerformanceOption} style={{ height: "140px" }} notMerge lazyUpdate />
          )}
        </div>

        {/* Profit Distribution */}
        <div className="analytics-compact-card">
          <div className="analytics-compact-card__title">收益分布</div>
          {profitDistributionOption && (
            <ReactECharts option={profitDistributionOption} style={{ height: "140px" }} notMerge lazyUpdate />
          )}
        </div>

        {/* Top Gainers */}
        <div className="analytics-compact-card">
          <div className="analytics-compact-card__title">涨幅榜</div>
          <div className="analytics-compact-list">
            {data.top_gainers.slice(0, 4).map((stock, i) => (
              <div key={stock.ticker} className="analytics-compact-list__item">
                <span className="analytics-compact-list__rank">{i + 1}</span>
                <span className="analytics-compact-list__name">{stock.name}</span>
                <span className="analytics-compact-list__value analytics-compact-list__value--profit">
                  +{stock.profit_pct.toFixed(1)}%
                </span>
              </div>
            ))}
          </div>
        </div>

        {/* Top Losers */}
        <div className="analytics-compact-card">
          <div className="analytics-compact-card__title">跌幅榜</div>
          <div className="analytics-compact-list">
            {data.top_losers.slice(0, 4).map((stock, i) => (
              <div key={stock.ticker} className="analytics-compact-list__item">
                <span className="analytics-compact-list__rank">{i + 1}</span>
                <span className="analytics-compact-list__name">{stock.name}</span>
                <span className="analytics-compact-list__value analytics-compact-list__value--loss">
                  {stock.profit_pct.toFixed(1)}%
                </span>
              </div>
            ))}
          </div>
        </div>

        {/* Treemap */}
        <div className="analytics-compact-card">
          <div className="analytics-compact-card__title">市值分布</div>
          {treemapOption && (
            <ReactECharts option={treemapOption} style={{ height: "140px" }} notMerge lazyUpdate />
          )}
        </div>
      </div>
    </div>
  );
}
