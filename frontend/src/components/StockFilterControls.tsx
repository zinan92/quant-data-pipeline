import { useState } from "react";

export type SortBy = "default" | "change_desc" | "change_asc" | "mv_desc" | "mv_asc" | "pe_desc" | "pe_asc";
export type FilterDirection = "all" | "up" | "down";

export interface FilterOptions {
  sortBy: SortBy;
  direction: FilterDirection;
  peMin: number;
  peMax: number;
  mvMin: number;  // 市值最小值（亿元）
  mvMax: number;  // 市值最大值（亿元）
  focusOnly: boolean;  // 只显示重点关注
}

interface Props {
  options: FilterOptions;
  onChange: (options: FilterOptions) => void;
  totalCount: number;
  filteredCount: number;
}

export function StockFilterControls({ options, onChange, totalCount, filteredCount }: Props) {
  const [showPEFilter, setShowPEFilter] = useState(false);
  const [showMVFilter, setShowMVFilter] = useState(false);

  const handleSortChange = (sortBy: SortBy) => {
    onChange({ ...options, sortBy });
  };

  const handleDirectionChange = (direction: FilterDirection) => {
    onChange({ ...options, direction });
  };

  const handlePEChange = (min: number, max: number) => {
    onChange({ ...options, peMin: min, peMax: max });
  };

  const handleMVChange = (min: number, max: number) => {
    onChange({ ...options, mvMin: min, mvMax: max });
  };

  const handleResetFilters = () => {
    onChange({
      sortBy: "default",
      direction: "all",
      peMin: 0,
      peMax: 1000,
      mvMin: 0,
      mvMax: 100000,
      focusOnly: false
    });
  };

  const handleToggleFocus = () => {
    onChange({ ...options, focusOnly: !options.focusOnly });
  };

  const hasActiveFilters = options.direction !== "all" || options.sortBy !== "default" || options.peMin > 0 || options.peMax < 1000 || options.mvMin > 0 || options.mvMax < 100000 || options.focusOnly;

  return (
    <div className="stock-filter-controls">
      <div className="stock-filter-controls__section">
        <label className="stock-filter-controls__label">排序：</label>
        <select
          className="stock-filter-controls__select"
          value={options.sortBy}
          onChange={(e) => handleSortChange(e.target.value as SortBy)}
        >
          <option value="default">默认（市值排序）</option>
          <option value="change_desc">涨跌幅：从高到低 ↓</option>
          <option value="change_asc">涨跌幅：从低到高 ↑</option>
          <option value="mv_desc">市值：从大到小 ↓</option>
          <option value="mv_asc">市值：从小到大 ↑</option>
          <option value="pe_desc">PE：从高到低 ↓</option>
          <option value="pe_asc">PE：从低到高 ↑</option>
        </select>
      </div>

      <div className="stock-filter-controls__section">
        <label className="stock-filter-controls__label">筛选：</label>
        <div className="stock-filter-controls__button-group">
          <button
            className={`stock-filter-controls__button ${options.direction === "all" ? "stock-filter-controls__button--active" : ""}`}
            onClick={() => handleDirectionChange("all")}
          >
            全部
          </button>
          <button
            className={`stock-filter-controls__button stock-filter-controls__button--up ${options.direction === "up" ? "stock-filter-controls__button--active" : ""}`}
            onClick={() => handleDirectionChange("up")}
          >
            ↑ 上涨
          </button>
          <button
            className={`stock-filter-controls__button stock-filter-controls__button--down ${options.direction === "down" ? "stock-filter-controls__button--active" : ""}`}
            onClick={() => handleDirectionChange("down")}
          >
            ↓ 下跌
          </button>
          <button
            className={`stock-filter-controls__button stock-filter-controls__button--focus ${options.focusOnly ? "stock-filter-controls__button--active" : ""}`}
            onClick={handleToggleFocus}
            title="只显示重点关注的股票"
          >
            ★ 重点关注
          </button>
        </div>
      </div>

      <div className="stock-filter-controls__section">
        <button
          className="stock-filter-controls__pe-toggle"
          onClick={() => setShowMVFilter(!showMVFilter)}
        >
          市值(亿) {showMVFilter ? "▼" : "▶"}
        </button>
        {showMVFilter && (
          <div className="stock-filter-controls__pe-inputs">
            <input
              type="number"
              className="stock-filter-controls__input"
              placeholder="最小"
              value={options.mvMin || ""}
              onChange={(e) => handleMVChange(Number(e.target.value) || 0, options.mvMax)}
              min="0"
              step="10"
            />
            <span className="stock-filter-controls__separator">-</span>
            <input
              type="number"
              className="stock-filter-controls__input"
              placeholder="最大"
              value={options.mvMax < 100000 ? options.mvMax : ""}
              onChange={(e) => handleMVChange(options.mvMin, Number(e.target.value) || 100000)}
              min="0"
              step="10"
            />
          </div>
        )}
      </div>

      <div className="stock-filter-controls__section">
        <button
          className="stock-filter-controls__pe-toggle"
          onClick={() => setShowPEFilter(!showPEFilter)}
        >
          PE范围 {showPEFilter ? "▼" : "▶"}
        </button>
        {showPEFilter && (
          <div className="stock-filter-controls__pe-inputs">
            <input
              type="number"
              className="stock-filter-controls__input"
              placeholder="最小PE"
              value={options.peMin || ""}
              onChange={(e) => handlePEChange(Number(e.target.value) || 0, options.peMax)}
              min="0"
              step="1"
            />
            <span className="stock-filter-controls__separator">-</span>
            <input
              type="number"
              className="stock-filter-controls__input"
              placeholder="最大PE"
              value={options.peMax < 1000 ? options.peMax : ""}
              onChange={(e) => handlePEChange(options.peMin, Number(e.target.value) || 1000)}
              min="0"
              step="1"
            />
          </div>
        )}
      </div>

      <div className="stock-filter-controls__info">
        显示 <strong>{filteredCount}</strong> / {totalCount} 只股票
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
