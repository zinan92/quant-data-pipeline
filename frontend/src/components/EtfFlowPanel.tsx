import { useQuery } from "@tanstack/react-query";
import { apiFetch, REFRESH_INTERVALS } from "../utils/api";
import { EtfKlineCard } from "./EtfKlineCard";
import type { MAConfig } from "../types/chartConfig";

interface EtfFlowItem {
  name: string;
  ticker: string;
  flow_billion: number;
  turnover_billion: number | null;
  change_pct: number | null;
  market_cap_billion: number | null;
  exposure: string | null;
  flow_ratio_pct: number | null;
}

interface EtfFlowResponse {
  as_of: string;
  source: string;
  summary: {
    net_flow_billion: number;
    inflow_billion: number;
    outflow_billion: number;
    turnover_billion: number;
    avg_change_pct: number | null;
    inflow_ratio: number;
  };
  all_etfs: EtfFlowItem[];
}

async function fetchEtfFlowSummary(): Promise<EtfFlowResponse> {
  const response = await apiFetch("/api/etf/flows");
  if (!response.ok) {
    throw new Error("Failed to fetch ETF flows");
  }
  return response.json();
}

function formatNumber(value: number, digits = 2): string {
  const abs = Math.abs(value);
  if (abs >= 1000) {
    return `${value.toFixed(0)}`;
  }
  return value.toFixed(digits);
}

interface Props {
  maConfig: MAConfig;
}

export function EtfFlowPanel({ maConfig }: Props) {
  const { data, isLoading, error } = useQuery({
    queryKey: ["etf-flow-summary"],
    queryFn: fetchEtfFlowSummary,
    staleTime: REFRESH_INTERVALS.boards,
    refetchInterval: REFRESH_INTERVALS.boards
  });

  if (isLoading) {
    return (
      <div className="etf-flow etf-flow--fullscreen etf-flow--loading">
        <div className="etf-flow__spinner">ETF资金流加载中...</div>
      </div>
    );
  }

  if (error || !data) {
    return null;
  }

  return (
    <div className="etf-flow etf-flow--fullscreen">
      <div className="etf-flow__header">
        <div>
          <h3 className="etf-flow__title">行业ETF涨跌排行</h3>
          <p className="etf-flow__subtitle">按当日涨跌幅排序，{data.all_etfs.length}只行业ETF</p>
        </div>
        <div className="etf-flow__meta">
          <span>数据时间：{data.as_of}</span>
        </div>
      </div>

      {/* ETF网格布局 */}
      <div className="etf-flow__grid">
        {data.all_etfs.map(item => (
          <EtfKlineCard key={item.ticker} item={item} type="inflow" asOf={data.as_of} maConfig={maConfig} />
        ))}
      </div>
    </div>
  );
}
