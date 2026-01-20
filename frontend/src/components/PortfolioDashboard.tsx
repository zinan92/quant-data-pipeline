import { useMemo } from "react";
import ReactECharts from "echarts-for-react";
import { useQuery } from "@tanstack/react-query";
import { apiFetch, REFRESH_INTERVALS } from "../utils/api";

interface PortfolioHistory {
  dates: string[];
  normalized_values: number[];
  initial_investment: number;
  current_value: number;
  total_return: number;
  return_pct: number;
  stock_count: number;
}

interface AnalyticsData {
  overview: {
    total_stocks: number;
    up_count: number;
    down_count: number;
    up_pct: number;
    down_pct: number;
  };
  industry_allocation: Array<{
    name: string;
    market_value: number;
    count: number;
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
    profit_pct: number;
  }>;
  top_losers: Array<{
    ticker: string;
    name: string;
    profit_pct: number;
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

async function fetchPortfolioHistory(): Promise<PortfolioHistory> {
  const response = await apiFetch("/api/watchlist/portfolio/history");
  if (!response.ok) throw new Error("Failed to fetch");
  return response.json();
}

async function fetchAnalytics(): Promise<AnalyticsData> {
  const response = await apiFetch("/api/watchlist/analytics");
  if (!response.ok) throw new Error("Failed to fetch");
  return response.json();
}

export function PortfolioDashboard() {
  const { data: portfolio } = useQuery({
    queryKey: ["portfolio-history"],
    queryFn: fetchPortfolioHistory,
    staleTime: REFRESH_INTERVALS.portfolio,
    refetchInterval: REFRESH_INTERVALS.portfolio
  });

  const { data: analytics } = useQuery({
    queryKey: ["watchlist-analytics"],
    queryFn: fetchAnalytics,
    staleTime: REFRESH_INTERVALS.portfolio,
    refetchInterval: REFRESH_INTERVALS.portfolio
  });

  // Portfolio Net Value Chart
  const portfolioOption = useMemo(() => {
    if (!portfolio || portfolio.dates.length === 0) return null;
    return {
      backgroundColor: "transparent",
      tooltip: {
        trigger: "axis",
        formatter: (params: any) => `${params[0].axisValue}<br/>净值: ${params[0].value.toFixed(4)}`
      },
      grid: { left: 40, right: 10, top: 10, bottom: 25 },
      xAxis: {
        type: "category",
        data: portfolio.dates,
        axisLabel: { color: "#8f9bbd", fontSize: 9, interval: Math.floor(portfolio.dates.length / 4) },
        axisLine: { lineStyle: { color: "#55617d" } }
      },
      yAxis: {
        type: "value",
        axisLabel: { color: "#8f9bbd", fontSize: 9, formatter: (v: number) => v.toFixed(2) },
        splitLine: { lineStyle: { color: "rgba(255,255,255,0.05)" } }
      },
      series: [{
        type: "line",
        data: portfolio.normalized_values,
        smooth: true,
        symbol: "none",
        lineStyle: { color: "#5fb0ff", width: 2 },
        areaStyle: {
          color: { type: "linear", x: 0, y: 0, x2: 0, y2: 1,
            colorStops: [
              { offset: 0, color: "rgba(95, 176, 255, 0.3)" },
              { offset: 1, color: "rgba(95, 176, 255, 0.05)" }
            ]
          }
        },
        markLine: { silent: true, symbol: "none", lineStyle: { color: "#8f9bbd", type: "dashed" }, data: [{ yAxis: 1.0 }] }
      }]
    };
  }, [portfolio]);

  // Industry Pie Chart
  const industryPieOption = useMemo(() => {
    if (!analytics || analytics.industry_allocation.length === 0) return null;
    return {
      backgroundColor: "transparent",
      tooltip: { trigger: "item", formatter: (p: any) => `${p.name}: ${p.percent.toFixed(1)}%` },
      legend: { type: "scroll", orient: "vertical", right: 5, top: 0, bottom: 0, textStyle: { color: "#b8c2e1", fontSize: 9 }, itemWidth: 8, itemHeight: 8 },
      series: [{
        type: "pie",
        radius: ["30%", "60%"],
        center: ["30%", "50%"],
        itemStyle: { borderRadius: 3, borderColor: "#12182a", borderWidth: 1 },
        label: { show: false },
        data: analytics.industry_allocation.slice(0, 8).map((item) => ({ value: item.market_value, name: item.name }))
      }]
    };
  }, [analytics]);

  // Industry Performance Bar Chart
  const industryBarOption = useMemo(() => {
    if (!analytics || analytics.industry_performance.length === 0) return null;
    const top6 = analytics.industry_performance.slice(0, 6);
    return {
      backgroundColor: "transparent",
      tooltip: { trigger: "axis", formatter: (p: any) => `${p[0].name}: ${p[0].value >= 0 ? "+" : ""}${p[0].value.toFixed(2)}%` },
      grid: { left: 5, right: 30, top: 5, bottom: 5, containLabel: true },
      xAxis: {
        type: "value",
        axisLabel: { color: "#8f9bbd", fontSize: 8, formatter: (v: number) => v.toFixed(0) + "%" },
        splitLine: { lineStyle: { color: "rgba(255,255,255,0.05)" } }
      },
      yAxis: {
        type: "category",
        data: top6.map((item) => item.name),
        axisLabel: { color: "#8f9bbd", fontSize: 9 },
        axisLine: { lineStyle: { color: "#55617d" } }
      },
      series: [{
        type: "bar",
        data: top6.map((item) => ({ value: item.return_pct, itemStyle: { color: item.return_pct >= 0 ? "#23c19f" : "#ef5f7c" } })),
        barWidth: "50%",
        label: { show: true, position: "right", formatter: (p: any) => (p.value >= 0 ? "+" : "") + p.value.toFixed(1) + "%", color: "#e6edf7", fontSize: 8 }
      }]
    };
  }, [analytics]);

  // Profit Distribution
  const profitDistOption = useMemo(() => {
    if (!analytics || analytics.profit_distribution.length === 0) return null;
    return {
      backgroundColor: "transparent",
      tooltip: { trigger: "axis" },
      grid: { left: 5, right: 5, top: 10, bottom: 5, containLabel: true },
      xAxis: {
        type: "category",
        data: analytics.profit_distribution.map((item) => item.range),
        axisLabel: { color: "#8f9bbd", fontSize: 8, rotate: 25 },
        axisLine: { lineStyle: { color: "#55617d" } }
      },
      yAxis: {
        type: "value",
        axisLabel: { color: "#8f9bbd", fontSize: 8 },
        splitLine: { lineStyle: { color: "rgba(255,255,255,0.05)" } }
      },
      series: [{
        type: "bar",
        data: analytics.profit_distribution.map((item, i) => ({ value: item.count, itemStyle: { color: i < 3 ? "#ef5f7c" : "#23c19f" } })),
        barWidth: "50%",
        label: { show: true, position: "top", color: "#e6edf7", fontSize: 9 }
      }]
    };
  }, [analytics]);

  // Treemap
  const treemapOption = useMemo(() => {
    if (!analytics || analytics.market_value_tree.length === 0) return null;
    return {
      backgroundColor: "transparent",
      tooltip: {
        formatter: (p: any) => p.treePathInfo.length === 2
          ? `${p.name}: ¥${(p.value / 10000).toFixed(1)}万`
          : `${p.name}: ${p.data.profit_pct >= 0 ? "+" : ""}${p.data.profit_pct.toFixed(1)}%`
      },
      series: [{
        type: "treemap",
        width: "100%",
        height: "100%",
        roam: false,
        nodeClick: false,
        breadcrumb: { show: false },
        label: { show: true, formatter: (p: any) => p.name, fontSize: 9, color: "#e6edf7" },
        itemStyle: { borderColor: "#12182a", borderWidth: 1, gapWidth: 1 },
        levels: [
          { itemStyle: { borderWidth: 0, gapWidth: 2 } },
          { itemStyle: { borderWidth: 2, gapWidth: 1 } },
          { colorSaturation: [0.35, 0.5], itemStyle: { borderWidth: 2, gapWidth: 1 } }
        ],
        data: analytics.market_value_tree
      }]
    };
  }, [analytics]);

  if (!portfolio || !analytics) {
    return <div className="dashboard-loading">加载中...</div>;
  }

  const isProfit = portfolio.total_return >= 0;

  return (
    <div className="portfolio-dashboard">
      {/* 2x2 Grid */}
      <div className="dashboard-grid">
        {/* Top-Left: Portfolio */}
        <div className="dashboard-cell">
          <div className="dashboard-cell__header">
            <span className="dashboard-cell__title">投资组合</span>
            <div className="dashboard-cell__stats">
              <span>{portfolio.stock_count}只</span>
              <span>投资 ¥{(portfolio.initial_investment / 10000).toFixed(1)}万</span>
              <span>市值 ¥{(portfolio.current_value / 10000).toFixed(2)}万</span>
              <span className={isProfit ? "stat-profit" : "stat-loss"}>
                {isProfit ? "+" : ""}{portfolio.return_pct.toFixed(2)}%
              </span>
            </div>
          </div>
          <div className="dashboard-cell__content">
            {portfolioOption && <ReactECharts option={portfolioOption} style={{ height: "100%" }} notMerge lazyUpdate />}
          </div>
        </div>

        {/* Top-Right: Industry */}
        <div className="dashboard-cell">
          <div className="dashboard-cell__header">
            <span className="dashboard-cell__title">行业分析</span>
            <div className="dashboard-cell__stats">
              <span className="stat-profit">{analytics.overview.up_count}盈利</span>
              <span className="stat-loss">{analytics.overview.down_count}亏损</span>
            </div>
          </div>
          <div className="dashboard-cell__content dashboard-cell__content--split">
            <div className="dashboard-half">
              <div className="dashboard-half__title">配置</div>
              {industryPieOption && <ReactECharts option={industryPieOption} style={{ height: "calc(100% - 18px)" }} notMerge lazyUpdate />}
            </div>
            <div className="dashboard-half">
              <div className="dashboard-half__title">表现</div>
              {industryBarOption && <ReactECharts option={industryBarOption} style={{ height: "calc(100% - 18px)" }} notMerge lazyUpdate />}
            </div>
          </div>
        </div>

        {/* Bottom-Left: Gainers/Losers */}
        <div className="dashboard-cell">
          <div className="dashboard-cell__header">
            <span className="dashboard-cell__title">涨跌榜</span>
          </div>
          <div className="dashboard-cell__content dashboard-cell__content--split">
            <div className="dashboard-half">
              <div className="dashboard-half__title dashboard-half__title--profit">涨幅榜</div>
              <div className="dashboard-list">
                {analytics.top_gainers.slice(0, 5).map((s, i) => (
                  <div key={s.ticker} className="dashboard-list__item">
                    <span className="dashboard-list__rank">{i + 1}</span>
                    <span className="dashboard-list__name">{s.name}</span>
                    <span className="dashboard-list__value stat-profit">+{s.profit_pct.toFixed(1)}%</span>
                  </div>
                ))}
              </div>
            </div>
            <div className="dashboard-half">
              <div className="dashboard-half__title dashboard-half__title--loss">跌幅榜</div>
              <div className="dashboard-list">
                {analytics.top_losers.slice(0, 5).map((s, i) => (
                  <div key={s.ticker} className="dashboard-list__item">
                    <span className="dashboard-list__rank">{i + 1}</span>
                    <span className="dashboard-list__name">{s.name}</span>
                    <span className="dashboard-list__value stat-loss">{s.profit_pct.toFixed(1)}%</span>
                  </div>
                ))}
              </div>
            </div>
          </div>
        </div>

        {/* Bottom-Right: Distribution */}
        <div className="dashboard-cell">
          <div className="dashboard-cell__header">
            <span className="dashboard-cell__title">分布分析</span>
          </div>
          <div className="dashboard-cell__content dashboard-cell__content--split">
            <div className="dashboard-half">
              <div className="dashboard-half__title">收益分布</div>
              {profitDistOption && <ReactECharts option={profitDistOption} style={{ height: "calc(100% - 18px)" }} notMerge lazyUpdate />}
            </div>
            <div className="dashboard-half">
              <div className="dashboard-half__title">市值分布</div>
              {treemapOption && <ReactECharts option={treemapOption} style={{ height: "calc(100% - 18px)" }} notMerge lazyUpdate />}
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}
