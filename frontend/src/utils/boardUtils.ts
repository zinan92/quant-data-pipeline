/**
 * 股票板块判断工具函数
 * 用于根据股票代码判断所属板块（创业板、科创板等）
 */

export type BoardType = 'KCB' | 'CYB' | 'BJ' | 'SH' | 'SZ';

export interface BoardInfo {
  type: BoardType;
  label: string;      // 显示标签
  className: string;  // CSS类名
  tradable: boolean;  // 是否可交易（对于不能交易创业板/科创板的用户）
}

/**
 * 根据ticker判断股票所属板块
 * @param ticker 股票代码（支持带后缀和不带后缀）
 * @returns 板块信息
 */
export function getBoardInfo(ticker: string): BoardInfo {
  const code = ticker.split('.')[0]; // 去除后缀

  if (code.startsWith('688') || code.startsWith('689')) {
    return {
      type: 'KCB',
      label: '科',
      className: 'board-tag--kcb',
      tradable: false
    };
  }

  if (code.startsWith('300') || code.startsWith('301')) {
    return {
      type: 'CYB',
      label: '创',
      className: 'board-tag--cyb',
      tradable: false
    };
  }

  if (code.startsWith('8') || code.startsWith('4')) {
    return {
      type: 'BJ',
      label: '北',
      className: 'board-tag--bj',
      tradable: true
    };
  }

  if (code.startsWith('6')) {
    return {
      type: 'SH',
      label: '',
      className: '',
      tradable: true
    };
  }

  // 深圳主板 (000, 001, 002)
  return {
    type: 'SZ',
    label: '',
    className: '',
    tradable: true
  };
}

/**
 * 判断是否为创业板或科创板（不可交易）
 */
export function isRestrictedBoard(ticker: string): boolean {
  const info = getBoardInfo(ticker);
  return !info.tradable;
}

/**
 * 获取板块标签（仅返回创业板和科创板的标签）
 */
export function getBoardLabel(ticker: string): string | null {
  const info = getBoardInfo(ticker);
  return info.label || null;
}
