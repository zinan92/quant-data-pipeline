/**
 * Hook for fetching ALL K-line data for the dashboard grid.
 * Fetches 10 assets × 3 timeframes = 30 datasets in parallel.
 */
import { useState, useCallback, useRef, useEffect } from "react";
import { buildApiUrl } from "../utils/api";
import type { KlineDataPoint } from "../components/charts/KlineChart";

// ─── Asset types ───

export interface Asset {
  id: string;
  name: string;
  type: "index" | "commodity" | "crypto";
}

export interface AssetGroup {
  title: string;
  emoji: string;
  assets: Asset[];
}

export const ASSET_GROUPS: AssetGroup[] = [
  {
    title: "A-SHARE INDEXES",
    emoji: "🇨🇳",
    assets: [
      { id: "000001.SH", name: "上证指数", type: "index" },
      { id: "399001.SZ", name: "深证成指", type: "index" },
      { id: "399006.SZ", name: "创业板指", type: "index" },
    ],
  },
  {
    title: "COMMODITIES",
    emoji: "🛢️",
    assets: [
      { id: "GC=F", name: "黄金", type: "commodity" },
      { id: "SI=F", name: "白银", type: "commodity" },
      { id: "HG=F", name: "铜", type: "commodity" },
      { id: "CL=F", name: "原油", type: "commodity" },
    ],
  },
  {
    title: "CRYPTO",
    emoji: "₿",
    assets: [
      { id: "BTC", name: "BTC", type: "crypto" },
      { id: "ETH", name: "ETH", type: "crypto" },
      { id: "SOL", name: "SOL", type: "crypto" },
    ],
  },
];

// Flatten for convenience
export const ALL_ASSETS: Asset[] = ASSET_GROUPS.flatMap((g) => g.assets);

export const TIMEFRAMES = [
  { id: "day", label: "日线" },
  { id: "30m", label: "30分" },
  { id: "5m", label: "5分" },
];

// ─── URL builder — uses correct endpoint per asset type ───

function getKlineUrl(asset: Asset, timeframe: string): string {
  switch (asset.type) {
    case "index":
      // Use the dedicated index kline endpoints (NOT /api/candles which is for stocks)
      if (timeframe === "day") {
        return `/api/index/kline/${asset.id}?limit=120`;
      } else if (timeframe === "30m") {
        return `/api/index/kline30m/${asset.id}?limit=120`;
      } else {
        // 5m — use 30m endpoint as fallback (no 5m index endpoint exists)
        return `/api/index/kline30m/${asset.id}?limit=120`;
      }

    case "commodity": {
      const interval = timeframe === "day" ? "1d" : timeframe === "30m" ? "30m" : "5m";
      return `/api/commodities/klines/${encodeURIComponent(asset.id)}?interval=${interval}`;
    }

    case "crypto": {
      const interval = timeframe === "day" ? "1d" : timeframe === "30m" ? "30m" : "5m";
      return `/api/crypto/kline/${asset.id}?interval=${interval}&limit=120`;
    }

    default:
      return "";
  }
}

// ─── Response normalizer ───

function normalizeKlines(data: any, type: string): KlineDataPoint[] {
  const items = data.candles || data.klines || [];
  return items.map((k: any) => {
    let dateStr = "";

    // Index daily: { date: "YYYYMMDD" }
    if (k.date && typeof k.date === "string") {
      if (/^\d{8}$/.test(k.date)) {
        // YYYYMMDD → YYYY-MM-DD
        dateStr = `${k.date.slice(0, 4)}-${k.date.slice(4, 6)}-${k.date.slice(6, 8)}`;
      } else if (k.date.includes("T")) {
        // Intraday: "YYYY-MM-DDTHH:MM:SS" → unix seconds
        dateStr = String(Math.floor(new Date(k.date).getTime() / 1000));
      } else {
        // "YYYY-MM-DD" already fine
        dateStr = k.date;
      }
    }
    // Index 30m: { datetime: unix_seconds_number }
    else if (k.datetime && typeof k.datetime === "number") {
      dateStr = String(k.datetime);
    }
    // Crypto: { time: "YYYY-MM-DDTHH:MM:SS", timestamp: epoch_ms }
    else if (k.timestamp && typeof k.timestamp === "number") {
      dateStr = String(Math.floor(k.timestamp / 1000));
    } else if (k.time && typeof k.time === "string") {
      if (k.time.includes("T")) {
        dateStr = String(Math.floor(new Date(k.time).getTime() / 1000));
      } else {
        dateStr = k.time;
      }
    } else if (k.timestamp && typeof k.timestamp === "string") {
      dateStr = k.timestamp;
    }

    return {
      date: dateStr,
      open: k.open,
      high: k.high,
      low: k.low,
      close: k.close,
      volume: k.volume || 0,
    };
  });
}

// ─── Health check type ───

export interface HealthStatus {
  status: "healthy" | "degraded" | "error" | "loading";
  checks?: Record<string, any>;
  timestamp?: string;
}

// ─── Data map type ───
// assetId → timeframe → KlineDataPoint[]
export type KlineDataMap = Record<string, Record<string, KlineDataPoint[]>>;

export interface DashboardGridState {
  dataMap: KlineDataMap;
  loading: boolean;
  loadingCount: number;
  totalCount: number;
  errors: string[];
  health: HealthStatus;
  refresh: () => void;
}

// ─── Hook ───

export function useDashboardKlines(): DashboardGridState {
  const [dataMap, setDataMap] = useState<KlineDataMap>({});
  const [loading, setLoading] = useState(true);
  const [loadingCount, setLoadingCount] = useState(0);
  const [errors, setErrors] = useState<string[]>([]);
  const [health, setHealth] = useState<HealthStatus>({ status: "loading" });
  const fetchedRef = useRef(false);

  const totalCount = ALL_ASSETS.length * TIMEFRAMES.length; // 30

  const fetchAll = useCallback(async () => {
    setLoading(true);
    setLoadingCount(0);
    setErrors([]);

    const newMap: KlineDataMap = {};
    const newErrors: string[] = [];

    // Fetch per asset group sequentially, 3 timeframes per asset in parallel
    // This prevents 30 concurrent requests overwhelming yfinance/backend
    for (const group of ASSET_GROUPS) {
      const groupResults = await Promise.allSettled(
        group.assets.flatMap((asset) =>
          TIMEFRAMES.map(async (tf) => {
            const url = getKlineUrl(asset, tf.id);
            if (!url) throw new Error(`No URL for ${asset.name} ${tf.id}`);
            const resp = await fetch(buildApiUrl(url));
            if (!resp.ok) {
              throw new Error(`${asset.name} ${tf.label}: HTTP ${resp.status}`);
            }
            const data = await resp.json();
            const normalized = normalizeKlines(data, asset.type);
            setLoadingCount((c) => c + 1);
            return { asset, timeframe: tf.id, data: normalized };
          })
        )
      );

      for (const result of groupResults) {
        if (result.status === "fulfilled") {
          const { asset, timeframe, data } = result.value;
          if (!newMap[asset.id]) newMap[asset.id] = {};
          newMap[asset.id][timeframe] = data;
        } else {
          newErrors.push(result.reason?.message || "Unknown error");
          setLoadingCount((c) => c + 1);
        }
      }

      // Update state progressively per group so charts appear as they load
      setDataMap((prev) => ({ ...prev, ...newMap }));
    }

    setDataMap(newMap);
    setErrors(newErrors);
    setLoading(false);

    // Fetch health check
    try {
      const healthResp = await fetch(buildApiUrl("/api/health/data"));
      if (healthResp.ok) {
        const healthData = await healthResp.json();
        setHealth(healthData);
      } else {
        setHealth({ status: "error" });
      }
    } catch {
      setHealth({ status: "error" });
    }
  }, []);

  // Fetch on mount
  useEffect(() => {
    if (!fetchedRef.current) {
      fetchedRef.current = true;
      fetchAll();
    }
  }, [fetchAll]);

  return {
    dataMap,
    loading,
    loadingCount,
    totalCount,
    errors,
    health,
    refresh: fetchAll,
  };
}
