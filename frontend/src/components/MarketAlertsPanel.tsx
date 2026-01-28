/**
 * 异动提醒面板组件
 */
import { useEffect, useState } from 'react';

interface AlertItem {
  type: string;
  time: string;
  code: string;
  name: string;
}

interface AlertSummary {
  [key: string]: {
    count: number;
    top: AlertItem[];
  };
}

interface Props {
  refreshInterval?: number;
}

async function fetchAlertsSummary(): Promise<AlertSummary> {
  try {
    const response = await fetch('/api/news/market-alerts');
    if (!response.ok) return {};
    return await response.json();
  } catch {
    return {};
  }
}

const ALERT_ICONS: Record<string, string> = {
  '大笔买入': '🟢',
  '大笔卖出': '🔴',
  '封涨停板': '🔥',
  '封跌停板': '💧',
};

export function MarketAlertsPanel({ refreshInterval = 30000 }: Props) {
  const [summary, setSummary] = useState<AlertSummary>({});
  const [loading, setLoading] = useState(true);
  const [expanded, setExpanded] = useState<string | null>(null);

  useEffect(() => {
    const load = async () => {
      const data = await fetchAlertsSummary();
      setSummary(data);
      setLoading(false);
    };

    load();
    const interval = setInterval(load, refreshInterval);
    return () => clearInterval(interval);
  }, [refreshInterval]);

  if (loading) {
    return <div className="market-alerts-panel market-alerts-panel--loading">加载异动数据...</div>;
  }

  const alertTypes = Object.keys(summary);
  if (alertTypes.length === 0) {
    return null;
  }

  return (
    <div className="market-alerts-panel">
      <h3 className="market-alerts-panel__title">⚡ 盘口异动</h3>
      <div className="market-alerts-panel__grid">
        {alertTypes.map((type) => {
          const data = summary[type];
          const icon = ALERT_ICONS[type] || '📊';
          const isExpanded = expanded === type;

          return (
            <div
              key={type}
              className={`market-alerts-panel__card ${isExpanded ? 'market-alerts-panel__card--expanded' : ''}`}
              onClick={() => setExpanded(isExpanded ? null : type)}
            >
              <div className="market-alerts-panel__card-header">
                <span className="market-alerts-panel__icon">{icon}</span>
                <span className="market-alerts-panel__type">{type}</span>
                <span className="market-alerts-panel__count">{data.count}</span>
              </div>
              {isExpanded && data.top && data.top.length > 0 && (
                <div className="market-alerts-panel__card-body">
                  {data.top.slice(0, 5).map((item, idx) => (
                    <div key={idx} className="market-alerts-panel__item">
                      <span className="market-alerts-panel__item-time">{item.time}</span>
                      <span className="market-alerts-panel__item-code">{item.code}</span>
                      <span className="market-alerts-panel__item-name">{item.name}</span>
                    </div>
                  ))}
                </div>
              )}
            </div>
          );
        })}
      </div>
    </div>
  );
}
