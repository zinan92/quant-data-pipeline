import { useMemo, useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { apiFetch, REFRESH_INTERVALS } from "../utils/api";
import { ConceptKlineCard } from "./ConceptKlineCard";
import { ConceptFilterControls, ConceptFilterOptions } from "./ConceptFilterControls";
import type { MAConfig } from "../types/chartConfig";

interface ConceptInfo {
  name: string;
  code: string;
  category: string;
  stock_count: number;
  change_pct: number | null;
}

interface ConceptListResponse {
  concepts: ConceptInfo[];
  total: number;
}

async function fetchConcepts(): Promise<ConceptListResponse> {
  const response = await apiFetch("/api/concepts");
  if (!response.ok) {
    throw new Error("Failed to fetch concepts");
  }
  return response.json();
}

interface Props {
  maConfig: MAConfig;
  onConceptClick?: (concept: ConceptInfo) => void;
}

export function ConceptKlinePanel({ maConfig, onConceptClick }: Props) {
  const [filterOptions, setFilterOptions] = useState<ConceptFilterOptions>({
    sortBy: "default",
    category: "all"
  });

  const { data, isLoading, error } = useQuery({
    queryKey: ["concepts-list"],
    queryFn: fetchConcepts,
    staleTime: REFRESH_INTERVALS.boards,
    refetchInterval: REFRESH_INTERVALS.boards
  });

  // 获取所有分类
  const categories = useMemo(() => {
    if (!data) return [];
    const cats = new Set(data.concepts.map(c => c.category));
    return Array.from(cats).sort();
  }, [data]);

  // 筛选和排序
  const filteredConcepts = useMemo(() => {
    if (!data) return [];

    let result = [...data.concepts];

    // 按分类筛选
    if (filterOptions.category !== "all") {
      result = result.filter(c => c.category === filterOptions.category);
    }

    // 排序
    switch (filterOptions.sortBy) {
      case "change_desc":
        result.sort((a, b) => (b.change_pct ?? -999) - (a.change_pct ?? -999));
        break;
      case "change_asc":
        result.sort((a, b) => (a.change_pct ?? 999) - (b.change_pct ?? 999));
        break;
      case "name":
        result.sort((a, b) => a.name.localeCompare(b.name, 'zh-CN'));
        break;
      case "stock_count_desc":
        result.sort((a, b) => b.stock_count - a.stock_count);
        break;
      case "stock_count_asc":
        result.sort((a, b) => a.stock_count - b.stock_count);
        break;
      default:
        // 保持原顺序
        break;
    }

    return result;
  }, [data, filterOptions]);

  if (isLoading) {
    return (
      <div className="etf-flow etf-flow--fullscreen etf-flow--loading">
        <div className="etf-flow__spinner">概念板块加载中...</div>
      </div>
    );
  }

  if (error || !data) {
    return null;
  }

  return (
    <div className="etf-flow etf-flow--fullscreen">
      <div className="etf-flow__header">
        <div>
          <h3 className="etf-flow__title">热门概念板块日K线</h3>
          <p className="etf-flow__subtitle">共 {data.total} 个热门概念板块（双击查看成分股）</p>
        </div>
      </div>

      <ConceptFilterControls
        options={filterOptions}
        onChange={setFilterOptions}
        categories={categories}
        totalCount={data.total}
        filteredCount={filteredConcepts.length}
      />

      {/* 概念板块网格布局 - 3列 */}
      <div className="concept-grid">
        {filteredConcepts.map(concept => (
          <ConceptKlineCard
            key={concept.code}
            concept={concept}
            maConfig={maConfig}
            onClick={onConceptClick}
          />
        ))}
      </div>
    </div>
  );
}
