/**
 * Hook for fetching ALL K-line data for the dashboard grid.
 * 10 assets × 3 timeframes = 30 datasets.
 */
import { useState, useCallback, useRef, useEffect } from "react";
import { buildApiUrl } from "../utils/api";
import type { KlineDataPoint } from "../components/charts/KlineChart";

// ─── Types ───

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

export const ALL_ASSETS: Asset[] = ASSET_GROUPS.flatMap((g) => g.assets);

export const TIMEFRAMES = [
  { id: "day", label: "日线" },
  { id: "30m", label: "30分" },
  { id: "5m", label: "5分" },
];

// ─── URL builder ───

function getKlineUrl(asset: Asset, timeframe: string): string {
  switch (asset.type) {
    case "index":
      if (timeframe === "day") return `/api/index/kline/${asset.id}?limit=120`;
      if (timeframe === "30m") return `/api/index/kline30m/${asset.id}?limit=120`;
      return `/api/index/kline30m/${asset.id}?limit=120`; // 5m fallback

    case "commodity": {
      const interval = timeframe === "day" ? "1d" : timeframe === "30m" ? "30m" : "5m";
      return `/api/commodities/klines/${encodeURIComponent(asset.id)}?interval=${interval}`;
    }

    case "crypto": {
      const interval = timeframe === "day" ? "1d" : timeframe === "30m" ? "1h" : "5m";
      return `/api/crypto/kline/${asset.id}?interval=${interval}&limit=120`;
    }

    default:
      return "";
  }
}

// ─── Normalizer ───

function normalizeKlines(data: any, _type: string): KlineDataPoint[] {
  const items = data.candles || data.klines || [];
  if (!Array.isArray(items) || items.length === 0) return [];

  return items.map((k: any) => {
    let dateStr = "";

    // Has k.date (index daily "YYYYMMDD", commodity "YYYY-MM-DD", commodity intraday "YYYY-MM-DDTHH:MM:SS")
    if (k.date && typeof k.date === "string") {
      if (/^\d{8}$/.test(k.date)) {
        dateStr = `${k.date.slice(0, 4)}-${k.date.slice(4, 6)}-${k.date.slice(6, 8)}`;
      } else if (k.date.includes("T")) {
        dateStr = String(Math.floor(new Date(k.date).getTime() / 1000));
      } else {
        dateStr = k.date; // "YYYY-MM-DD"
      }
    }
    // Index 30m: { datetime: unix_seconds }
    else if (k.datetime && typeof k.datetime === "number") {
      dateStr = String(k.datetime);
    }
    // Crypto: { timestamp: epoch_ms }
    else if (k.timestamp && typeof k.timestamp === "number") {
      dateStr = String(Math.floor(k.timestamp / 1000));
    }
    // Crypto fallback: { time: "ISO string" }
    else if (k.time && typeof k.time === "string") {
      if (k.time.includes("T")) {
        dateStr = String(Math.floor(new Date(k.time).getTime() / 1000));
      } else {
        dateStr = k.time;
      }
    }

    return {
      date: dateStr,
      open: k.open ?? 0,
      high: k.high ?? 0,
      low: k.low ?? 0,
      close: k.close ?? 0,
      volume: k.volume ?? 0,
    };
  }).filter((k: KlineDataPoint) => k.date !== "" && k.close > 0);
}

// ─── Health check ───

export interface HealthStatus {
  status: "healthy" | "degraded" | "error" | "loading";
  checks?: Record<string, any>;
}

// ─── Data map ───
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

  const totalCount = ALL_ASSETS.length * TIMEFRAMES.length;

  const fetchAll = useCallback(async () => {
    setLoading(true);
    setLoadingCount(0);
    setErrors([]);

    // Build task list
    const tasks = ALL_ASSETS.flatMap((asset) =>
      TIMEFRAMES.map((tf) => ({ asset, timeframe: tf.id, url: getKlineUrl(asset, tf.id) }))
    );

    // Fetch all in parallel with Promise.allSettled
    const results = await Promise.allSettled(
      tasks.map(async (task) => {
        const resp = await fetch(buildApiUrl(task.url));
        if (!resp.ok) throw new Error(`HTTP ${resp.status}`);
        const data = await resp.json();
        const normalized = normalizeKlines(data, task.asset.type);
        return { assetId: task.asset.id, timeframe: task.timeframe, data: normalized };
      })
    );

    // Build map from results
    const map: KlineDataMap = {};
    const errs: string[] = [];
    let loaded = 0;

    for (let i = 0; i < results.length; i++) {
      const result = results[i];
      const task = tasks[i];
      loaded++;

      if (result.status === "fulfilled") {
        const { assetId, timeframe, data } = result.value;
        if (!map[assetId]) map[assetId] = {};
        map[assetId][timeframe] = data;
      } else {
        errs.push(`${task.asset.name} ${task.timeframe}: ${result.reason?.message || "error"}`);
      }
    }

    console.log("[Dashboard] Loaded", loaded, "charts. Map keys:", Object.keys(map), "Errors:", errs.length);
    for (const [id, tfs] of Object.entries(map)) {
      console.log(`  ${id}:`, Object.entries(tfs).map(([tf, d]) => `${tf}=${d.length}`).join(", "));
    }

    setDataMap(map);
    setLoadingCount(loaded);
    setErrors(errs);
    setLoading(false);

    // Health check
    try {
      const hr = await fetch(buildApiUrl("/api/health/data"));
      if (hr.ok) setHealth(await hr.json());
      else setHealth({ status: "error" });
    } catch {
      setHealth({ status: "error" });
    }
  }, []);

  useEffect(() => {
    if (!fetchedRef.current) {
      fetchedRef.current = true;
      fetchAll();
    }
  }, [fetchAll]);

  return { dataMap, loading, loadingCount, totalCount, errors, health, refresh: fetchAll };
}
