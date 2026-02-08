/**
 * 自选股卡片 - 双K线布局（日线 + 30分钟）
 * 支持展开/收起公司详情
 */

import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import type { SymbolMeta } from "../types/symbol";
import type { MAConfig } from "../types/chartConfig";
import { fetchCandles } from "../hooks/useCandles";
import { useMemo, useState, useRef, useEffect } from "react";
import { apiFetch, REFRESH_INTERVALS } from "../utils/api";
import { KlineChart, type KlineDataPoint } from "./charts";
import { getBoardInfo } from "../utils/boardUtils";
import { KlineEvaluationForm } from "./KlineEvaluationForm";
import { TradeDialog } from "./TradeDialog";

interface RealtimePrice {
  ticker: string;
  price: number;
  change: number;
  changePercent: number;
  lastUpdate: string;
}

interface Props {
  symbol: SymbolMeta;
  maConfig: MAConfig;
  realtimePrice?: RealtimePrice;
  klineLimit?: number;
  sector?: string;
  onSectorChange?: (ticker: string, newSector: string) => void;
}

export function WatchlistCard({ symbol, maConfig, realtimePrice, klineLimit = 120, sector, onSectorChange }: Props) {
  const [isExpanded, setIsExpanded] = useState(false);
  const [isEarningsExpanded, setIsEarningsExpanded] = useState(false);
  const [isInWatchlist, setIsInWatchlist] = useState<boolean | null>(null); // null表示加载中
  const [tradeDialog, setTradeDialog] = useState<{ type: "buy" | "sell" } | null>(null);
  const [showSectorDropdown, setShowSectorDropdown] = useState(false);
  const sectorDropdownRef = useRef<HTMLDivElement>(null);
  const queryClient = useQueryClient();
  const tickerForApi = symbol.ticker.split('.')[0];
  const cardRef = useRef<HTMLElement>(null);

  // 获取可用赛道列表
  const { data: availableSectorsData } = useQuery({
    queryKey: ["available-sectors"],
    queryFn: async () => {
      const response = await apiFetch("/api/sectors/list/available");
      if (!response.ok) return { sectors: [] };
      return response.json();
    },
    staleTime: 1000 * 60 * 60, // 1小时缓存
  });

  const availableSectors = availableSectorsData?.sectors ?? [];

  // 更新赛道的mutation
  const updateSectorMutation = useMutation({
    mutationFn: async (newSector: string) => {
      const response = await apiFetch(`/api/sectors/${tickerForApi}`, {
        method: "PUT",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ sector: newSector })
      });
      if (!response.ok) {
        throw new Error("更新赛道失败");
      }
      return response.json();
    },
    onSuccess: (_, newSector) => {
      // 刷新赛道数据
      queryClient.invalidateQueries({ queryKey: ["sectors-all"] });
      queryClient.invalidateQueries({ queryKey: ["sector-turnover"] });
      // 通知父组件
      onSectorChange?.(tickerForApi, newSector);
      setShowSectorDropdown(false);
    }
  });

  // 切换重点关注的mutation
  const toggleFocusMutation = useMutation({
    mutationFn: async () => {
      const response = await apiFetch(`/api/watchlist/${tickerForApi}/focus`, {
        method: "PATCH"
      });
      if (!response.ok) {
        const error = await response.text();
        throw new Error(`切换重点关注失败: ${error}`);
      }
      return response.json();
    },
    onSuccess: (data) => {
      console.log('Focus toggle success:', data);
      // 立即刷新watchlist数据
      queryClient.invalidateQueries({ queryKey: ["watchlist"] });
    },
    onError: (error) => {
      console.error('Focus toggle error:', error);
      alert(`操作失败: ${error.message}`);
    }
  });

  // 点击外部关闭下拉菜单
  useEffect(() => {
    const handleClickOutside = (event: MouseEvent) => {
      if (sectorDropdownRef.current && !sectorDropdownRef.current.contains(event.target as Node)) {
        setShowSectorDropdown(false);
      }
    };
    if (showSectorDropdown) {
      document.addEventListener("mousedown", handleClickOutside);
      return () => document.removeEventListener("mousedown", handleClickOutside);
    }
  }, [showSectorDropdown]);

  // 获取日线数据 (30分钟缓存，非交易时间数据变化不频繁)
  const { data: dayData } = useQuery({
    queryKey: ["candles", tickerForApi, "day", klineLimit],
    queryFn: () => fetchCandles(tickerForApi, "day", klineLimit),
    staleTime: 1000 * 60 * 30
  });

  // 获取30分钟数据 (30分钟缓存，非交易时间数据变化不频繁)
  const { data: mins30Data } = useQuery({
    queryKey: ["candles", tickerForApi, "30m", klineLimit],
    queryFn: () => fetchCandles(tickerForApi, "30m", klineLimit),
    staleTime: 1000 * 60 * 30
  });

  // 获取概念板块
  const { data: conceptsData } = useQuery({
    queryKey: ["ticker-concepts", tickerForApi],
    queryFn: async () => {
      const response = await fetch(`/api/concepts/by-ticker/${tickerForApi}`);
      if (!response.ok) return { concepts: [] };
      return response.json();
    },
    staleTime: 1000 * 60 * 60,
    enabled: isExpanded // 只有展开时才加载
  });

  // 获取业绩数据（业绩预告和业绩快报）
  const { data: earningsData, isLoading: earningsLoading } = useQuery({
    queryKey: ["earnings", tickerForApi],
    queryFn: async () => {
      const response = await apiFetch(`/api/earnings/${tickerForApi}`);
      if (!response.ok) return { forecasts: [], expresses: [] };
      return response.json();
    },
    staleTime: 1000 * 60 * 60, // 1小时缓存
    enabled: isEarningsExpanded // 只有展开时才加载
  });

  // 检查自选状态
  const { data: watchlistStatus } = useQuery({
    queryKey: ["watchlist-check", tickerForApi],
    queryFn: async () => {
      const response = await apiFetch(`/api/watchlist/check/${tickerForApi}`);
      if (!response.ok) return { in_watchlist: true };
      return response.json();
    },
    staleTime: REFRESH_INTERVALS.watchlist
  });

  // 获取模拟账户信息（用于买入时的可用现金）
  const { data: accountData } = useQuery({
    queryKey: ["simulated-account"],
    queryFn: async () => {
      const response = await apiFetch("/api/simulated/account");
      if (!response.ok) return null;
      return response.json();
    },
    staleTime: 30000,
  });

  // 检查该股票的持仓
  const { data: positionData } = useQuery({
    queryKey: ["simulated-position-check", tickerForApi],
    queryFn: async () => {
      const response = await apiFetch(`/api/simulated/check/${tickerForApi}`);
      if (!response.ok) return { has_position: false };
      return response.json();
    },
    staleTime: 30000,
  });

  useMemo(() => {
    if (watchlistStatus) {
      setIsInWatchlist(watchlistStatus.in_watchlist);
    }
  }, [watchlistStatus]);

  // 添加自选
  const addToWatchlist = useMutation({
    mutationFn: async () => {
      const response = await apiFetch("/api/watchlist", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ ticker: tickerForApi })
      });
      if (!response.ok) {
        const error = await response.json();
        throw new Error(error.detail || "添加失败");
      }
      return response.json();
    },
    onSuccess: () => {
      setIsInWatchlist(true);
      queryClient.invalidateQueries({ queryKey: ["watchlist"] });
      queryClient.invalidateQueries({ queryKey: ["watchlist-check", tickerForApi] });
    }
  });

  // 移除自选
  const removeFromWatchlist = useMutation({
    mutationFn: async () => {
      const response = await apiFetch(`/api/watchlist/${tickerForApi}`, {
        method: "DELETE"
      });
      if (!response.ok) {
        const error = await response.json();
        throw new Error(error.detail || "移除失败");
      }
      return response.json();
    },
    onSuccess: () => {
      setIsInWatchlist(false);
      queryClient.invalidateQueries({ queryKey: ["watchlist"] });
      queryClient.invalidateQueries({ queryKey: ["watchlist-check", tickerForApi] });
    }
  });

  // 转换日线数据
  const dayChartData: KlineDataPoint[] = useMemo(() => {
    if (!dayData || !dayData.candles) return [];
    return dayData.candles.map(c => ({
      // 直接从timestamp字符串提取日期，避免时区转换问题
      date: c.timestamp.slice(0, 10).replace(/-/g, ''),
      open: c.open,
      high: c.high,
      low: c.low,
      close: c.close,
      volume: c.volume || 0,
    }));
  }, [dayData]);

  // 转换30分钟数据
  const mins30ChartData: KlineDataPoint[] = useMemo(() => {
    if (!mins30Data || !mins30Data.candles) return [];
    return mins30Data.candles.map(c => ({
      date: String(Math.floor(new Date(c.timestamp).getTime() / 1000) + 8 * 3600),
      open: c.open,
      high: c.high,
      low: c.low,
      close: c.close,
      volume: c.volume || 0,
    }));
  }, [mins30Data]);

  // 获取最后一个交易日的收盘价和前日涨跌幅
  const { lastClose, prevDayChange } = useMemo(() => {
    if (!dayData || dayData.candles.length === 0) {
      return { lastClose: null, prevDayChange: null };
    }
    const candles = dayData.candles;
    const lastClose = candles[candles.length - 1].close;

    // 计算昨日涨跌幅（昨日收盘相对前日收盘）
    let prevDayChange = null;
    if (candles.length >= 3) {
      const yesterdayClose = candles[candles.length - 2].close;
      const prevClose = candles[candles.length - 3].close;
      prevDayChange = ((yesterdayClose - prevClose) / prevClose) * 100;
    }

    return { lastClose, prevDayChange };
  }, [dayData]);

  // 合并公司信息为一段
  const companyInfoText = useMemo(() => {
    const parts: string[] = [];
    if (symbol.introduction) parts.push(symbol.introduction);
    if (symbol.mainBusiness) parts.push(`主营业务：${symbol.mainBusiness}`);
    if (symbol.businessScope) parts.push(`经营范围：${symbol.businessScope}`);
    return parts.join(' ');
  }, [symbol]);

  const industry = symbol.industryLv1 || "未知";

  // 获取板块信息
  const boardInfo = getBoardInfo(symbol.ticker);

  // 准备K线数据用于评估表单
  const klineDataForEval = useMemo(() => {
    if (!dayData) return null;
    return {
      ticker: tickerForApi,
      timeframe: "day",
      candles: dayData.candles.map(c => ({
        timestamp: c.timestamp,
        open: c.open,
        high: c.high,
        low: c.low,
        close: c.close,
        volume: c.volume,
        ma5: c.ma5,
        ma10: c.ma10,
        ma20: c.ma20,
        ma50: c.ma50,
      }))
    };
  }, [dayData, tickerForApi]);

  // 获取K线最后日期
  const klineEndDateForEval = useMemo(() => {
    if (!dayData || dayData.candles.length === 0) return "";
    const lastCandle = dayData.candles[dayData.candles.length - 1];
    const date = new Date(lastCandle.timestamp);
    return date.toISOString().split('T')[0];
  }, [dayData]);

  return (
    <article className="watchlist-card" ref={cardRef}>
      {/* 头部信息 */}
      <header className="watchlist-card__header">
        <div className="watchlist-card__title-row">
          <h3 className="watchlist-card__name">
            {symbol.name}
            {boardInfo.label && (
              <span className={`board-tag ${boardInfo.className}`}>{boardInfo.label}</span>
            )}
            <span className="watchlist-card__ticker">{symbol.ticker}</span>
            {symbol.positioning && (
              <span className="watchlist-card__positioning">{symbol.positioning}</span>
            )}
            <div className="watchlist-card__sector-wrapper" ref={sectorDropdownRef}>
              <span
                className="watchlist-card__sector watchlist-card__sector--clickable"
                onClick={(e) => {
                  e.stopPropagation();
                  setShowSectorDropdown(!showSectorDropdown);
                }}
              >
                {sector || '未分类'}
                <span className="watchlist-card__sector-arrow">▼</span>
              </span>
              {showSectorDropdown && (
                <div className="watchlist-card__sector-dropdown">
                  {availableSectors.map((s) => (
                    <div
                      key={s}
                      className={`watchlist-card__sector-option ${s === sector ? 'watchlist-card__sector-option--active' : ''}`}
                      onClick={(e) => {
                        e.stopPropagation();
                        if (s !== sector) {
                          updateSectorMutation.mutate(s);
                        } else {
                          setShowSectorDropdown(false);
                        }
                      }}
                    >
                      {s}
                      {s === sector && <span className="watchlist-card__sector-check">✓</span>}
                    </div>
                  ))}
                </div>
              )}
            </div>
            <button
              className="watchlist-card__trade-mini watchlist-card__trade-mini--buy"
              onClick={() => setTradeDialog({ type: "buy" })}
              disabled={!accountData || accountData.cash <= 0}
              title="买入"
            >
              买
            </button>
            <button
              className="watchlist-card__trade-mini watchlist-card__trade-mini--sell"
              onClick={() => setTradeDialog({ type: "sell" })}
              disabled={!positionData?.has_position}
              title="卖出"
            >
              卖
            </button>
            <button
              className={`watchlist-card__focus-btn ${symbol.isFocus ? "watchlist-card__focus-btn--active" : ""} ${toggleFocusMutation.isPending ? "watchlist-card__focus-btn--loading" : ""}`}
              onClick={() => {
                console.log('Focus button clicked for', symbol.ticker, 'current isFocus:', symbol.isFocus);
                toggleFocusMutation.mutate();
              }}
              disabled={toggleFocusMutation.isPending}
              title={toggleFocusMutation.isPending ? "处理中..." : (symbol.isFocus ? "取消重点关注" : "重点关注")}
            >
              {toggleFocusMutation.isPending ? "⌛" : (symbol.isFocus ? "★" : "☆")}
            </button>
            {positionData?.has_position && positionData.position && (
              <span className="watchlist-card__position-mini">
                {positionData.position.shares.toLocaleString()}股
                <span style={{ color: positionData.position.pnl_pct >= 0 ? "#ef5f7c" : "#4dd4ac" }}>
                  {positionData.position.pnl_pct >= 0 ? "+" : ""}{positionData.position.pnl_pct.toFixed(1)}%
                </span>
              </span>
            )}
          </h3>
          <div className="watchlist-card__actions">
            <button
              className="watchlist-card__earnings-btn"
              onClick={() => setIsEarningsExpanded(!isEarningsExpanded)}
            >
              {isEarningsExpanded ? "收起业绩" : "业绩"}
            </button>
            <button
              className="watchlist-card__detail-btn"
              onClick={() => setIsExpanded(!isExpanded)}
            >
              {isExpanded ? "收起" : "详情"}
            </button>
            {isInWatchlist === null ? (
              <button className="watchlist-card__add-btn" disabled>
                ...
              </button>
            ) : isInWatchlist ? (
              <button
                className="watchlist-card__remove-btn"
                onClick={() => removeFromWatchlist.mutate()}
                disabled={removeFromWatchlist.isPending}
              >
                {removeFromWatchlist.isPending ? "移除中..." : "移除"}
              </button>
            ) : (
              <button
                className="watchlist-card__add-btn"
                onClick={() => addToWatchlist.mutate()}
                disabled={addToWatchlist.isPending}
              >
                {addToWatchlist.isPending ? "添加中..." : "➕ 自选"}
              </button>
            )}
          </div>
        </div>
        <div className="watchlist-card__meta">
          {realtimePrice ? (
            <span className={`watchlist-card__price watchlist-card__price--${realtimePrice.change >= 0 ? 'up' : 'down'}`}>
              ¥{realtimePrice.price.toFixed(2)}
              <span className="watchlist-card__change">
                今 {realtimePrice.change >= 0 ? '+' : ''}{realtimePrice.changePercent.toFixed(2)}%
              </span>
            </span>
          ) : lastClose !== null && (
            <span className="watchlist-card__price">¥{lastClose.toFixed(2)}</span>
          )}
          {prevDayChange !== null && (
            <span className={`watchlist-card__prev-change watchlist-card__prev-change--${prevDayChange >= 0 ? 'up' : 'down'}`}>
              昨 {prevDayChange >= 0 ? '+' : ''}{prevDayChange.toFixed(2)}%
            </span>
          )}
          {symbol.totalMv && (
            <span className="watchlist-card__badge">{(symbol.totalMv / 1e4).toFixed(0)}亿</span>
          )}
          {symbol.peTtm !== null && symbol.peTtm !== undefined && (
            <span className="watchlist-card__badge">PE {symbol.peTtm.toFixed(1)}</span>
          )}
          <span className="watchlist-card__industry">{industry}</span>
          {realtimePrice && (
            <span className="watchlist-card__live">🔴 {realtimePrice.lastUpdate}</span>
          )}
        </div>
      </header>

      {/* 双K线图区域 */}
      <div className="watchlist-card__charts">
        <div className="watchlist-card__chart">
          <div className="watchlist-card__chart-label">日线</div>
          {dayChartData.length > 0 ? (
            <KlineChart
              data={dayChartData}
              height={280}
              showVolume={true}
              showMACD={true}
              maConfig={maConfig}
              compact={true}
            />
          ) : (
            <div className="watchlist-card__loading">加载日线...</div>
          )}
        </div>
        <div className="watchlist-card__chart">
          <div className="watchlist-card__chart-label">30分钟</div>
          {mins30ChartData.length > 0 ? (
            <KlineChart
              data={mins30ChartData}
              height={280}
              showVolume={true}
              showMACD={true}
              maConfig={maConfig}
              compact={true}
            />
          ) : (
            <div className="watchlist-card__loading">加载30分钟...</div>
          )}
        </div>
      </div>

      {/* K线标注评估表单 - 始终显示 */}
      <KlineEvaluationForm
        ticker={tickerForApi}
        stockName={symbol.name}
        timeframe="day"
        klineEndDate={klineEndDateForEval}
        priceAtEval={lastClose}
        klineData={klineDataForEval}
        chartRef={cardRef}
      />

      {/* 业绩预告和业绩快报 */}
      {isEarningsExpanded && (
        <div className="watchlist-card__earnings">
          <h4 className="watchlist-card__earnings-title">业绩数据（2025-2026年）</h4>
          {earningsLoading ? (
            <div className="watchlist-card__loading">加载业绩数据...</div>
          ) : (
            <>
              {/* 业绩预告 */}
              {earningsData?.forecasts && earningsData.forecasts.length > 0 ? (
                <div className="watchlist-card__earnings-section">
                  <h5 className="watchlist-card__earnings-subtitle">业绩预告</h5>
                  {earningsData.forecasts.map((f: any, idx: number) => (
                    <div key={idx} className="watchlist-card__earnings-item">
                      <div className="watchlist-card__earnings-row">
                        <span className="watchlist-card__earnings-label">报告期：</span>
                        <span>{f.end_date?.slice(0, 4)}-{f.end_date?.slice(4, 6)}-{f.end_date?.slice(6, 8)}</span>
                        <span className="watchlist-card__earnings-label" style={{ marginLeft: '1rem' }}>公告日：</span>
                        <span>{f.ann_date?.slice(0, 4)}-{f.ann_date?.slice(4, 6)}-{f.ann_date?.slice(6, 8)}</span>
                      </div>
                      <div className="watchlist-card__earnings-row">
                        <span className={`watchlist-card__earnings-type watchlist-card__earnings-type--${
                          f.type?.includes('增') || f.type?.includes('盈') ? 'positive' :
                          f.type?.includes('减') || f.type?.includes('亏') ? 'negative' : 'neutral'
                        }`}>
                          {f.type || '未知'}
                        </span>
                        {(f.p_change_min !== null || f.p_change_max !== null) && (
                          <span className="watchlist-card__earnings-change">
                            预计变动：{f.p_change_min?.toFixed(1) ?? '?'}% ~ {f.p_change_max?.toFixed(1) ?? '?'}%
                          </span>
                        )}
                      </div>
                      {(f.net_profit_min !== null || f.net_profit_max !== null) && (
                        <div className="watchlist-card__earnings-row">
                          <span className="watchlist-card__earnings-label">预计净利润：</span>
                          <span>
                            {f.net_profit_min !== null ? (f.net_profit_min / 10000).toFixed(2) : '?'}亿 ~
                            {f.net_profit_max !== null ? (f.net_profit_max / 10000).toFixed(2) : '?'}亿
                          </span>
                          {f.last_parent_net !== null && (
                            <span className="watchlist-card__earnings-label" style={{ marginLeft: '0.5rem' }}>
                              (上年同期: {(f.last_parent_net / 10000).toFixed(2)}亿)
                            </span>
                          )}
                        </div>
                      )}
                      {f.summary && (
                        <div className="watchlist-card__earnings-summary">{f.summary}</div>
                      )}
                      {f.change_reason && !f.summary && (
                        <div className="watchlist-card__earnings-summary">{f.change_reason}</div>
                      )}
                    </div>
                  ))}
                </div>
              ) : (
                <div className="watchlist-card__earnings-empty">暂无2025-2026年业绩预告</div>
              )}

              {/* 业绩快报 */}
              {earningsData?.expresses && earningsData.expresses.length > 0 ? (
                <div className="watchlist-card__earnings-section">
                  <h5 className="watchlist-card__earnings-subtitle">业绩快报</h5>
                  {earningsData.expresses.map((e: any, idx: number) => (
                    <div key={idx} className="watchlist-card__earnings-item">
                      <div className="watchlist-card__earnings-row">
                        <span className="watchlist-card__earnings-label">报告期：</span>
                        <span>{e.end_date?.slice(0, 4)}-{e.end_date?.slice(4, 6)}-{e.end_date?.slice(6, 8)}</span>
                        <span className="watchlist-card__earnings-label" style={{ marginLeft: '1rem' }}>公告日：</span>
                        <span>{e.ann_date?.slice(0, 4)}-{e.ann_date?.slice(4, 6)}-{e.ann_date?.slice(6, 8)}</span>
                      </div>
                      <div className="watchlist-card__earnings-row">
                        {e.revenue !== null && (
                          <span>营收：{(e.revenue / 1e8).toFixed(2)}亿</span>
                        )}
                        {e.n_income !== null && (
                          <span style={{ marginLeft: '1rem' }}>净利润：{(e.n_income / 1e8).toFixed(2)}亿</span>
                        )}
                      </div>
                      <div className="watchlist-card__earnings-row">
                        {e.yoy_sales !== null && (
                          <span className={e.yoy_sales >= 0 ? 'text-positive' : 'text-negative'}>
                            营收同比：{e.yoy_sales >= 0 ? '+' : ''}{e.yoy_sales.toFixed(2)}%
                          </span>
                        )}
                        {e.yoy_net_profit !== null && (
                          <span className={e.yoy_net_profit >= 0 ? 'text-positive' : 'text-negative'} style={{ marginLeft: '1rem' }}>
                            净利润同比：{e.yoy_net_profit >= 0 ? '+' : ''}{e.yoy_net_profit.toFixed(2)}%
                          </span>
                        )}
                      </div>
                      {(e.diluted_eps !== null || e.diluted_roe !== null) && (
                        <div className="watchlist-card__earnings-row">
                          {e.diluted_eps !== null && <span>EPS：{e.diluted_eps.toFixed(3)}</span>}
                          {e.diluted_roe !== null && <span style={{ marginLeft: '1rem' }}>ROE：{e.diluted_roe.toFixed(2)}%</span>}
                        </div>
                      )}
                    </div>
                  ))}
                </div>
              ) : (
                <div className="watchlist-card__earnings-empty">暂无2025-2026年业绩快报</div>
              )}
            </>
          )}
        </div>
      )}

      {/* 展开的公司详情 */}
      {isExpanded && (
        <div className="watchlist-card__details">
          {/* 概念板块 */}
          {conceptsData && conceptsData.concepts && conceptsData.concepts.length > 0 && (
            <div className="watchlist-card__concepts">
              <span className="watchlist-card__concepts-label">概念：</span>
              {conceptsData.concepts.slice(0, 15).map((concept: string) => (
                <span key={concept} className="watchlist-card__concept-tag">{concept}</span>
              ))}
              {conceptsData.concepts.length > 15 && (
                <span className="watchlist-card__concept-more">+{conceptsData.concepts.length - 15}</span>
              )}
            </div>
          )}
          {/* 公司信息（合并为一段） */}
          {companyInfoText && (
            <p className="watchlist-card__company-info">{companyInfoText}</p>
          )}
        </div>
      )}

      {/* 交易对话框 */}
      {tradeDialog && (
        <TradeDialog
          type={tradeDialog.type}
          ticker={tickerForApi}
          stockName={symbol.name}
          currentPrice={realtimePrice?.price ?? lastClose}
          availableCash={accountData?.cash ?? 0}
          holdingShares={positionData?.position?.shares ?? 0}
          costPrice={positionData?.position?.cost_price ?? 0}
          onClose={() => setTradeDialog(null)}
          onSuccess={() => {
            queryClient.invalidateQueries({ queryKey: ["simulated-position-check", tickerForApi] });
          }}
        />
      )}
    </article>
  );
}
