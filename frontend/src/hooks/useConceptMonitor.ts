import { useEffect, useState } from "react";
import { buildApiUrl } from "../utils/api";
import { isMarketOpen } from "./useRealtimePrice";

export interface ConceptData {
  rank: number;
  name: string;
  code: string;
  boardType?: string;  // "行业" or "概念"
  changePct: number;
  changeValue: number;
  mainVolume: number | null;  // Optional field
  moneyInflow: number;
  volumeRatio: number;
  upCount: number;
  downCount: number;
  limitUp: number;
  totalStocks: number;
  turnover: number;
  volume: number;
  day5Change: number;
  day10Change: number;
  day20Change: number;
}

interface ConceptMonitorResponse {
  success: boolean;
  timestamp: string;
  total: number;
  data: ConceptData[];
}

interface UseConceptMonitorOptions {
  type: 'top' | 'watch'; // 涨幅前20 or 自选概念
  topN?: number; // 当type='top'时，获取前N个
  interval?: number; // 轮询间隔（毫秒），默认150秒
  enabled?: boolean; // 是否启用
}

/**
 * 使用概念板块监控Hook
 *
 * @param options - 配置选项
 * @returns 概念板块数据和更新时间
 *
 * @example
 * const { data, timestamp, loading } = useConceptMonitor({
 *   type: 'top',
 *   topN: 20,
 *   interval: 150000, // 2.5分钟
 *   enabled: true
 * });
 */
export function useConceptMonitor(options: UseConceptMonitorOptions) {
  const { type, topN = 20, interval = 150000, enabled = true } = options;

  const [data, setData] = useState<ConceptData[]>([]);
  const [timestamp, setTimestamp] = useState<string>('');
  const [loading, setLoading] = useState<boolean>(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    // 如果未启用，不执行
    if (!enabled) {
      return;
    }

    const fetchData = async () => {
      try {
        const endpoint = type === 'top'
          ? `/api/concept-monitor/top?n=${topN}`
          : `/api/concept-monitor/watch`;

        const url = buildApiUrl(endpoint);

        const response = await fetch(url, {
          method: 'GET',
          cache: 'no-cache'
        });

        if (!response.ok) {
          throw new Error(`HTTP ${response.status}: ${response.statusText}`);
        }

        const json: ConceptMonitorResponse = await response.json();

        if (json.success) {
          setData(json.data);
          setTimestamp(json.timestamp);
          setError(null);
        } else {
          throw new Error('API returned success=false');
        }
      } catch (err) {
        console.error('Failed to fetch concept monitor data:', err);
        setError(err instanceof Error ? err.message : '获取数据失败');
      } finally {
        setLoading(false);
      }
    };

    // 立即获取一次数据
    fetchData();

    // 设置定时轮询（收盘后停止）
    if (!isMarketOpen()) {
      // Market Off: 只获取一次，不轮询
      return;
    }

    // Market On: 设置定时轮询
    const intervalId = setInterval(fetchData, interval);

    // 清理
    return () => {
      clearInterval(intervalId);
    };
  }, [type, topN, interval, enabled]);

  return { data, timestamp, loading, error };
}
