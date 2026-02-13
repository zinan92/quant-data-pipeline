import type { CandleBatchResponse, Timeframe } from "../types";
import { SAMPLE_CANDLES } from "../mocks/sampleData";
import { apiFetch } from "../utils/api";

/**
 * 识别股票交易所类型
 */
function getTickerType(ticker: string): { type: 'A-share' | 'BJ' | 'concept', fullTicker: string } {
  // Remove existing suffixes
  const cleanTicker = ticker.replace(/\.(SH|SZ|BJ|TI)$/, '');
  
  // Beijing Stock Exchange: 8xxxxx, 9xxxxx
  if (/^[89]\d{5}$/.test(cleanTicker)) {
    return { type: 'BJ', fullTicker: `${cleanTicker}.BJ` };
  }
  
  // A-share: 0xxxxx, 3xxxxx (SZ), 6xxxxx (SH)
  if (/^[036]\d{5}$/.test(cleanTicker)) {
    const suffix = cleanTicker.startsWith('6') ? 'SH' : 'SZ';
    return { type: 'A-share', fullTicker: `${cleanTicker}.${suffix}` };
  }
  
  // Concept codes: assume anything else is A-share format
  return { type: 'A-share', fullTicker: ticker };
}

export async function fetchCandles(
  ticker: string,
  timeframe: Timeframe,
  limit: number = 120
): Promise<CandleBatchResponse> {
  const { type, fullTicker } = getTickerType(ticker);
  
  try {
    const response = await apiFetch(
      `/api/candles/${ticker}?timeframe=${timeframe}&limit=${limit}`
    );
    
    if (!response.ok) {
      // Provide specific error messages based on ticker type
      if (type === 'BJ') {
        throw new Error(`北京交易所股票 ${ticker} 数据暂不支持`);
      }
      throw new Error(`Failed to load candles for ${ticker}`);
    }
    
    return response.json();
  } catch (error) {
    const key = `${ticker}-${timeframe}`;
    
    // For BJ stocks, don't fallback to sample data - show the real error
    if (type === 'BJ') {
      throw new Error(`北京交易所股票 ${ticker} K线数据暂不支持。请联系管理员添加数据源。`);
    }
    
    console.warn(`Fallback to sample candles for ${key}`, error);
    const sample = SAMPLE_CANDLES[key];
    if (!sample) {
      throw error;
    }
    return sample;
  }
}
