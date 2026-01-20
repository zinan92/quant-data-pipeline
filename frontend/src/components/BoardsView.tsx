import { useState, useEffect } from "react";
import { BoardCard } from "./BoardCard";
import { apiFetch } from "../utils/api";

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

interface IndustriesResponse {
  data: IndustryData[];
  last_update_time: string;
}

interface Props {
  onBoardClick: (boardName: string) => void;
  categoryName?: string;
  onBackClick?: () => void;
}

export function BoardsView({ onBoardClick, categoryName, onBackClick }: Props) {
  const [boards, setBoards] = useState<BoardData[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [categoryIndustries, setCategoryIndustries] = useState<string[]>([]);

  // 如果有 categoryName，先获取该分类下的行业列表
  useEffect(() => {
    if (!categoryName) {
      setCategoryIndustries([]);
      return;
    }

    apiFetch("/api/boards/super-categories")
      .then((response) => response.json())
      .then((data) => {
        // 在 offensive 和 defensive 中查找该分类
        const allCategories = [...data.offensive, ...data.defensive];
        const category = allCategories.find((cat) => cat.name === categoryName);
        if (category) {
          const industryNames = category.industries.map((ind: { name: string }) => ind.name);
          setCategoryIndustries(industryNames);
        }
      })
      .catch((err) => {
        console.error("Failed to load category industries:", err);
      });
  }, [categoryName]);

  useEffect(() => {
    // 从API获取实际的行业列表
    apiFetch("/api/symbols/industries")
      .then((response) => {
        if (!response.ok) {
          throw new Error("Failed to load industries");
        }
        return response.json();
      })
      .then((response: IndustriesResponse) => {
        // 如果有分类过滤，只显示该分类下的行业
        let filteredIndustries = response.data;
        if (categoryName && categoryIndustries.length > 0) {
          filteredIndustries = response.data.filter((ind) =>
            categoryIndustries.includes(ind.板块名称)
          );
        }

        // 转换为BoardData格式
        const data: BoardData[] = filteredIndustries.map((ind, idx) => ({
          排名: idx + 1,
          板块名称: ind.板块名称,
          板块代码: `IND_${idx}`,
          最新价: 0,
          涨跌额: 0,
          涨跌幅: ind.涨跌幅,
          总市值: ind.总市值,
          换手率: 0,
          上涨家数: ind.上涨家数,
          下跌家数: ind.下跌家数,
          领涨股票: "",
          "领涨股票-涨跌幅": 0,
          行业PE: ind.行业PE,
        }));

        setBoards(data);
        setLoading(false);
      })
      .catch((err) => {
        setError(err.message);
        setLoading(false);
      });
  }, [categoryName, categoryIndustries]);

  if (loading) {
    return (
      <div className="boards-view__loading">
        加载板块数据...
      </div>
    );
  }

  if (error) {
    return (
      <div className="boards-view__error">
        加载失败: {error}
      </div>
    );
  }

  return (
    <div className="boards-view">
      {categoryName && (
        <div className="boards-view__category-header">
          <button
            className="boards-view__back-btn"
            onClick={onBackClick}
          >
            ← 返回分类
          </button>
          <h2 className="boards-view__category-title">{categoryName}</h2>
          <span className="boards-view__category-count">
            {boards.length} 个行业
          </span>
        </div>
      )}
      <div className="boards-grid">
        {boards.map((board, index) => (
          <BoardCard
            key={board.板块代码}
            board={board}
            rank={index + 1}
            onClick={() => onBoardClick(board.板块名称)}
          />
        ))}
      </div>
    </div>
  );
}
