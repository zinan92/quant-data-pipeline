import { useMemo } from "react";
import ReactECharts from "echarts-for-react";
import { useQuery } from "@tanstack/react-query";
import { apiFetch, REFRESH_INTERVALS } from "../utils/api";

interface Industry {
  name: string;
  note: string;
}

interface SuperCategory {
  name: string;
  score: number;
  industries: Industry[];
  total_mv?: number;
  pct_change?: number;
  trade_date?: string;
}

interface SuperCategoriesData {
  offensive: SuperCategory[];
  defensive: SuperCategory[];
  total_categories: number;
  offensive_count: number;
  defensive_count: number;
  last_update_time?: string;
}

interface Props {
  onBoardClick: (boardName: string) => void;
}

async function fetchSuperCategories(): Promise<SuperCategoriesData> {
  const response = await apiFetch("/api/boards/super-categories");
  if (!response.ok) {
    throw new Error("Failed to fetch super categories");
  }
  return response.json();
}

export function MarketHeatMap({ onBoardClick }: Props) {
  const { data: categoriesData, isLoading, error } = useQuery({
    queryKey: ["super-categories"],
    queryFn: fetchSuperCategories,
    staleTime: REFRESH_INTERVALS.boards,
    refetchInterval: REFRESH_INTERVALS.boards
  });

  const option = useMemo(() => {
    if (!categoriesData) return {};

    const allCategories = [...categoriesData.offensive, ...categoriesData.defensive];

    // 准备热力图数据
    const data = allCategories.map(category => {
      const pctChange = category.pct_change ?? 0;
      const pctChangeValue = pctChange * 100;

      // 根据涨跌幅计算颜色
      const getColor = (change: number) => {
        if (change <= -3) return "#7f1d1d";      // 深红 <= -3%
        if (change <= -2) return "#991b1b";
        if (change <= -1.5) return "#b91c1c";
        if (change <= -1) return "#dc2626";
        if (change <= -0.5) return "#ef4444";    // 红色
        if (change <= -0.2) return "#f87171";
        if (change < 0) return "#fca5a5";        // 淡红
        if (change === 0) return "#475569";      // 灰色
        if (change < 0.2) return "#a7f3d0";      // 淡绿
        if (change < 0.5) return "#6ee7b7";
        if (change < 1) return "#34d399";
        if (change < 1.5) return "#10b981";      // 绿色
        if (change < 2) return "#059669";
        if (change < 3) return "#047857";
        return "#065f46";                         // 深绿 >= 3%
      };

      return {
        name: category.name,
        value: category.total_mv ?? 0,
        pct_change: pctChange,
        score: category.score,
        itemStyle: {
          color: getColor(pctChangeValue)
        }
      };
    });

    return {
      tooltip: {
        formatter: (params: any) => {
          const { name, value, data } = params;
          const pctChange = data.pct_change * 100;
          const score = data.score;
          const mv = (value / 10000).toFixed(0);
          return `
            <div style="font-size: 14px;">
              <strong>${name}</strong><br/>
              市值：${mv}亿<br/>
              涨跌幅：<span style="color: ${pctChange >= 0 ? '#14b8a6' : '#ef4444'}">${pctChange >= 0 ? '+' : ''}${pctChange.toFixed(2)}%</span><br/>
              评分：${score}
            </div>
          `;
        }
      },
      series: [
        {
          type: "treemap",
          data: data,
          roam: false,
          nodeClick: "link",
          breadcrumb: {
            show: false
          },
          label: {
            show: true,
            formatter: (params: any) => {
              const { name, data } = params;
              const pctChange = data.pct_change * 100;
              return `{name|${name}}\n{change|${pctChange >= 0 ? '+' : ''}${pctChange.toFixed(2)}%}`;
            },
            rich: {
              name: {
                fontSize: 14,
                fontWeight: "bold",
                color: "#fff",
                lineHeight: 20
              },
              change: {
                fontSize: 12,
                color: "#fff",
                lineHeight: 18
              }
            }
          },
          upperLabel: {
            show: false
          },
          itemStyle: {
            borderColor: "#1e293b",
            borderWidth: 2,
            gapWidth: 2
          },
          levels: [
            {
              itemStyle: {
                borderWidth: 0,
                gapWidth: 5
              }
            },
            {
              itemStyle: {
                gapWidth: 1
              }
            }
          ]
        }
      ]
    };
  }, [categoriesData]);

  const onEvents = useMemo(() => ({
    click: (params: any) => {
      if (params.data && params.data.name) {
        // 这里暂时不处理点击，因为热力图显示的是超级行业组
        // 如果需要，可以扩展为点击后展开显示该组内的细分行业
        console.log("Clicked category:", params.data.name);
      }
    }
  }), [onBoardClick]);

  if (isLoading) {
    return (
      <div className="market-heatmap__loading">
        加载热力图数据...
      </div>
    );
  }

  if (error) {
    return (
      <div className="market-heatmap__error">
        加载热力图失败: {(error as Error).message}
      </div>
    );
  }

  // 格式化日期显示
  const formatDate = (dateStr: string) => {
    if (!dateStr) return "";
    if (dateStr.length === 8) {
      return `${dateStr.slice(0, 4)}-${dateStr.slice(4, 6)}-${dateStr.slice(6, 8)}`;
    }
    return dateStr;
  };

  return (
    <div className="market-heatmap">
      <div className="market-heatmap__header">
        <div className="market-heatmap__title-section">
          <h3 className="market-heatmap__title">市场全景热力图</h3>
          {categoriesData?.last_update_time && (
            <span className="market-heatmap__update-time">
              更新: {formatDate(categoriesData.last_update_time)}
            </span>
          )}
        </div>
      </div>

      <div className="market-heatmap__content">
        <ReactECharts
          option={option}
          style={{ height: "400px", width: "100%" }}
          onEvents={onEvents}
          notMerge={true}
          lazyUpdate={true}
        />
      </div>

      {/* 图例移到底部 */}
      <div className="market-heatmap__footer">
        <div className="market-heatmap__legend">
          <span className="market-heatmap__legend-item">
            <span className="market-heatmap__legend-color market-heatmap__legend-color--down"></span>
            下跌
          </span>
          <span className="market-heatmap__legend-item">
            <span className="market-heatmap__legend-color market-heatmap__legend-color--flat"></span>
            平盘
          </span>
          <span className="market-heatmap__legend-item">
            <span className="market-heatmap__legend-color market-heatmap__legend-color--up"></span>
            上涨
          </span>
        </div>
        <span className="market-heatmap__legend-note">面积 = 市值规模</span>
      </div>
    </div>
  );
}
