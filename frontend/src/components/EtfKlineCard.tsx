/**
 * ETF K线卡片
 * 使用统一的 KlineChart 组件 (Lightweight Charts)
 */

import { useMemo } from "react";
import { useQuery } from "@tanstack/react-query";
import { apiFetch, REFRESH_INTERVALS } from "../utils/api";
import type { MAConfig } from "../types/chartConfig";
import { KlineChart, type KlineDataPoint } from "./charts";

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

interface KlineData {
  date: string;
  open: number;
  high: number;
  low: number;
  close: number;
  volume: number;
  amount: number;
}

interface KlineResponse {
  ticker: string;
  count: number;
  klines: KlineData[];
}

async function fetchEtfKline(ticker: string): Promise<KlineResponse> {
  const response = await apiFetch(`/api/etf/kline/${ticker}?limit=120`);
  if (!response.ok) {
    throw new Error("Failed to fetch ETF kline");
  }
  return response.json();
}

interface Props {
  item: EtfFlowItem;
  type: "broad" | "inflow" | "outflow";
  asOf: string;  // 格式: "YYYY-MM-DD"
  maConfig: MAConfig;
}

export function EtfKlineCard({ item, type, asOf, maConfig }: Props) {
  const { data: klineData } = useQuery({
    queryKey: ["etf-kline", item.ticker],
    queryFn: () => fetchEtfKline(item.ticker),
    staleTime: REFRESH_INTERVALS.boards,
  });

  const changePct = item.change_pct ?? 0;
  const isPositive = changePct >= 0;

  // 转换数据格式为 KlineChart 需要的格式
  const chartData: KlineDataPoint[] = useMemo(() => {
    if (!klineData || !klineData.klines) return [];
    return klineData.klines.map(k => ({
      date: k.date.toString().replace(/\.0$/, ''),
      open: k.open,
      high: k.high,
      low: k.low,
      close: k.close,
      volume: k.volume,
      amount: k.amount,
    }));
  }, [klineData]);

  return (
    <div className="etf-kline-card">
      {/* Header */}
      <div className="etf-kline-card__header">
        <div className="etf-kline-card__title">
          <span className="etf-kline-card__name">{item.name}</span>
          {item.market_cap_billion !== null && item.market_cap_billion !== undefined && (
            <span className="etf-kline-card__market-cap">{item.market_cap_billion.toFixed(0)}亿</span>
          )}
          {item.exposure && <span className="etf-kline-card__tag">{item.exposure}</span>}
        </div>
        <div className={`etf-kline-card__change ${isPositive ? "etf-kline-card__change--up" : "etf-kline-card__change--down"}`}>
          {isPositive ? "+" : ""}{changePct.toFixed(2)}%
        </div>
      </div>

      {/* K线图（使用统一组件） */}
      <div className="etf-kline-card__chart etf-kline-card__chart--full">
        {chartData.length > 0 ? (
          <KlineChart
            data={chartData}
            height={320}
            showVolume={true}
            showMACD={true}
            maConfig={maConfig}
            compact={true}
          />
        ) : (
          <div className="etf-kline-card__loading">加载K线...</div>
        )}
      </div>
    </div>
  );
}
