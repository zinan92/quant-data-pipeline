import type { CandleBatchResponse, Timeframe } from "../types";
import { SAMPLE_CANDLES } from "../mocks/sampleData";
import { apiFetch } from "../utils/api";

export async function fetchCandles(
  ticker: string,
  timeframe: Timeframe,
  limit: number = 120
): Promise<CandleBatchResponse> {
  try {
    const response = await apiFetch(
      `/api/candles/${ticker}?timeframe=${timeframe}&limit=${limit}`
    );
    if (!response.ok) {
      throw new Error(`Failed to load candles for ${ticker}`);
    }
    return response.json();
  } catch (error) {
    const key = `${ticker}-${timeframe}`;
    console.warn(`Fallback to sample candles for ${key}`, error);
    const sample = SAMPLE_CANDLES[key];
    if (!sample) {
      throw error;
    }
    return sample;
  }
}
