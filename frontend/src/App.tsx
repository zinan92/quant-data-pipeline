import { useState, useEffect } from "react";
import { BrowserRouter, Routes, Route, useNavigate, useLocation, useParams } from "react-router-dom";
import { WatchlistView } from "./components/WatchlistView";
import { SearchBar } from "./components/SearchBar";
import { StockDetail } from "./components/StockDetail";
import { IndexChart } from "./components/IndexChart";
import { RefreshButton } from "./components/RefreshButton";
import { SimulatedPortfolioView } from "./components/SimulatedPortfolioView";
import { MomentumSignalsView } from "./components/MomentumSignalsView";
import { ConceptMonitorTable } from "./components/ConceptMonitorTable";
import { ConceptKlinePanel } from "./components/ConceptKlinePanel";
import { MultiAssetDashboard } from "./components/MultiAssetDashboard";
import { USSectorCards } from "./components/USSectorCards";
import type { MAConfig } from "./types/chartConfig";
import { DEFAULT_MA_CONFIG } from "./types/chartConfig";

const DEFAULT_KLINE_LIMIT = 120;
const KLINE_LIMIT_KEY = "klineLimit";

function AppShell() {
  const navigate = useNavigate();
  const location = useLocation();
  const [maConfig, setMAConfig] = useState<MAConfig>(DEFAULT_MA_CONFIG);
  const [klineLimit, setKlineLimit] = useState<number>(() => {
    const saved = localStorage.getItem(KLINE_LIMIT_KEY);
    return saved ? parseInt(saved, 10) : DEFAULT_KLINE_LIMIT;
  });

  useEffect(() => {
    localStorage.setItem(KLINE_LIMIT_KEY, klineLimit.toString());
  }, [klineLimit]);

  const handleStockSelect = (ticker: string) => {
    navigate(`/stock/${ticker}`);
  };

  const currentPath = location.pathname;
  const isMainTab = currentPath === "/" || currentPath === "/watchlist";

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
            <button className="topbar__button topbar__button--secondary" onClick={() => navigate(-1)}>
              ← 返回
            </button>
          )}
          <RefreshButton />
          <button
            className="topbar__button topbar__button--warning"
            onClick={() => navigate("/signals")}
          >
            🔔 动量信号
          </button>
          <button
            className="topbar__button topbar__button--secondary"
            onClick={() => navigate("/portfolio")}
          >
            持仓
          </button>
          <button
            className={`topbar__button ${currentPath === "/us-sectors" ? "topbar__button--primary" : "topbar__button--secondary"}`}
            onClick={() => navigate("/us-sectors")}
          >
            🇺🇸 美股板块
          </button>
          <button
            className={`topbar__button ${currentPath === "/dashboard" ? "topbar__button--primary" : "topbar__button--secondary"}`}
            onClick={() => navigate("/dashboard")}
          >
            🌍 Dashboard
          </button>
          <button
            className={`topbar__button ${currentPath === "/" ? "topbar__button--primary" : "topbar__button--secondary"}`}
            onClick={() => navigate("/")}
          >
            📊 市场
          </button>
          <button
            className={`topbar__button ${currentPath === "/watchlist" ? "topbar__button--primary" : "topbar__button--secondary"}`}
            onClick={() => navigate("/watchlist")}
          >
            ⭐ 我的自选
          </button>
        </div>
      </header>

      {/* 主内容区 */}
      <main className="app__main">
        <Routes>
          {/* 市场概览 */}
          <Route path="/" element={
            <>
              <div className="dashboard dashboard--fullwidth">
                <div className="index-row">
                  <IndexChart tsCode="000001.SH" maConfig={maConfig} onMAConfigChange={setMAConfig} />
                  <IndexChart tsCode="399006.SZ" maConfig={maConfig} onMAConfigChange={setMAConfig} hideIndicators />
                  <IndexChart tsCode="000688.SH" maConfig={maConfig} onMAConfigChange={setMAConfig} hideIndicators />
                </div>
              </div>
              <div className="app__content">
                <div className="concept-panels-row">
                  <ConceptMonitorTable type="top" topN={20} />
                  <ConceptMonitorTable type="watch" />
                </div>
                <ConceptKlinePanel maConfig={maConfig} onConceptClick={() => {}} />
              </div>
            </>
          } />

          {/* 我的自选 */}
          <Route path="/watchlist" element={
            <div className="app__content">
              <WatchlistView
                maConfig={maConfig}
                onMAConfigChange={setMAConfig}
                onPortfolioClick={() => navigate("/portfolio")}
              />
            </div>
          } />

          {/* 个股详情 */}
          <Route path="/stock/:ticker" element={
            <div className="app__content">
              <StockDetailWrapper
                maConfig={maConfig}
                onMAConfigChange={setMAConfig}
                klineLimit={klineLimit}
                onKlineLimitChange={setKlineLimit}
              />
            </div>
          } />

          {/* 持仓 */}
          <Route path="/portfolio" element={
            <div className="app__content">
              <SimulatedPortfolioView />
            </div>
          } />

          {/* 动量信号 */}
          <Route path="/signals" element={
            <div className="app__content">
              <MomentumSignalsView />
            </div>
          } />

          {/* US Sector Cards */}
          <Route path="/us-sectors" element={
            <div className="app__content">
              <USSectorCards />
            </div>
          } />

          {/* Multi-Asset Dashboard */}
          <Route path="/dashboard" element={
            <div className="app__content">
              <MultiAssetDashboard />
            </div>
          } />
        </Routes>
      </main>
    </div>
  );
}

/** Wrapper to extract ticker from URL params */
function StockDetailWrapper({
  maConfig, onMAConfigChange, klineLimit, onKlineLimitChange
}: {
  maConfig: MAConfig;
  onMAConfigChange: (c: MAConfig) => void;
  klineLimit: number;
  onKlineLimitChange: (n: number) => void;
}) {
  const { ticker } = useParams<{ ticker: string }>();
  if (!ticker) return <div className="chart-grid__placeholder">未指定股票代码</div>;
  return (
    <StockDetail
      ticker={ticker}
      maConfig={maConfig}
      onMAConfigChange={onMAConfigChange}
      klineLimit={klineLimit}
      onKlineLimitChange={onKlineLimitChange}
    />
  );
}

export default function App() {
  return (
    <BrowserRouter>
      <AppShell />
    </BrowserRouter>
  );
}
