/**
 * 技术指标计算工具
 * 统一的 MA、EMA、MACD 等指标计算函数
 */

/**
 * 计算简单移动平均线 (SMA)
 */
export function calculateMA(data: number[], period: number): (number | null)[] {
  const result: (number | null)[] = [];
  for (let i = 0; i < data.length; i++) {
    if (i < period - 1) {
      result.push(null);
    } else {
      let sum = 0;
      for (let j = 0; j < period; j++) {
        sum += data[i - j];
      }
      result.push(sum / period);
    }
  }
  return result;
}

/**
 * 计算指数移动平均线 (EMA)
 */
export function calculateEMA(data: number[], period: number): number[] {
  const result: number[] = [];
  const multiplier = 2 / (period + 1);

  // 第一个值用 SMA
  let sum = 0;
  for (let i = 0; i < Math.min(period, data.length); i++) {
    sum += data[i];
  }

  // 填充前面的值
  for (let i = 0; i < period - 1; i++) {
    result.push(sum / period);
  }
  result.push(sum / period);

  // 之后用 EMA 公式
  for (let i = period; i < data.length; i++) {
    const ema = (data[i] - result[i - 1]) * multiplier + result[i - 1];
    result.push(ema);
  }

  return result;
}

/**
 * MACD 计算结果
 */
export interface MACDResult {
  dif: (number | null)[];
  dea: (number | null)[];
  macd: (number | null)[];
}

/**
 * 计算 MACD 指标
 * @param closes 收盘价数组
 * @param fastPeriod 快线周期，默认 12
 * @param slowPeriod 慢线周期，默认 26
 * @param signalPeriod 信号线周期，默认 9
 */
export function calculateMACD(
  closes: number[],
  fastPeriod = 12,
  slowPeriod = 26,
  signalPeriod = 9
): MACDResult {
  if (closes.length < slowPeriod) {
    return {
      dif: closes.map(() => null),
      dea: closes.map(() => null),
      macd: closes.map(() => null),
    };
  }

  const emaFast = calculateEMA(closes, fastPeriod);
  const emaSlow = calculateEMA(closes, slowPeriod);

  // DIF = EMA(fast) - EMA(slow)
  const difValues: number[] = [];
  for (let i = 0; i < closes.length; i++) {
    difValues.push(emaFast[i] - emaSlow[i]);
  }

  // DEA = EMA(DIF, signalPeriod)
  const deaValues = calculateEMA(difValues, signalPeriod);

  // 构建结果，前 slowPeriod-1 个值为 null
  const dif: (number | null)[] = [];
  const dea: (number | null)[] = [];
  const macd: (number | null)[] = [];

  for (let i = 0; i < closes.length; i++) {
    if (i < slowPeriod - 1) {
      dif.push(null);
      dea.push(null);
      macd.push(null);
    } else {
      dif.push(difValues[i]);
      dea.push(deaValues[i]);
      macd.push((difValues[i] - deaValues[i]) * 2);
    }
  }

  return { dif, dea, macd };
}

/**
 * 检测金叉死叉
 */
export interface CrossSignal {
  index: number;
  type: 'golden' | 'death';  // 金叉 or 死叉
  price: number;
}

export function detectCrosses(
  dif: (number | null)[],
  dea: (number | null)[]
): CrossSignal[] {
  const signals: CrossSignal[] = [];

  for (let i = 1; i < dif.length; i++) {
    const prevDif = dif[i - 1];
    const currDif = dif[i];
    const prevDea = dea[i - 1];
    const currDea = dea[i];

    if (prevDif === null || currDif === null || prevDea === null || currDea === null) {
      continue;
    }

    // 金叉：DIF 从下往上穿过 DEA
    if (prevDif <= prevDea && currDif > currDea) {
      signals.push({ index: i, type: 'golden', price: currDif });
    }
    // 死叉：DIF 从上往下穿过 DEA
    else if (prevDif >= prevDea && currDif < currDea) {
      signals.push({ index: i, type: 'death', price: currDif });
    }
  }

  return signals;
}
