import { useMemo, useState, useEffect } from "react";
import { WatchlistView } from "./components/WatchlistView";
import { ControlPanel } from "./components/ControlPanel";
import { SearchBar } from "./components/SearchBar";
import { StockDetail } from "./components/StockDetail";
import { IndexChart } from "./components/IndexChart";
import { RefreshButton } from "./components/RefreshButton";
import { SimulatedPortfolioView } from "./components/SimulatedPortfolioView";
import { MomentumSignalsView } from "./components/MomentumSignalsView";
import { ConceptMonitorTable } from "./components/ConceptMonitorTable";
import { ConceptKlinePanel } from "./components/ConceptKlinePanel";
import type { Timeframe } from "./types/timeframe";
import type { MAConfig } from "./types/chartConfig";
import { DEFAULT_MA_CONFIG } from "./types/chartConfig";

const DEFAULT_KLINE_LIMIT = 120;
const KLINE_LIMIT_KEY = "klineLimit";

type ViewMode = "market" | "watchlist" | "stock" | "portfolio" | "signals";

export default function App() {
  const [viewMode, setViewMode] = useState<ViewMode>("market");
  const [selectedStock, setSelectedStock] = useState<string | null>(null);
  const [timeframe, setTimeframe] = useState<Timeframe>("day");
  const [maConfig, setMAConfig] = useState<MAConfig>(DEFAULT_MA_CONFIG);
  const [klineLimit, setKlineLimit] = useState<number>(() => {
    const saved = localStorage.getItem(KLINE_LIMIT_KEY);
    return saved ? parseInt(saved, 10) : DEFAULT_KLINE_LIMIT;
  });
  const [history, setHistory] = useState<
    Array<{ viewMode: ViewMode; selectedStock: string | null }>
  >([]);

  useEffect(() => {
    localStorage.setItem(KLINE_LIMIT_KEY, klineLimit.toString());
  }, [klineLimit]);

  const pushHistory = () => {
    setHistory(prev => [...prev, { viewMode, selectedStock }]);
  };

  const handlePortfolioClick = () => {
    pushHistory();
    setViewMode("portfolio");
  };

  const handleStockSelect = (ticker: string) => {
    pushHistory();
    setSelectedStock(ticker);
    setViewMode("stock");
  };

  const handleBackClick = () => {
    setHistory(prev => {
      if (prev.length === 0) {
        setViewMode("market");
        setSelectedStock(null);
        return prev;
      }
      const next = [...prev];
      const last = next.pop()!;
      setViewMode(last.viewMode);
      setSelectedStock(last.selectedStock);
      return next;
    });
  };

  const isMainTab = viewMode === "market" || viewMode === "watchlist";

  return (
    <div className="app">
      {/* 顶部导航栏 */}
      <header className="app__topbar">
        <div className="app__topbar-left">
          <span className="app__brand-label">A-SHARE MONITOR</span>
          <SearchBar onSelectStock={handleStockSelect} />
        </div>
        <div className="app__topbar-right">
          {!isMainTab && (
            <button className="topbar__button topbar__button--secondary" onClick={handleBackClick}>
              ← 返回
            </button>
          )}
          {isMainTab && (
            <>
              <RefreshButton />
              <button className="topbar__button topbar__button--warning" onClick={() => { pushHistory(); setViewMode("signals"); }}>
                🔔 动量信号
              </button>
              <button className="topbar__button topbar__button--secondary" onClick={handlePortfolioClick}>
                持仓
              </button>
              <button
                className={`topbar__button ${viewMode === "market" ? "topbar__button--primary" : "topbar__button--secondary"}`}
                onClick={() => setViewMode("market")}
              >
                📊 市场
              </button>
              <button
                className={`topbar__button ${viewMode === "watchlist" ? "topbar__button--primary" : "topbar__button--secondary"}`}
                onClick={() => setViewMode("watchlist")}
              >
                ⭐ 我的自选
              </button>
            </>
          )}
        </div>
      </header>

      {/* 主内容区 */}
      <main className="app__main">
        {/* Tab 1: 市场概览 */}
        {viewMode === "market" && (
          <>
            {/* 指数区 */}
            <div className="dashboard dashboard--fullwidth">
              <div className="index-row">
                <IndexChart tsCode="000001.SH" maConfig={maConfig} onMAConfigChange={setMAConfig} />
                <IndexChart tsCode="399006.SZ" maConfig={maConfig} onMAConfigChange={setMAConfig} hideIndicators />
                <IndexChart tsCode="000688.SH" maConfig={maConfig} onMAConfigChange={setMAConfig} hideIndicators />
              </div>
            </div>

            {/* 板块排行 */}
            <div className="app__content">
              <div className="concept-panels-row">
                <ConceptMonitorTable type="top" topN={20} />
                <ConceptMonitorTable type="watch" />
              </div>
              <ConceptKlinePanel maConfig={maConfig} onConceptClick={() => {}} />
            </div>
          </>
        )}

        {/* Tab 2: 我的自选 */}
        {viewMode === "watchlist" && (
          <div className="app__content">
            <WatchlistView
              maConfig={maConfig}
              onMAConfigChange={setMAConfig}
              onPortfolioClick={handlePortfolioClick}
            />
          </div>
        )}

        {/* 其他视图 */}
        {viewMode === "portfolio" && (
          <div className="app__content">
            <SimulatedPortfolioView />
          </div>
        )}
        {viewMode === "signals" && (
          <div className="app__content">
            <MomentumSignalsView />
          </div>
        )}
        {viewMode === "stock" && selectedStock && (
          <div className="app__content">
            <StockDetail
              ticker={selectedStock}
              maConfig={maConfig}
              onMAConfigChange={setMAConfig}
              klineLimit={klineLimit}
              onKlineLimitChange={setKlineLimit}
            />
          </div>
        )}
      </main>
    </div>
  );
}
