import { useQuery } from "@tanstack/react-query";
import { BoardCard } from "./BoardCard";
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

interface IndustryData {
  板块名称: string;
  股票数量: number;
  总市值: number;
  涨跌幅: number;
  上涨家数: number;
  下跌家数: number;
  行业PE: number | null;
}

interface BoardData {
  排名: number;
  板块名称: string;
  板块代码: string;
  最新价: number;
  涨跌额: number;
  涨跌幅: number;
  总市值: number;
  换手率: number;
  上涨家数: number;
  下跌家数: number;
  领涨股票: string;
  "领涨股票-涨跌幅": number;
  行业PE?: number | null;
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

interface IndustriesResponse {
  data: IndustryData[];
  last_update_time: string;
}

async function fetchIndustries(): Promise<IndustriesResponse> {
  const response = await apiFetch("/api/symbols/industries");
  if (!response.ok) {
    throw new Error("Failed to fetch industries");
  }
  return response.json();
}

export function SuperCategoryView({ onBoardClick }: Props) {
  const { data: categoriesData, isLoading: categoriesLoading, error: categoriesError } = useQuery({
    queryKey: ["super-categories"],
    queryFn: fetchSuperCategories,
    staleTime: REFRESH_INTERVALS.boards,
    refetchInterval: REFRESH_INTERVALS.boards
  });

  const { data: industriesData, isLoading: industriesLoading, error: industriesError } = useQuery({
    queryKey: ["industries"],
    queryFn: fetchIndustries,
    staleTime: REFRESH_INTERVALS.boards,
    refetchInterval: REFRESH_INTERVALS.boards
  });

  if (categoriesLoading || industriesLoading) {
    return (
      <div className="super-category-view__loading">
        加载超级行业组...
      </div>
    );
  }

  if (categoriesError || industriesError) {
    return (
      <div className="super-category-view__error">
        加载失败: {((categoriesError || industriesError) as Error).message}
      </div>
    );
  }

  if (!categoriesData || !industriesData) {
    return null;
  }

  // 将行业数据转换为 Map，方便查找
  const industryMap = new Map<string, IndustryData>();
  industriesData.data.forEach(ind => {
    industryMap.set(ind.板块名称, ind);
  });

  // 为每个超级分类获取其行业的 BoardCard 数据
  const getBoardsForCategory = (category: SuperCategory): BoardData[] => {
    return category.industries
      .map((ind, idx) => {
        const industryData = industryMap.get(ind.name);
        if (!industryData) return null;

        return {
          排名: idx + 1,
          板块名称: industryData.板块名称,
          板块代码: `IND_${ind.name}`,
          最新价: 0,
          涨跌额: 0,
          涨跌幅: industryData.涨跌幅,
          总市值: industryData.总市值,
          换手率: 0,
          上涨家数: industryData.上涨家数,
          下跌家数: industryData.下跌家数,
          领涨股票: "",
          "领涨股票-涨跌幅": 0,
          行业PE: industryData.行业PE ?? null,
        } as BoardData;
      })
      .filter((board): board is BoardData => board !== null);
  };

  // 格式化日期显示
  const formatDate = (dateStr: string) => {
    if (!dateStr) return "未知";
    // 格式：YYYYMMDD -> YYYY-MM-DD
    if (dateStr.length === 8) {
      return `${dateStr.slice(0, 4)}-${dateStr.slice(4, 6)}-${dateStr.slice(6, 8)}`;
    }
    return dateStr;
  };

  return (
    <div className="super-category-view">
      <div className="super-category-view__header">
        <h2>A股超级行业组分类</h2>
        <p className="super-category-view__subtitle">
          共 {categoriesData.total_categories} 个超级行业组，覆盖 90 个细分行业
          {categoriesData.last_update_time && (
            <span className="super-category-view__update-time">
              · 数据更新: {formatDate(categoriesData.last_update_time)}
            </span>
          )}
        </p>
      </div>

      <div className="super-category-view__split">
        {/* 左侧：进攻性板块 */}
        <div className="super-category-view__column super-category-view__column--offensive">
          <div className="super-category-view__column-header">
            <h3>🚀 进攻性板块</h3>
            <span className="super-category-view__badge">
              {categoriesData.offensive_count} 组 · 评分 &gt; 50
            </span>
          </div>
          <div className="super-category-view__list">
            {categoriesData.offensive.map((category) => {
              const boards = getBoardsForCategory(category);
              return (
                <div key={category.name} className="super-category-group">
                  <div className="super-category-group__header">
                    <div className="super-category-group__title-section">
                      <h4 className="super-category-group__name">{category.name}</h4>
                      {category.pct_change !== null && category.pct_change !== undefined && (
                        <span className={`super-category-group__change ${category.pct_change >= 0 ? 'super-category-group__change--up' : 'super-category-group__change--down'}`}>
                          {category.pct_change >= 0 ? '+' : ''}{(category.pct_change * 100).toFixed(2)}%
                        </span>
                      )}
                      {category.total_mv && (
                        <span className="super-category-group__mv">
                          市值 {(category.total_mv / 10000).toFixed(0)}亿
                        </span>
                      )}
                    </div>
                    <span className="super-category-group__score super-category-group__score--offensive">
                      {category.score}
                    </span>
                  </div>
                  <div className="super-category-group__boards">
                    {boards.map((board, idx) => (
                      <BoardCard
                        key={board.板块名称}
                        board={board}
                        rank={idx + 1}
                        onClick={() => onBoardClick(board.板块名称)}
                      />
                    ))}
                  </div>
                </div>
              );
            })}
          </div>
        </div>

        {/* 右侧：防守性板块 */}
        <div className="super-category-view__column super-category-view__column--defensive">
          <div className="super-category-view__column-header">
            <h3>🛡️ 防守性板块</h3>
            <span className="super-category-view__badge">
              {categoriesData.defensive_count} 组 · 评分 ≤ 50
            </span>
          </div>
          <div className="super-category-view__list">
            {categoriesData.defensive.map((category) => {
              const boards = getBoardsForCategory(category);
              return (
                <div key={category.name} className="super-category-group">
                  <div className="super-category-group__header">
                    <div className="super-category-group__title-section">
                      <h4 className="super-category-group__name">{category.name}</h4>
                      {category.pct_change !== null && category.pct_change !== undefined && (
                        <span className={`super-category-group__change ${category.pct_change >= 0 ? 'super-category-group__change--up' : 'super-category-group__change--down'}`}>
                          {category.pct_change >= 0 ? '+' : ''}{(category.pct_change * 100).toFixed(2)}%
                        </span>
                      )}
                      {category.total_mv && (
                        <span className="super-category-group__mv">
                          市值 {(category.total_mv / 10000).toFixed(0)}亿
                        </span>
                      )}
                    </div>
                    <span className="super-category-group__score super-category-group__score--defensive">
                      {category.score}
                    </span>
                  </div>
                  <div className="super-category-group__boards">
                    {boards.map((board, idx) => (
                      <BoardCard
                        key={board.板块名称}
                        board={board}
                        rank={idx + 1}
                        onClick={() => onBoardClick(board.板块名称)}
                      />
                    ))}
                  </div>
                </div>
              );
            })}
          </div>
        </div>
      </div>
    </div>
  );
}
