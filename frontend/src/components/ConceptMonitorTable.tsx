import { useConceptMonitor, ConceptData } from '../hooks/useConceptMonitor';

interface ConceptMonitorTableProps {
  type: 'top' | 'watch';
  topN?: number;
}

export function ConceptMonitorTable({ type, topN = 20 }: ConceptMonitorTableProps) {
  const { data, timestamp, loading, error } = useConceptMonitor({
    type,
    topN: type === 'top' ? 20 : topN, // 涨幅TOP固定20个
    interval: 150000, // 2.5分钟
    enabled: true
  });

  // 格式化数字
  const formatNumber = (value: number, decimals: number = 2): string => {
    if (value === 0 || value === null || value === undefined) return '-';
    return value.toFixed(decimals);
  };

  // 格式化百分比
  const formatPercent = (value: number): string => {
    if (value === 0 || value === null || value === undefined) return '-';
    const sign = value > 0 ? '+' : '';
    return `${sign}${value.toFixed(2)}%`;
  };

  // 格式化资金流（亿元）
  const formatMoney = (value: number): string => {
    if (value === 0 || value === null || value === undefined) return '-';
    return `${value > 0 ? '+' : ''}${value.toFixed(2)}亿`;
  };

  // 获取涨跌颜色
  const getColor = (value: number): string => {
    if (value > 0) return 'text-red-500';
    if (value < 0) return 'text-green-500';
    return 'text-gray-400';
  };

  if (loading && data.length === 0) {
    return (
      <div className="concept-monitor-panel">
        <div className="text-center text-gray-500 py-8">加载中...</div>
      </div>
    );
  }

  if (error) {
    return (
      <div className="concept-monitor-panel">
        <div className="text-center text-red-500 py-8">
          ❌ {error}
        </div>
      </div>
    );
  }

  const title = type === 'top' ? `涨幅TOP20` : '自选热门';

  return (
    <div className="concept-monitor-panel">
      {/* 表头 */}
      <div className="concept-monitor-panel__header">
        <h3 className="concept-monitor-panel__title">{title}</h3>
        <span className="concept-monitor-panel__timestamp">{timestamp}</span>
      </div>

      {/* 表格 */}
      <div className="concept-monitor-panel__content">
        <table className="concept-monitor-table">
          <thead>
            <tr>
              <th className="text-center w-8">#</th>
              <th className="text-left">板块名称</th>
              <th className="text-right">涨幅</th>
              <th className="text-right">主力资金</th>
              <th className="text-center">涨停</th>
              <th className="text-center">涨/跌</th>
              <th className="text-right">5日</th>
              <th className="text-right">10日</th>
              <th className="text-right">20日</th>
              <th className="text-right">成交额</th>
              <th className="text-right">成交量</th>
            </tr>
          </thead>
          <tbody>
            {data.map((row: ConceptData) => (
              <tr key={row.code}>
                <td className="text-center text-gray-500 font-mono text-xs">{row.rank}</td>
                <td className="concept-name">
                  {row.name}
                </td>
                <td className={`text-right font-mono font-semibold ${getColor(row.changePct)}`}>
                  {formatPercent(row.changePct)}
                </td>
                <td className={`text-right font-mono text-xs ${getColor(row.moneyInflow)}`}>
                  {formatMoney(row.moneyInflow)}
                </td>
                <td className="text-center">
                  {row.limitUp > 0 && (
                    <span className="limit-up-badge">{row.limitUp}</span>
                  )}
                  {row.limitUp === 0 && (
                    <span className="text-gray-600">-</span>
                  )}
                </td>
                <td className="text-center text-xs">
                  <span className="text-red-500 font-medium">{row.upCount}</span>
                  <span className="text-gray-600 mx-0.5">/</span>
                  <span className="text-green-500 font-medium">{row.downCount}</span>
                </td>
                <td className={`text-right font-mono text-xs ${getColor(row.day5Change)}`}>
                  {formatPercent(row.day5Change)}
                </td>
                <td className={`text-right font-mono text-xs ${getColor(row.day10Change)}`}>
                  {formatPercent(row.day10Change)}
                </td>
                <td className={`text-right font-mono text-xs ${getColor(row.day20Change)}`}>
                  {formatPercent(row.day20Change)}
                </td>
                <td className="text-right font-mono text-xs text-gray-400">
                  {formatNumber(row.turnover, 1)}亿
                </td>
                <td className="text-right font-mono text-xs text-gray-400">
                  {formatNumber(row.volume, 0)}万
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      {/* 无数据提示 */}
      {data.length === 0 && !loading && (
        <div className="text-center text-gray-500 py-8">暂无数据</div>
      )}
    </div>
  );
}
