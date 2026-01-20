const API_BASE = import.meta.env.VITE_API_BASE || "";

export function buildApiUrl(path: string): string {
  if (path.startsWith("http")) return path;
  const prefix = API_BASE.endsWith("/") ? API_BASE.slice(0, -1) : API_BASE;
  const suffix = path.startsWith("/") ? path : `/${path}`;
  return `${prefix}${suffix}`;
}

export async function apiFetch(input: string, init?: RequestInit): Promise<Response> {
  const url = buildApiUrl(input);
  return fetch(url, init);
}

export const REFRESH_INTERVALS = {
  symbols: 60 * 60 * 1000, // 1h
  watchlist: 30 * 60 * 1000, // 30min (increased from 5min)
  boards: 30 * 60 * 1000, // 30min (increased from 10min)
  portfolio: 30 * 60 * 1000 // 30min (increased from 5min)
};
