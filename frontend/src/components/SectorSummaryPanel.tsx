/**
 * 赛道统计面板 - 显示各赛道的汇总统计
 */

import { useMemo } from "react";
import { useQuery } from "@tanstack/react-query";
import { apiFetch } from "../utils/api";

interface RealtimePrice {
  ticker: string;
  price: number;
  change: number;
  changePercent: number;
}

interface SectorStats {
  name: string;
  count: number;
  avgChange: number;
  upCount: number;
  downCount: number;
  flatCount: number;
  limitUpCount: number;
  limitDownCount: number;
  maxGainer: { ticker: string; name: string; change: number } | null;
  maxLoser: { ticker: string; name: string; change: number } | null;
}

interface Props {
  sectorsMap: Map<string, string>;  // ticker -> sector
  realtimePrices: Map<string, RealtimePrice>;
  stockNames: Map<string, string>;  // ticker -> name
  selectedSectors: Set<string>;  // 选中的赛道
  onSectorClick: (sector: string) => void;  // 点击赛道的回调
}

// 赛道排序顺序（将从API动态获取）

export function SectorSummaryPanel({ sectorsMap, realtimePrices, stockNames, selectedSectors, onSectorClick }: Props) {
  // 获取可用赛道列表
  const { data: availableSectorsData } = useQuery<{ sectors: string[] }>({
    queryKey: ["available-sectors"],
    queryFn: async () => {
      const response = await apiFetch("/api/sectors/list/available");
      if (!response.ok) return { sectors: [] };
      return response.json();
    },
    staleTime: 1000 * 60 * 60, // 1小时缓存
  });

  const availableSectors = availableSectorsData?.sectors ?? [];

  // 计算各赛道统计
  const sectorStats = useMemo(() => {
    const stats: Record<string, SectorStats> = {};

    // 初始化所有赛道
    for (const sector of availableSectors) {
      stats[sector] = {
        name: sector,
        count: 0,
        avgChange: 0,
        upCount: 0,
        downCount: 0,
        flatCount: 0,
        limitUpCount: 0,
        limitDownCount: 0,
        maxGainer: null,
        maxLoser: null,
      };
    }

    // 收集每个赛道的涨跌幅
    const sectorChanges: Record<string, number[]> = {};
    for (const sector of availableSectors) {
      sectorChanges[sector] = [];
    }

    // 遍历所有股票（只统计在自选股中的，即有实时价格的）
    for (const [ticker, sector] of sectorsMap.entries()) {
      if (!stats[sector]) continue;

      const price = realtimePrices.get(ticker);
      // 只有在自选股中（有实时价格）的股票才计入统计
      if (!price) continue;

      stats[sector].count++;
      if (price && price.changePercent !== undefined) {
        const change = price.changePercent;
        sectorChanges[sector].push(change);

        // 统计涨跌
        if (change > 0.01) {
          stats[sector].upCount++;
        } else if (change < -0.01) {
          stats[sector].downCount++;
        } else {
          stats[sector].flatCount++;
        }

        // 涨停/跌停 (>=9.9% 或 <=-9.9%)
        if (change >= 9.9) {
          stats[sector].limitUpCount++;
        } else if (change <= -9.9) {
          stats[sector].limitDownCount++;
        }

        // 最大涨幅/跌幅
        const stockName = stockNames.get(ticker) || ticker;
        if (!stats[sector].maxGainer || change > stats[sector].maxGainer.change) {
          stats[sector].maxGainer = { ticker, name: stockName, change };
        }
        if (!stats[sector].maxLoser || change < stats[sector].maxLoser.change) {
          stats[sector].maxLoser = { ticker, name: stockName, change };
        }
      }
    }

    // 计算平均涨跌幅
    for (const sector of availableSectors) {
      const changes = sectorChanges[sector];
      if (changes.length > 0) {
        stats[sector].avgChange = changes.reduce((a, b) => a + b, 0) / changes.length;
      }
    }

    // 按平均涨跌幅排序（保持基本顺序，但涨幅高的靠前）
    return availableSectors
      .map(sector => stats[sector])
      .filter(s => s.count > 0)
      .sort((a, b) => b.avgChange - a.avgChange);
  }, [sectorsMap, realtimePrices, stockNames, availableSectors]);

  if (sectorStats.length === 0) {
    return (
      <div className="sector-panel">
        <div className="sector-panel__loading">加载赛道数据...</div>
      </div>
    );
  }

  return (
    <div className="sector-panel">
      <h3 className="sector-panel__title">赛道统计</h3>
      <div className="sector-panel__grid">
        {sectorStats.map((stat) => {
          const isPositive = stat.avgChange >= 0;
          const isSelected = selectedSectors.has(stat.name);

          return (
            <div
              key={stat.name}
              className={`sector-card ${isSelected ? 'sector-card--selected' : ''}`}
              onClick={() => onSectorClick(stat.name)}
            >
              <div className="sector-card__header">
                <span className="sector-card__name">
                  {stat.name}
                </span>
                <span className="sector-card__count">{stat.count}支</span>
              </div>

              <div className="sector-card__avg">
                <span className={`sector-card__avg-value ${isPositive ? 'sector-card__avg-value--up' : 'sector-card__avg-value--down'}`}>
                  {isPositive ? '+' : ''}{stat.avgChange.toFixed(2)}%
                </span>
              </div>

              <div className="sector-card__stats">
                <span className="sector-card__stat sector-card__stat--up">
                  ↑{stat.upCount}
                </span>
                <span className="sector-card__stat sector-card__stat--down">
                  ↓{stat.downCount}
                </span>
                {stat.limitUpCount > 0 && (
                  <span className="sector-card__stat sector-card__stat--limit-up">
                    涨停{stat.limitUpCount}
                  </span>
                )}
                {stat.limitDownCount > 0 && (
                  <span className="sector-card__stat sector-card__stat--limit-down">
                    跌停{stat.limitDownCount}
                  </span>
                )}
              </div>

              {stat.maxGainer && stat.maxGainer.change > 0 && (
                <div className="sector-card__extreme">
                  <span className="sector-card__extreme-label">领涨:</span>
                  <span className="sector-card__extreme-name">{stat.maxGainer.name}</span>
                  <span className="sector-card__extreme-value sector-card__extreme-value--up">
                    +{stat.maxGainer.change.toFixed(2)}%
                  </span>
                </div>
              )}

              {stat.maxLoser && stat.maxLoser.change < 0 && (
                <div className="sector-card__extreme">
                  <span className="sector-card__extreme-label">领跌:</span>
                  <span className="sector-card__extreme-name">{stat.maxLoser.name}</span>
                  <span className="sector-card__extreme-value sector-card__extreme-value--down">
                    {stat.maxLoser.change.toFixed(2)}%
                  </span>
                </div>
              )}
            </div>
          );
        })}
      </div>
    </div>
  );
}
