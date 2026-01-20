import { useEffect, useState } from "react";
import { buildApiUrl } from "../utils/api";

interface RealtimePrice {
  ticker: string;
  price: number;
  change: number;
  changePercent: number;
  lastUpdate: string;
}

interface UseRealtimePriceOptions {
  tickers: string[];
  interval?: number; // 轮询间隔（毫秒），默认60秒
  enabled?: boolean; // 是否启用
}

/**
 * 检查当前是否在交易时间
 * A股交易时间：9:30-11:30, 13:00-15:00
 */
export function isMarketOpen(): boolean {
  const now = new Date();
  const day = now.getDay();

  // 周末不交易
  if (day === 0 || day === 6) {
    return false;
  }

  const hours = now.getHours();
  const minutes = now.getMinutes();
  const time = hours * 100 + minutes;

  // 9:30-11:30 或 13:00-15:00
  return (time >= 930 && time <= 1130) || (time >= 1300 && time <= 1500);
}

/**
 * 将股票代码转换为新浪财经API格式
 * 例如: 000001 -> sz000001, 600000 -> sh600000
 * Returns null for unsupported tickers
 */
function convertToSinaFormat(ticker: string): string | null {
  // Skip Beijing Stock Exchange (8/9 prefix) and other unsupported tickers
  if (ticker.startsWith('8') || ticker.startsWith('9')) {
    return null;
  }
  if (ticker.startsWith('6')) {
    return `sh${ticker}`;
  } else if (ticker.startsWith('0') || ticker.startsWith('3')) {
    return `sz${ticker}`;
  }
  return null;  // Unsupported ticker
}

/**
 * 解析新浪财经API返回的数据
 * 格式: var hq_str_sh600000="浦发银行,9.02,9.03,9.13,9.14,9.01,9.12,9.13,..."
 */
function parseSinaData(response: string): Map<string, RealtimePrice> {
  const result = new Map<string, RealtimePrice>();
  const lines = response.split('\n').filter(line => line.trim());

  for (const line of lines) {
    try {
      const match = line.match(/var hq_str_(s[hz]\d{6})="(.+)";/);
      if (!match) continue;

      const sinaCode = match[1];
      const data = match[2].split(',');

      if (data.length < 32) continue;

      // 提取原始ticker (去掉sh/sz前缀)
      const ticker = sinaCode.substring(2);

      const currentPrice = parseFloat(data[3]); // 当前价
      const prevClose = parseFloat(data[2]); // 昨收

      // 市场休市时当前价为0，使用昨收价
      const displayPrice = currentPrice > 0 ? currentPrice : prevClose;
      const change = currentPrice > 0 ? currentPrice - prevClose : 0;
      const changePercent = currentPrice > 0 && prevClose > 0 ? (change / prevClose) * 100 : 0;

      const priceData = {
        ticker,
        price: displayPrice,
        change,
        changePercent,
        lastUpdate: new Date().toLocaleTimeString('zh-CN')
      };

      result.set(ticker, priceData);
    } catch (error) {
      console.error('Failed to parse Sina data:', line, error);
    }
  }

  return result;
}

/**
 * 从新浪财经获取实时价格（通过后端代理）
 * 新浪API有大约170个股票的限制，需要分批请求
 */
const BATCH_SIZE = 100; // 每批最多100个股票

async function fetchRealtimePrice(tickers: string[]): Promise<Map<string, RealtimePrice>> {
  // Filter out unsupported tickers (BSE stocks, etc.)
  const supportedTickers = tickers.filter(t => convertToSinaFormat(t) !== null);

  if (supportedTickers.length === 0) {
    return new Map();
  }

  const result = new Map<string, RealtimePrice>();

  // 分批请求
  const batches: string[][] = [];
  for (let i = 0; i < supportedTickers.length; i += BATCH_SIZE) {
    batches.push(supportedTickers.slice(i, i + BATCH_SIZE));
  }

  // 并行请求所有批次
  const fetchBatch = async (batch: string[]): Promise<Map<string, RealtimePrice>> => {
    const tickerStr = batch.join(',');
    const url = buildApiUrl(`/api/realtime/prices?tickers=${encodeURIComponent(tickerStr)}`);

    try {
      const response = await fetch(url, {
        method: 'GET',
        cache: 'no-cache'
      });

      if (!response.ok) {
        console.error('Failed to fetch realtime price batch:', response.status);
        return new Map();
      }

      const json = await response.json();
      return parseSinaData(json.data);
    } catch (error) {
      console.error('Failed to fetch realtime price batch:', error);
      return new Map();
    }
  };

  try {
    // Fetch batches sequentially with delay to avoid rate limiting
    const batchResults: Map<string, RealtimePrice>[] = [];
    for (let i = 0; i < batches.length; i++) {
      const batchResult = await fetchBatch(batches[i]);
      batchResults.push(batchResult);

      // Add 200ms delay between batches to avoid rate limiting
      if (i < batches.length - 1) {
        await new Promise(resolve => setTimeout(resolve, 200));
      }
    }

    // 合并所有批次的结果
    for (const batchResult of batchResults) {
      for (const [ticker, price] of batchResult) {
        result.set(ticker, price);
      }
    }
  } catch (error) {
    console.error('Failed to fetch realtime prices:', error);
  }

  return result;
}

/**
 * 使用实时价格Hook
 *
 * @param options - 配置选项
 * @returns 实时价格数据的Map
 *
 * @example
 * const prices = useRealtimePrice({
 *   tickers: ['000001', '600000'],
 *   interval: 60000, // 60秒
 *   enabled: true
 * });
 */
export function useRealtimePrice(options: UseRealtimePriceOptions): Map<string, RealtimePrice> {
  const { tickers, interval = 60000, enabled = true } = options;
  const [prices, setPrices] = useState<Map<string, RealtimePrice>>(new Map());

  useEffect(() => {
    // 如果未启用或没有股票代码，不执行
    if (!enabled || tickers.length === 0) {
      return;
    }

    const marketOpen = isMarketOpen();

    // 立即获取一次数据（无论是否在交易时间）
    // 非交易时间会返回最后一个交易日的收盘价
    let isMounted = true;
    fetchRealtimePrice(tickers).then((data) => {
      if (isMounted) {
        setPrices(data);
      }
    });

    // 始终启动轮询，内部再判断是否处于交易时段。
    // 原逻辑在非交易时段直接返回，导致页面早上打开后即使后来开盘也不会开始轮询。
    if (!marketOpen) {
      console.log("[Real-time] Market is closed, waiting to start polling when market opens");
    } else {
      console.log("[Real-time] Market is open, starting polling");
    }

    const intervalId = setInterval(() => {
      if (isMarketOpen()) {
        fetchRealtimePrice(tickers).then((data) => {
          if (isMounted) {
            setPrices(data);
          }
        });
      }
    }, interval);

    // 清理
    return () => {
      isMounted = false;
      clearInterval(intervalId);
    };
  }, [tickers, interval, enabled]);

  return prices;
}
