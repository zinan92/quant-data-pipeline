import { useEffect, useState, useRef, useCallback } from "react";
import { buildApiUrl } from "../utils/api";
import type {
  IndexRealtimeData,
  CommoditiesResponse,
  CryptoTickersResponse,
  AssetCardData,
} from "../types/dashboard";

const POLL_INTERVAL = 60_000; // 60 seconds
const CRYPTO_POLL_INTERVAL = 15_000; // 15 seconds (crypto moves fast)
const MAX_HISTORY = 20; // sparkline data points

interface DashboardState {
  indexes: AssetCardData[];
  commodities: AssetCardData[];
  crypto: AssetCardData[];
  loading: boolean;
  error: string | null;
  lastUpdate: string | null;
}

const INDEX_CODES = [
  { code: "000001.SH", name: "上证指数" },
  { code: "399001.SZ", name: "深证成指" },
  { code: "399006.SZ", name: "创业板指" },
];

const CRYPTO_SYMBOLS = ["BTC", "ETH", "SOL", "HYPE"];

function toCardData(
  id: string,
  name: string,
  price: number,
  change: number,
  changePct: number,
  lastUpdate: string,
  high24h?: number,
  low24h?: number,
  nameCn?: string,
): AssetCardData {
  return {
    id,
    name,
    nameCn,
    price,
    change,
    changePct,
    high24h,
    low24h,
    lastUpdate,
    priceHistory: price > 0 ? [price] : [],
  };
}

export function useDashboardData(): DashboardState & { refetch: () => void } {
  const [state, setState] = useState<DashboardState>({
    indexes: [],
    commodities: [],
    crypto: [],
    loading: true,
    error: null,
    lastUpdate: null,
  });

  // Track price history across polls
  const historyRef = useRef<Record<string, number[]>>({});

  const appendHistory = useCallback((id: string, price: number): number[] => {
    if (price <= 0) return historyRef.current[id] || [];
    const prev = historyRef.current[id] || [];
    const next = [...prev, price].slice(-MAX_HISTORY);
    historyRef.current[id] = next;
    return next;
  }, []);

  // Fetch A-share indexes
  const fetchIndexes = useCallback(async (): Promise<AssetCardData[]> => {
    const results = await Promise.allSettled(
      INDEX_CODES.map(async ({ code, name }) => {
        const resp = await fetch(buildApiUrl(`/api/index/realtime/${code}`));
        if (!resp.ok) throw new Error(`Index ${code} failed: ${resp.status}`);
        const data: IndexRealtimeData = await resp.json();
        const history = appendHistory(code, data.price);
        return {
          ...toCardData(
            code,
            data.name || name,
            data.price,
            data.change,
            data.change_pct,
            data.last_update,
          ),
          priceHistory: history,
        };
      }),
    );
    return results
      .filter((r): r is PromiseFulfilledResult<AssetCardData> => r.status === "fulfilled")
      .map((r) => r.value);
  }, [appendHistory]);

  // Fetch commodities
  const fetchCommodities = useCallback(async (): Promise<AssetCardData[]> => {
    const resp = await fetch(buildApiUrl("/api/commodities/realtime"));
    if (!resp.ok) throw new Error(`Commodities failed: ${resp.status}`);
    const data: CommoditiesResponse = await resp.json();
    return data.commodities.map((c) => {
      const history = appendHistory(c.symbol, c.price);
      return {
        ...toCardData(
          c.symbol,
          c.name,
          c.price,
          c.change,
          c.change_pct,
          c.last_update,
          c.high_24h,
          c.low_24h,
          c.name_cn,
        ),
        priceHistory: history,
      };
    });
  }, [appendHistory]);

  // Fetch crypto tickers
  const fetchCrypto = useCallback(async (): Promise<AssetCardData[]> => {
    const resp = await fetch(buildApiUrl("/api/crypto/realtime"));
    if (!resp.ok) throw new Error(`Crypto failed: ${resp.status}`);
    const data: CryptoTickersResponse = await resp.json();
    return CRYPTO_SYMBOLS.map((sym) => {
      const ticker = data.tickers.find(
        (t) => t.symbol === sym || t.pair === `${sym}USDT`,
      );
      if (!ticker) {
        return toCardData(sym, sym, 0, 0, 0, "", 0, 0);
      }
      const history = appendHistory(sym, ticker.price);
      return {
        ...toCardData(
          sym,
          sym,
          ticker.price,
          ticker.change_24h,
          ticker.change_pct_24h,
          ticker.last_update,
          ticker.high_24h,
          ticker.low_24h,
        ),
        priceHistory: history,
      };
    }).filter((c) => c.price > 0 || historyRef.current[c.id]?.length);
  }, [appendHistory]);

  const fetchAll = useCallback(async () => {
    try {
      const [indexes, commodities, crypto] = await Promise.all([
        fetchIndexes().catch((e) => {
          console.warn("Index fetch error:", e);
          return [] as AssetCardData[];
        }),
        fetchCommodities().catch((e) => {
          console.warn("Commodity fetch error:", e);
          return [] as AssetCardData[];
        }),
        fetchCrypto().catch((e) => {
          console.warn("Crypto fetch error:", e);
          return [] as AssetCardData[];
        }),
      ]);

      setState((prev) => ({
        indexes: indexes.length ? indexes : prev.indexes,
        commodities: commodities.length ? commodities : prev.commodities,
        crypto: crypto.length ? crypto : prev.crypto,
        loading: false,
        error: null,
        lastUpdate: new Date().toLocaleTimeString(),
      }));
    } catch (e) {
      setState((prev) => ({
        ...prev,
        loading: false,
        error: e instanceof Error ? e.message : "Unknown error",
      }));
    }
  }, [fetchIndexes, fetchCommodities, fetchCrypto]);

  // Crypto-only refresh (more frequent)
  const fetchCryptoOnly = useCallback(async () => {
    try {
      const crypto = await fetchCrypto();
      if (crypto.length) {
        setState((prev) => ({
          ...prev,
          crypto,
          lastUpdate: new Date().toLocaleTimeString(),
        }));
      }
    } catch {
      // silently fail, keep old data
    }
  }, [fetchCrypto]);

  useEffect(() => {
    fetchAll();
    const mainTimer = setInterval(fetchAll, POLL_INTERVAL);
    const cryptoTimer = setInterval(fetchCryptoOnly, CRYPTO_POLL_INTERVAL);
    return () => {
      clearInterval(mainTimer);
      clearInterval(cryptoTimer);
    };
  }, [fetchAll, fetchCryptoOnly]);

  return { ...state, refetch: fetchAll };
}
