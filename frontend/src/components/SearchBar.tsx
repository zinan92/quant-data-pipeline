import { useState, useRef, useEffect } from "react";
import { useQuery } from "@tanstack/react-query";
import type { SymbolMeta } from "../types/symbol";
import { apiFetch, REFRESH_INTERVALS } from "../utils/api";
import { getBoardInfo } from "../utils/boardUtils";

interface Props {
  onSelectStock: (ticker: string) => void;
}

async function searchSymbols(query: string): Promise<SymbolMeta[]> {
  if (!query || query.length < 1) {
    return [];
  }
  const response = await apiFetch(
    `/api/symbols/search?q=${encodeURIComponent(query)}`
  );
  if (!response.ok) {
    throw new Error("Search failed");
  }
  return response.json();
}

export function SearchBar({ onSelectStock }: Props) {
  const [query, setQuery] = useState("");
  const [showResults, setShowResults] = useState(false);
  const searchRef = useRef<HTMLDivElement>(null);

  const { data: results, isLoading } = useQuery({
    queryKey: ["search", query],
    queryFn: () => searchSymbols(query),
    enabled: query.length >= 1,
    staleTime: REFRESH_INTERVALS.symbols,
    refetchInterval: REFRESH_INTERVALS.symbols
  });

  // Close results when clicking outside
  useEffect(() => {
    function handleClickOutside(event: MouseEvent) {
      if (searchRef.current && !searchRef.current.contains(event.target as Node)) {
        setShowResults(false);
      }
    }

    document.addEventListener("mousedown", handleClickOutside);
    return () => {
      document.removeEventListener("mousedown", handleClickOutside);
    };
  }, []);

  const handleSelectStock = (ticker: string) => {
    setShowResults(false);
    setQuery("");
    onSelectStock(ticker);
  };

  return (
    <div className="search-bar" ref={searchRef}>
      <input
        type="text"
        className="search-bar__input"
        placeholder="搜索股票代码或名称..."
        value={query}
        onChange={(e) => {
          setQuery(e.target.value);
          setShowResults(true);
        }}
        onFocus={() => setShowResults(true)}
      />
      {showResults && query.length >= 1 && (
        <div className="search-bar__results">
          {isLoading && (
            <div className="search-bar__loading">搜索中...</div>
          )}
          {!isLoading && results && results.length === 0 && (
            <div className="search-bar__empty">未找到匹配的股票</div>
          )}
          {!isLoading && results && results.length > 0 && (
            <ul className="search-bar__list">
              {results.map((stock) => {
                const boardInfo = getBoardInfo(stock.ticker);
                return (
                <li
                  key={stock.ticker}
                  className="search-bar__item"
                  onClick={() => handleSelectStock(stock.ticker)}
                >
                  <div className="search-bar__item-main">
                    <span className="search-bar__item-name">
                      {stock.name}
                      {boardInfo.label && (
                        <span className={`board-tag ${boardInfo.className}`}>{boardInfo.label}</span>
                      )}
                    </span>
                    <span className="search-bar__item-ticker">{stock.ticker}</span>
                  </div>
                  <div className="search-bar__item-info">
                    {stock.totalMv && (
                      <span className="search-bar__item-mv">
                        {(stock.totalMv / 1e4).toFixed(0)}亿
                      </span>
                    )}
                    {stock.peTtm !== null && stock.peTtm !== undefined && (
                      <span className="search-bar__item-pe">
                        PE {stock.peTtm.toFixed(1)}
                      </span>
                    )}
                  </div>
                </li>
                );
              })}
            </ul>
          )}
        </div>
      )}
    </div>
  );
}
