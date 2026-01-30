import { useMemo, useState, useEffect } from "react";
import { WatchlistView } from "./components/WatchlistView";
import { ControlPanel } from "./components/ControlPanel";
import { SearchBar } from "./components/SearchBar";
import { StockDetail } from "./components/StockDetail";
import { IndexChart } from "./components/IndexChart";
import { ConceptKlinePanel } from "./components/ConceptKlinePanel";
import { ConceptDetailView } from "./components/ConceptDetailView";
import { RefreshButton } from "./components/RefreshButton";
import { SimulatedPortfolioView } from "./components/SimulatedPortfolioView";
import { ConceptMonitorTable } from "./components/ConceptMonitorTable";
import { MomentumSignalsView } from "./components/MomentumSignalsView";
import type { Timeframe } from "./types/timeframe";
import type { MAConfig } from "./types/chartConfig";
import { DEFAULT_MA_CONFIG } from "./types/chartConfig";

const DEFAULT_KLINE_LIMIT = 120;
const KLINE_LIMIT_KEY = "klineLimit";

type ViewMode = "concepts" | "conceptDetail" | "watchlist" | "stock" | "portfolio" | "signals";

interface ConceptInfo {
  name: string;
  code: string;
  category: string;
  stock_count: number;
}

export default function App() {
  const [viewMode, setViewMode] = useState<ViewMode>("concepts");
  const [selectedConcept, setSelectedConcept] = useState<ConceptInfo | null>(null);
  const [selectedStock, setSelectedStock] = useState<string | null>(null);
  const [timeframe, setTimeframe] = useState<Timeframe>("day");
  const [maConfig, setMAConfig] = useState<MAConfig>(DEFAULT_MA_CONFIG);
  const [klineLimit, setKlineLimit] = useState<number>(() => {
    const saved = localStorage.getItem(KLINE_LIMIT_KEY);
    return saved ? parseInt(saved, 10) : DEFAULT_KLINE_LIMIT;
  });
  const [history, setHistory] = useState<
    Array<{
      viewMode: ViewMode;
      selectedConcept: ConceptInfo | null;
      selectedStock: string | null;
    }>
  >([]);

  const snapshot = useMemo(
    () => ({
      viewMode,
      selectedConcept,
      selectedStock
    }),
    [viewMode, selectedConcept, selectedStock]
  );

  // Save klineLimit to localStorage
  useEffect(() => {
    localStorage.setItem(KLINE_LIMIT_KEY, klineLimit.toString());
  }, [klineLimit]);

  const pushHistory = () => {
    setHistory(prev => [...prev, snapshot]);
  };

  const handleConceptClick = (concept: ConceptInfo) => {
    pushHistory();
    setSelectedConcept(concept);
    setViewMode("conceptDetail");
  };

  const handleWatchlistClick = () => {
    pushHistory();
    setViewMode("watchlist");
  };

  const handlePortfolioClick = () => {
    pushHistory();
    setViewMode("portfolio");
  };

  const handleSignalsClick = () => {
    pushHistory();
    setViewMode("signals");
  };

  const handleStockSelect = (ticker: string) => {
    pushHistory();
    setSelectedStock(ticker);
    setViewMode("stock");
  };

  const handleBackClick = () => {
    setHistory(prev => {
      if (prev.length === 0) {
        setViewMode("concepts");
        setSelectedConcept(null);
        setSelectedStock(null);
        return prev;
      }

      const next = [...prev];
      const last = next.pop()!;
      setViewMode(last.viewMode);
      setSelectedConcept(last.selectedConcept);
      setSelectedStock(last.selectedStock);
      return next;
    });
  };

  return (
    <div className="app">
      {/* 顶部导航栏 */}
      <header className="app__topbar">
        <div className="app__topbar-left">
          <span className="app__brand-label">A-SHARE MONITOR</span>
          <SearchBar onSelectStock={handleStockSelect} />
        </div>
        <div className="app__topbar-right">
          {viewMode !== "concepts" && (
            <button className="topbar__button topbar__button--secondary" onClick={handleBackClick}>
              ← 返回
            </button>
          )}
          {viewMode === "concepts" && (
            <>
              <RefreshButton />
              <button className="topbar__button topbar__button--warning" onClick={handleSignalsClick}>
                🔔 动量信号
              </button>
              <button className="topbar__button topbar__button--secondary" onClick={handlePortfolioClick}>
                持仓
              </button>
              <button className="topbar__button topbar__button--primary" onClick={handleWatchlistClick}>
                我的自选
              </button>
            </>
          )}
        </div>
      </header>

      {/* 主内容区 */}
      <main className="app__main">
        {/* 主要指数图表 - 仅在concepts视图显示 */}
        {viewMode === "concepts" && (
          <div className="dashboard dashboard--fullwidth">
            <div className="index-row">
              <IndexChart key="000001.SH" tsCode="000001.SH" maConfig={maConfig} onMAConfigChange={setMAConfig} />
              <IndexChart key="399006.SZ" tsCode="399006.SZ" maConfig={maConfig} onMAConfigChange={setMAConfig} />
              <IndexChart key="000688.SH" tsCode="000688.SH" maConfig={maConfig} onMAConfigChange={setMAConfig} />
            </div>
          </div>
        )}

        {/* 概念板块实时监控 - 仅在concepts视图显示 */}
        {viewMode === "concepts" && (
          <div className="concept-monitor-container">
            <ConceptMonitorTable type="top" topN={20} />
            <ConceptMonitorTable type="watch" />
          </div>
        )}

        {/* 概念板块K线 - 仅在concepts视图显示 */}
        {viewMode === "concepts" && (
          <div className="dashboard dashboard--fullwidth">
            <ConceptKlinePanel maConfig={maConfig} onConceptClick={handleConceptClick} />
          </div>
        )}

        {/* 内容区域 */}
        <div className="app__content">
          {viewMode === "watchlist" && (
            <WatchlistView
              maConfig={maConfig}
              onMAConfigChange={setMAConfig}
              onPortfolioClick={handlePortfolioClick}
            />
          )}
          {viewMode === "portfolio" && (
            <SimulatedPortfolioView />
          )}
          {viewMode === "signals" && (
            <MomentumSignalsView />
          )}
          {viewMode === "conceptDetail" && selectedConcept && (
            <ConceptDetailView
              conceptName={selectedConcept.name}
              conceptCode={selectedConcept.code}
              maConfig={maConfig}
              onMAConfigChange={setMAConfig}
              klineLimit={klineLimit}
            />
          )}
          {viewMode === "stock" && selectedStock && (
            <StockDetail ticker={selectedStock} maConfig={maConfig} onMAConfigChange={setMAConfig} klineLimit={klineLimit} onKlineLimitChange={setKlineLimit} />
          )}
        </div>
      </main>
    </div>
  );
}
