import type { Timeframe } from "./timeframe";

export interface SymbolMeta {
  ticker: string;
  name: string;
  isFocus?: boolean;             // 是否重点关注
  totalMv: number | null;       // 总市值（万元）
  circMv: number | null;         // 流通市值（万元）
  peTtm: number | null;          // 市盈率TTM
  pb: number | null;             // 市净率
  listDate: string | null;       // 上市日期
  industryLv1: string | null;
  industryLv2: string | null;
  industryLv3: string | null;
  concepts: string[];            // 概念板块列表

  // Company information
  introduction: string | null;   // 公司介绍
  mainBusiness: string | null;   // 主要业务
  businessScope: string | null;  // 经营范围
  chairman: string | null;       // 法人代表
  manager: string | null;        // 总经理
  regCapital: number | null;     // 注册资本（万元）
  setupDate: string | null;      // 成立日期
  province: string | null;       // 所在省份
  city: string | null;           // 所在城市
  website: string | null;        // 公司网站

  lastUpdated: string;
  eastmoneyBoard: string[];
}

export interface CandlePoint {
  timestamp: string;
  open: number;
  high: number;
  low: number;
  close: number;
  volume: number | null;
  ma5: number | null;
  ma10: number | null;
  ma20: number | null;
  ma50: number | null;
}

export interface CandleBatchResponse {
  ticker: string;
  timeframe: Timeframe;
  candles: CandlePoint[];
}
