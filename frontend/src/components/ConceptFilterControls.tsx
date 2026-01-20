import { useMemo } from "react";

export type ConceptSortBy = "default" | "name" | "stock_count_desc" | "stock_count_asc" | "change_desc" | "change_asc";

export interface ConceptFilterOptions {
  sortBy: ConceptSortBy;
  category: string;  // "all" 或具体分类名
}

interface Props {
  options: ConceptFilterOptions;
  onChange: (options: ConceptFilterOptions) => void;
  categories: string[];  // 所有可用的分类
  totalCount: number;
  filteredCount: number;
}

export function ConceptFilterControls({ options, onChange, categories, totalCount, filteredCount }: Props) {
  const handleSortChange = (sortBy: ConceptSortBy) => {
    onChange({ ...options, sortBy });
  };

  const handleCategoryChange = (category: string) => {
    onChange({ ...options, category });
  };

  const handleResetFilters = () => {
    onChange({
      sortBy: "default",
      category: "all"
    });
  };

  const hasActiveFilters = options.category !== "all" || options.sortBy !== "default";

  return (
    <div className="stock-filter-controls">
      <div className="stock-filter-controls__section">
        <label className="stock-filter-controls__label">排序：</label>
        <select
          className="stock-filter-controls__select"
          value={options.sortBy}
          onChange={(e) => handleSortChange(e.target.value as ConceptSortBy)}
        >
          <option value="default">默认</option>
          <option value="change_desc">涨跌幅：从高到低 ↓</option>
          <option value="change_asc">涨跌幅：从低到高 ↑</option>
          <option value="name">名称</option>
          <option value="stock_count_desc">成分股数量：从多到少 ↓</option>
          <option value="stock_count_asc">成分股数量：从少到多 ↑</option>
        </select>
      </div>

      <div className="stock-filter-controls__section">
        <label className="stock-filter-controls__label">分类：</label>
        <select
          className="stock-filter-controls__select"
          value={options.category}
          onChange={(e) => handleCategoryChange(e.target.value)}
        >
          <option value="all">全部分类</option>
          {categories.map(cat => (
            <option key={cat} value={cat}>{cat}</option>
          ))}
        </select>
      </div>

      <div className="stock-filter-controls__info">
        显示 <strong>{filteredCount}</strong> / {totalCount} 个板块
        {hasActiveFilters && (
          <button
            className="stock-filter-controls__reset"
            onClick={handleResetFilters}
          >
            重置筛选
          </button>
        )}
      </div>
    </div>
  );
}
