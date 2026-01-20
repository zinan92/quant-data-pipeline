import { useQuery } from "@tanstack/react-query";
import { apiFetch, REFRESH_INTERVALS } from "../utils/api";

interface BoardStatsData {
  板块名称: string;
  板块代码: string;
  股票数量: number;
  上涨家数: number;
  下跌家数: number;
  平仓家数: number;
  加权平均PE: number | null;
  PE中位数: number | null;
  总市值: number;
  涨跌幅: number;
  龙头公司: {
    ticker: string;
    name: string;
    market_cap: number;
  } | null;
  市值增长: {
    "5天": number | null;
    "2周": number | null;
    "30天": number | null;
    "3个月": number | null;
    "6个月": number | null;
  };
  交易日期: string;
}

interface Props {
  boardName: string;
}

async function fetchBoardStats(boardName: string): Promise<BoardStatsData> {
  const response = await apiFetch(
    `/api/boards/${encodeURIComponent(boardName)}/stats`
  );
  if (!response.ok) {
    throw new Error("Failed to fetch board stats");
  }
  return response.json();
}

export function BoardStats({ boardName }: Props) {
  const { data, isLoading, error } = useQuery({
    queryKey: ["boardStats", boardName],
    queryFn: () => fetchBoardStats(boardName),
    staleTime: REFRESH_INTERVALS.boards,
    refetchInterval: REFRESH_INTERVALS.boards
  });

  if (isLoading) {
    return (
      <div className="board-stats board-stats--loading">
        加载板块信息...
      </div>
    );
  }

  if (error || !data) {
    return null;
  }

  const formatMarketCap = (mv: number) => {
    // mv单位是万元，转换为亿元需要除以10000
    return `${(mv / 1e4).toFixed(0)}亿`;
  };

  const formatGrowth = (value: number | null) => {
    if (value === null) return "N/A";
    const sign = value >= 0 ? "+" : "";
    return `${sign}${value.toFixed(2)}%`;
  };

  const getGrowthClass = (value: number | null) => {
    if (value === null) return "";
    return value >= 0 ? "board-stats__growth--positive" : "board-stats__growth--negative";
  };

  return (
    <div className="board-stats">
      <div className="board-stats__grid">
        <div className="board-stats__card">
          <div className="board-stats__label">股票数量</div>
          <div className="board-stats__value">{data.股票数量}</div>
        </div>
        <div className="board-stats__card board-stats__card--up">
          <div className="board-stats__label">上涨</div>
          <div className="board-stats__value">{data.上涨家数}</div>
        </div>
        <div className="board-stats__card board-stats__card--down">
          <div className="board-stats__label">下跌</div>
          <div className="board-stats__value">{data.下跌家数}</div>
        </div>
        <div className="board-stats__card">
          <div className="board-stats__label">平盘</div>
          <div className="board-stats__value">{data.平仓家数}</div>
        </div>
        <div className="board-stats__card">
          <div className="board-stats__label">平均PE</div>
          <div className="board-stats__value">
            {data.加权平均PE ? data.加权平均PE.toFixed(1) : "N/A"}
          </div>
        </div>
        <div className="board-stats__card">
          <div className="board-stats__label">PE中位数</div>
          <div className="board-stats__value">
            {data.PE中位数 ? data.PE中位数.toFixed(1) : "N/A"}
          </div>
        </div>
        <div className="board-stats__card">
          <div className="board-stats__label">总市值</div>
          <div className="board-stats__value">{formatMarketCap(data.总市值)}</div>
        </div>
        {data.龙头公司 && (
          <div className="board-stats__card board-stats__card--leader">
            <div className="board-stats__label">龙头</div>
            <div className="board-stats__value board-stats__value--leader">
              {data.龙头公司.name}
            </div>
          </div>
        )}
      </div>
    </div>
  );
}
