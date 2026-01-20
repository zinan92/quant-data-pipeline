import type { SymbolMeta } from "../types/symbol";
import { SAMPLE_SYMBOLS } from "../mocks/sampleData";
import { apiFetch, REFRESH_INTERVALS } from "../utils/api";

export async function fetchSymbols(): Promise<SymbolMeta[]> {
  try {
    const response = await apiFetch("/api/symbols");
    if (!response.ok) {
      throw new Error("Failed to load symbols");
    }
    return response.json();
  } catch (error) {
    console.warn("Falling back to sample symbols due to", error);
    return SAMPLE_SYMBOLS;
  }
}

export const SYMBOLS_QUERY_CONFIG = {
  staleTime: REFRESH_INTERVALS.symbols,
  refetchInterval: REFRESH_INTERVALS.symbols
};
