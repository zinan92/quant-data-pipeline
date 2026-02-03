/**
 * Hook for fetching and managing K-line data in the dashboard.
 * Supports A-share indexes, commodities, and crypto assets.
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

export const ASSETS = {
  indexes: [
    { id: "000001.SH", name: "上证指数", type: "index" as const },
    { id: "399001.SZ", name: "深证成指", type: "index" as const },
    { id: "399006.SZ", name: "创业板指", type: "index" as const },
  ],
  commodities: [
    { id: "GC=F", name: "黄金", type: "commodity" as const },
    { id: "SI=F", name: "白银", type: "commodity" as const },
    { id: "HG=F", name: "铜", type: "commodity" as const },
    { id: "CL=F", name: "原油", type: "commodity" as const },
  ],
  crypto: [
    { id: "BTC", name: "BTC", type: "crypto" as const },
    { id: "ETH", name: "ETH", type: "crypto" as const },
    { id: "SOL", name: "SOL", type: "crypto" as const },
  ],
};

export const TIMEFRAMES = [
  { id: "day", label: "日线" },
  { id: "30m", label: "30分" },
  { id: "5m", label: "5分" },
];

// ─── URL builder ───

function getKlineUrl(asset: Asset, timeframe: string): string {
  const tfMap: Record<string, Record<string, string>> = {
    index: { day: "day", "30m": "30m", "5m": "5m" },
    commodity: { day: "1d", "30m": "30m", "5m": "5m" },
    crypto: { day: "1d", "30m": "1h", "5m": "5m" },
  };
  const interval = tfMap[asset.type]?.[timeframe] || "day";

  switch (asset.type) {
    case "index":
      return `/api/candles/${asset.id}?timeframe=${interval}&limit=120`;
    case "commodity":
      return `/api/commodities/klines/${encodeURIComponent(asset.id)}?interval=${interval}`;
    case "crypto":
      return `/api/crypto/kline/${asset.id}?interval=${interval}&limit=120`;
    default:
      return "";
  }
}

// ─── Response normalizer ───

function normalizeKlines(data: any, type: string): KlineDataPoint[] {
  const items = data.candles || data.klines || [];
  return items.map((k: any) => {
    let dateStr = "";

    // For intraday data with epoch ms timestamps, use unix seconds
    // (lightweight-charts handles numeric timestamps as Unix epoch seconds)
    if (k.timestamp && typeof k.timestamp === "number") {
      // epoch ms → seconds string (KlineChart's parseDate handles numeric strings)
      dateStr = String(Math.floor(k.timestamp / 1000));
    } else if (k.date && typeof k.date === "string") {
      // Commodity/index daily: "YYYY-MM-DD" or "YYYY-MM-DDTHH:MM:SS"
      if (k.date.includes("T")) {
        // Intraday: convert to unix seconds
        dateStr = String(Math.floor(new Date(k.date).getTime() / 1000));
      } else {
        dateStr = k.date;
      }
    } else if (k.time && typeof k.time === "string") {
      if (k.time.includes("T")) {
        dateStr = String(Math.floor(new Date(k.time).getTime() / 1000));
      } else {
        dateStr = k.time;
      }
    } else if (k.timestamp && typeof k.timestamp === "string") {
      if (k.timestamp.includes("T")) {
        dateStr = String(Math.floor(new Date(k.timestamp).getTime() / 1000));
      } else {
        dateStr = k.timestamp;
      }
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

// ─── Hook ───

export interface DashboardKlinesState {
  selectedAsset: Asset;
  selectedTimeframe: string;
  klineData: KlineDataPoint[];
  loading: boolean;
  error: string | null;
  setAsset: (asset: Asset) => void;
  setTimeframe: (tf: string) => void;
}

export function useDashboardKlines(): DashboardKlinesState {
  const [selectedAsset, setSelectedAsset] = useState<Asset>(ASSETS.indexes[0]);
  const [selectedTimeframe, setSelectedTimeframe] = useState("day");
  const [klineData, setKlineData] = useState<KlineDataPoint[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  // Cache: keyed by "assetId|timeframe"
  const cacheRef = useRef<Record<string, KlineDataPoint[]>>({});

  const fetchKlines = useCallback(async (asset: Asset, timeframe: string) => {
    const cacheKey = `${asset.id}|${timeframe}`;

    // Return cached data if available
    if (cacheRef.current[cacheKey]) {
      setKlineData(cacheRef.current[cacheKey]);
      return;
    }

    setLoading(true);
    setError(null);

    try {
      const url = getKlineUrl(asset, timeframe);
      const resp = await fetch(buildApiUrl(url));
      if (!resp.ok) {
        throw new Error(`Failed to fetch klines: ${resp.status}`);
      }
      const data = await resp.json();
      const normalized = normalizeKlines(data, asset.type);

      // Cache the result
      cacheRef.current[cacheKey] = normalized;
      setKlineData(normalized);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Failed to load kline data");
      setKlineData([]);
    } finally {
      setLoading(false);
    }
  }, []);

  // Fetch when asset or timeframe changes
  useEffect(() => {
    fetchKlines(selectedAsset, selectedTimeframe);
  }, [selectedAsset, selectedTimeframe, fetchKlines]);

  const setAsset = useCallback((asset: Asset) => {
    setSelectedAsset(asset);
  }, []);

  const setTimeframe = useCallback((tf: string) => {
    setSelectedTimeframe(tf);
  }, []);

  return {
    selectedAsset,
    selectedTimeframe,
    klineData,
    loading,
    error,
    setAsset,
    setTimeframe,
  };
}
