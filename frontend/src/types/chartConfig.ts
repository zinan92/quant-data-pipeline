/**
 * K线图配置类型定义
 */

// 均线配置
export interface MAConfig {
  ma5: boolean;
  ma10: boolean;
  ma20: boolean;
  ma50: boolean;
}

// 均线颜色配置
export const MA_COLORS = {
  ma5: "#ffd064",   // 黄色
  ma10: "#5fb0ff",  // 蓝色
  ma20: "#a98bff",  // 紫色
  ma50: "#ff8ba7",  // 粉色
} as const;

// 均线标签
export const MA_LABELS = {
  ma5: "MA5",
  ma10: "MA10",
  ma20: "MA20",
  ma50: "MA50",
} as const;

// 图表配置
export interface ChartConfig {
  // 均线设置
  maConfig: MAConfig;
  // 是否显示成交量
  showVolume: boolean;
  // 是否显示MACD（仅指数图表使用）
  showMACD: boolean;
}

// 默认配置
export const DEFAULT_MA_CONFIG: MAConfig = {
  ma5: true,
  ma10: true,
  ma20: true,
  ma50: true,
};

export const DEFAULT_CHART_CONFIG: ChartConfig = {
  maConfig: DEFAULT_MA_CONFIG,
  showVolume: true,
  showMACD: true,
};

// 辅助函数：检查是否有任何均线启用
export function hasAnyMAEnabled(config: MAConfig): boolean {
  return config.ma5 || config.ma10 || config.ma20 || config.ma50;
}

// 辅助函数：获取启用的均线列表
export function getEnabledMAList(config: MAConfig): (keyof MAConfig)[] {
  return (Object.keys(config) as (keyof MAConfig)[]).filter(key => config[key]);
}
