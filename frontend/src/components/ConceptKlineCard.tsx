/**
 * 概念板块 K线卡片 - 双K线布局（日线 + 30分钟）
 * 使用统一的 KlineChart 组件 (Lightweight Charts)
 */

import { useMemo, useState, useEffect } from "react";
import { useQuery } from "@tanstack/react-query";
import { apiFetch, REFRESH_INTERVALS } from "../utils/api";
import type { MAConfig } from "../types/chartConfig";
import { KlineChart, type KlineDataPoint } from "./charts";
import { UpdateTimeIndicator } from "./UpdateTimeIndicator";
import { isMarketOpen } from "../hooks/useRealtimePrice";

interface ConceptInfo {
  name: string;
  code: string;
  category: string;
  stock_count: number;
  change_pct: number | null;
}

interface ConceptRealtimeData {
  code: string;
  name: string;
  price: number;
  pre_close: number;
  change_pct: number;
  last_update: string;
}

interface KlineBar {
  datetime: string;
  open: number;
  high: number;
  low: number;
  close: number;
  volume: number;
  amount: number;
}

interface ConceptKlineResponse {
  code: string;
  name: string;
  klines: KlineBar[];
}

async function fetchConceptKline(code: string, period: string): Promise<ConceptKlineResponse> {
  const response = await apiFetch(`/api/concepts/kline/${code}?period=${period}&limit=120`);
  if (!response.ok) {
    throw new Error("Failed to fetch concept kline");
  }
  return response.json();
}

async function fetchConceptRealtime(code: string): Promise<ConceptRealtimeData> {
  const response = await apiFetch(`/api/concepts/realtime/${code}`);
  if (!response.ok) {
    throw new Error("Failed to fetch concept realtime");
  }
  return response.json();
}

interface Props {
  concept: ConceptInfo;
  maConfig: MAConfig;
  onClick?: (concept: ConceptInfo) => void;
}

export function ConceptKlineCard({ concept, maConfig, onClick }: Props) {
  const [lastUpdate, setLastUpdate] = useState<string>("");

  // 获取实时数据（收盘后停止轮询）
  const { data: realtimeData } = useQuery({
    queryKey: ["concept-realtime", concept.code],
    queryFn: () => fetchConceptRealtime(concept.code),
    staleTime: 1000 * 30, // 30秒
    refetchInterval: isMarketOpen() ? 1000 * 30 : false, // 收盘后停止轮询
  });

  // 获取日线数据（收盘后停止轮询）
  const { data: dailyData } = useQuery({
    queryKey: ["concept-kline", concept.code, "daily"],
    queryFn: () => fetchConceptKline(concept.code, "daily"),
    staleTime: REFRESH_INTERVALS.boards,
    refetchInterval: isMarketOpen() ? REFRESH_INTERVALS.boards : false, // 收盘后停止轮询
  });

  // 获取30分钟数据（收盘后停止轮询）
  const { data: mins30Data } = useQuery({
    queryKey: ["concept-kline", concept.code, "30min"],
    queryFn: () => fetchConceptKline(concept.code, "30min"),
    staleTime: 1000 * 60 * 5, // 5分钟
    refetchInterval: isMarketOpen() ? 1000 * 60 * 5 : false, // 收盘后停止轮询
  });

  // 更新时间戳
  useEffect(() => {
    setLastUpdate(new Date().toLocaleTimeString('zh-CN'));
  }, [realtimeData, dailyData, mins30Data]);

  // 计算今日涨跌幅（优先使用实时数据，其次使用日线数据）
  const { todayChangePct, prevDayChangePct, currentPrice } = useMemo(() => {
    // 如果有实时数据，使用实时涨跌幅
    if (realtimeData) {
      let prevDayChangePct = null;
      if (dailyData && dailyData.klines.length >= 3) {
        const klines = dailyData.klines;
        const prevClose = klines[klines.length - 2].close;
        const prev2Close = klines[klines.length - 3].close;
        prevDayChangePct = ((prevClose - prev2Close) / prev2Close) * 100;
      }
      return {
        todayChangePct: realtimeData.change_pct,
        prevDayChangePct,
        currentPrice: realtimeData.price
      };
    }

    // 回退到日线数据计算
    if (!dailyData || dailyData.klines.length < 2) {
      return { todayChangePct: concept.change_pct ?? 0, prevDayChangePct: null, currentPrice: null };
    }
    const klines = dailyData.klines;
    const lastClose = klines[klines.length - 1].close;
    const prevClose = klines[klines.length - 2].close;
    const todayChangePct = ((lastClose - prevClose) / prevClose) * 100;

    let prevDayChangePct = null;
    if (klines.length >= 3) {
      const prev2Close = klines[klines.length - 3].close;
      prevDayChangePct = ((prevClose - prev2Close) / prev2Close) * 100;
    }

    return { todayChangePct, prevDayChangePct, currentPrice: lastClose };
  }, [realtimeData, dailyData, concept.change_pct]);

  const isPositive = todayChangePct >= 0;

  // 转换日线数据格式
  const dailyChartData: KlineDataPoint[] = useMemo(() => {
    if (!dailyData || !dailyData.klines) return [];
    return dailyData.klines.map(k => ({
      date: k.datetime.toString(),
      open: k.open,
      high: k.high,
      low: k.low,
      close: k.close,
      volume: k.volume,
    }));
  }, [dailyData]);

  // 转换30分钟数据格式（使用Unix时间戳）
  const mins30ChartData: KlineDataPoint[] = useMemo(() => {
    if (!mins30Data || !mins30Data.klines) return [];
    return mins30Data.klines.map(k => {
      // datetime格式: 202512291120 -> 转为Unix时间戳
      const dt = k.datetime.toString();
      const year = parseInt(dt.slice(0, 4));
      const month = parseInt(dt.slice(4, 6)) - 1;
      const day = parseInt(dt.slice(6, 8));
      const hour = parseInt(dt.slice(8, 10));
      const minute = parseInt(dt.slice(10, 12));
      const timestamp = Math.floor(new Date(year, month, day, hour, minute).getTime() / 1000) + 8 * 3600;

      return {
        date: String(timestamp),
        open: k.open,
        high: k.high,
        low: k.low,
        close: k.close,
        volume: k.volume,
      };
    });
  }, [mins30Data]);

  const handleDoubleClick = () => {
    if (onClick) {
      onClick(concept);
    }
  };

  return (
    <div className="concept-kline-card" onDoubleClick={handleDoubleClick} style={{ cursor: onClick ? "pointer" : "default" }}>
      {/* Header */}
      <div className="concept-kline-card__header">
        <div className="concept-kline-card__title">
          <span className="concept-kline-card__name">{concept.name}</span>
          <span className="concept-kline-card__count">{concept.stock_count}只</span>
          <span className="concept-kline-card__tag">{concept.category}</span>
        </div>
        <div className="concept-kline-card__meta">
          {currentPrice !== null && (
            <span className={`concept-kline-card__price ${isPositive ? "concept-kline-card__price--up" : "concept-kline-card__price--down"}`}>
              {currentPrice.toFixed(2)}
            </span>
          )}
          <span className={`concept-kline-card__change ${isPositive ? "concept-kline-card__change--up" : "concept-kline-card__change--down"}`}>
            今 {isPositive ? "+" : ""}{todayChangePct.toFixed(2)}%
          </span>
          {prevDayChangePct !== null && (
            <span className={`concept-kline-card__prev-change ${prevDayChangePct >= 0 ? "concept-kline-card__prev-change--up" : "concept-kline-card__prev-change--down"}`}>
              昨 {prevDayChangePct >= 0 ? "+" : ""}{prevDayChangePct.toFixed(2)}%
            </span>
          )}
          <span className="concept-kline-card__live">🔴 {lastUpdate}</span>
        </div>
      </div>

      {/* 双K线图区域 */}
      <div className="concept-kline-card__charts">
        <div className="concept-kline-card__chart-container">
          <div className="concept-kline-card__chart-header">
            <div className="concept-kline-card__chart-label">日线</div>
            <UpdateTimeIndicator section="concept" timeframe="day" />
          </div>
          <div className="concept-kline-card__chart">
            {dailyChartData.length > 0 ? (
              <KlineChart
                data={dailyChartData}
                height={280}
                showVolume={true}
                showMACD={true}
                maConfig={maConfig}
                compact={true}
              />
            ) : (
              <div className="concept-kline-card__loading">加载日线...</div>
            )}
          </div>
        </div>
        <div className="concept-kline-card__chart-container">
          <div className="concept-kline-card__chart-header">
            <div className="concept-kline-card__chart-label">30分钟</div>
            <UpdateTimeIndicator section="concept" timeframe="30m" />
          </div>
          <div className="concept-kline-card__chart">
            {mins30ChartData.length > 0 ? (
              <KlineChart
                data={mins30ChartData}
                height={280}
                showVolume={true}
                showMACD={true}
                maConfig={maConfig}
                compact={true}
              />
            ) : (
              <div className="concept-kline-card__loading">加载30分钟...</div>
            )}
          </div>
        </div>
      </div>
    </div>
  );
}
