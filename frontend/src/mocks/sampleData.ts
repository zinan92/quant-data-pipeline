import type { CandleBatchResponse, SymbolMeta, Timeframe } from "../types";

const baseTime = new Date("2024-01-01T00:00:00Z").getTime();

function generateSeries(
  ticker: string,
  timeframe: Timeframe,
  multiplier: number
): CandleBatchResponse {
  const candles = Array.from({ length: 60 }, (_, index) => {
    const open = 80 + Math.sin(index / 5) * multiplier * 2 + index * 0.2;
    const close = open + (Math.random() - 0.5) * multiplier;
    const high = Math.max(open, close) + Math.random() * multiplier;
    const low = Math.min(open, close) - Math.random() * multiplier;
    const volume = 1_000_000 + Math.random() * 100_000;
    return {
      timestamp: new Date(baseTime + index * 24 * 3600 * 1000).toISOString(),
      open: parseFloat(open.toFixed(2)),
      close: parseFloat(close.toFixed(2)),
      high: parseFloat(high.toFixed(2)),
      low: parseFloat(low.toFixed(2)),
      volume,
      turnover: volume * ((open + close) / 2),
      ma5: open + 0.3,
      ma10: open + 0.6,
      ma20: open + 1.0,
      ma50: open + 1.5
    };
  });
  return {
    ticker,
    timeframe,
    candles
  };
}

export const SAMPLE_SYMBOLS: SymbolMeta[] = [
  {
    ticker: "600519",
    name: "贵州茅台",
    totalMv: 24500000,
    circMv: 12500000,
    peTtm: 45.5,
    pb: 12.3,
    listDate: "2001-08-27",
    industryLv1: "白酒",
    industryLv2: null,
    industryLv3: null,
    concepts: ["白酒", "大消费"],
    introduction: "贵州茅台酒股份有限公司",
    mainBusiness: "白酒生产与销售",
    businessScope: "白酒生产销售",
    chairman: "丁雄军",
    manager: "丁雄军",
    regCapital: 125618,
    setupDate: "1999-11-20",
    province: "贵州",
    city: "遵义",
    website: "http://www.moutaichina.com",
    eastmoneyBoard: ["白酒"],
    lastUpdated: new Date().toISOString()
  },
  {
    ticker: "601318",
    name: "中国平安",
    totalMv: 12000000,
    circMv: 11500000,
    peTtm: 8.5,
    pb: 1.2,
    listDate: "2007-03-01",
    industryLv1: "保险",
    industryLv2: null,
    industryLv3: null,
    concepts: ["保险", "金融科技"],
    introduction: "中国平安保险（集团）股份有限公司",
    mainBusiness: "保险、银行、投资",
    businessScope: "保险、金融业务",
    chairman: "马明哲",
    manager: "谢永林",
    regCapital: 1823776,
    setupDate: "1988-03-21",
    province: "广东",
    city: "深圳",
    website: "http://www.pingan.com",
    eastmoneyBoard: ["保险"],
    lastUpdated: new Date().toISOString()
  }
];

export const SAMPLE_CANDLES: Record<string, CandleBatchResponse> = {
  "600519-day": generateSeries("600519", "day", 1.2),
  "601318-day": generateSeries("601318", "day", 0.8),
  "600519-30m": generateSeries("600519", "30m", 1.5),
  "601318-30m": generateSeries("601318", "30m", 1.1)
};
