/** Types for the Multi-Asset Dashboard */

export interface IndexRealtimeData {
  ts_code: string;
  name: string;
  price: number;
  change: number;
  change_pct: number;
  volume: number;
  amount: number;
  last_update: string;
}

export interface CommodityItem {
  symbol: string;
  name: string;
  name_cn: string;
  unit: string;
  price: number;
  change: number;
  change_pct: number;
  high_24h: number;
  low_24h: number;
  open_price: number;
  prev_close: number;
  last_update: string;
}

export interface CommoditiesResponse {
  count: number;
  source: string;
  last_update: string;
  commodities: CommodityItem[];
}

export interface CryptoTickerItem {
  symbol: string;
  pair: string;
  price: number;
  change_24h: number;
  change_pct_24h: number;
  high_24h: number;
  low_24h: number;
  volume_24h: number;
  quote_volume_24h: number;
  open_price: number;
  trades_count: number;
  last_update: string;
  is_stale: boolean;
  source: string;
}

export interface CryptoTickersResponse {
  count: number;
  source: string;
  tickers: CryptoTickerItem[];
}

/** Unified card data shape for the dashboard */
export interface AssetCardData {
  id: string;
  name: string;
  nameCn?: string;
  price: number;
  change: number;
  changePct: number;
  high24h?: number;
  low24h?: number;
  lastUpdate: string;
  priceHistory: number[]; // for sparkline
}
