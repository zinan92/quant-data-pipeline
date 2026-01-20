import { useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { buildApiUrl } from "../utils/api";
import "../styles/MomentumSignalsView.css";

interface MomentumSignal {
  concept_name: string;
  concept_code: string;
  signal_type: string;
  total_stocks: number;
  timestamp: string;
  details: string;
  // Surge-specific fields
  prev_up_count?: number;
  current_up_count?: number;
  delta_up_count?: number;
  threshold?: number;
  board_type?: string;
  // Kline-specific fields
  current_change_pct?: number;
  kline_info?: {
    trade_time: string;
    open: number;
    high: number;
    low: number;
    close: number;
    upper_shadow_ratio: number;
  };
}

interface MomentumSignalsResponse {
  success: boolean;
  timestamp: string;
  total_signals: number;
  surge_signals_count: number;
  kline_signals_count: number;
  signals: MomentumSignal[];
}

const fetchMomentumSignals = async (): Promise<MomentumSignalsResponse> => {
  const url = buildApiUrl("/api/concept-monitor/momentum-signals");
  const response = await fetch(url);
  if (!response.ok) {
    throw new Error("Failed to fetch momentum signals");
  }
  return response.json();
};

export function MomentumSignalsView() {
  const [autoRefresh, setAutoRefresh] = useState(true);

  const { data, isLoading, error, refetch } = useQuery({
    queryKey: ["momentumSignals"],
    queryFn: fetchMomentumSignals,
    refetchInterval: autoRefresh ? 60000 : false, // 60 seconds
    staleTime: 30000,
  });

  const renderSignalCard = (signal: MomentumSignal, index: number) => {
    const isSurge = signal.signal_type === "surge";
    const isKline = signal.signal_type === "kline_pattern";

    return (
      <div key={index} className="signal-card">
        <div className="signal-card__header">
          <div className="signal-card__title">
            <span className="signal-card__concept-name">{signal.concept_name}</span>
            <span className="signal-card__concept-code">({signal.concept_code})</span>
          </div>
          <span className={`signal-card__badge signal-card__badge--${signal.signal_type}`}>
            {isSurge ? "上涨激增" : "K线形态"}
          </span>
        </div>

        <div className="signal-card__body">
          <div className="signal-card__info">
            <div className="signal-card__info-item">
              <span className="signal-card__info-label">成分股:</span>
              <span className="signal-card__info-value">{signal.total_stocks}只</span>
            </div>
            <div className="signal-card__info-item">
              <span className="signal-card__info-label">触发时间:</span>
              <span className="signal-card__info-value">{signal.timestamp}</span>
            </div>
          </div>

          {isSurge && (
            <div className="signal-card__surge-details">
              <div className="signal-card__surge-row">
                <span className="signal-card__surge-label">上涨家数变化:</span>
                <span className="signal-card__surge-value">
                  {signal.prev_up_count} → {signal.current_up_count}
                  <span className="signal-card__surge-delta">
                    (+{signal.delta_up_count})
                  </span>
                </span>
              </div>
              <div className="signal-card__surge-row">
                <span className="signal-card__surge-label">板块类型:</span>
                <span className="signal-card__surge-value">
                  {signal.board_type === "large" ? "大板块" : "小板块"}
                  (阈值: {signal.threshold}只)
                </span>
              </div>
            </div>
          )}

          {isKline && signal.kline_info && (
            <div className="signal-card__kline-details">
              <div className="signal-card__kline-row">
                <span className="signal-card__kline-label">当前涨幅:</span>
                <span className={`signal-card__kline-value ${signal.current_change_pct! >= 0 ? 'signal-card__kline-value--positive' : 'signal-card__kline-value--negative'}`}>
                  {signal.current_change_pct?.toFixed(2)}%
                </span>
              </div>
              <div className="signal-card__kline-row">
                <span className="signal-card__kline-label">K线时间:</span>
                <span className="signal-card__kline-value">
                  {signal.kline_info.trade_time}
                </span>
              </div>
              <div className="signal-card__kline-row">
                <span className="signal-card__kline-label">开/收/高/低:</span>
                <span className="signal-card__kline-value">
                  {signal.kline_info.open.toFixed(2)} / {signal.kline_info.close.toFixed(2)} / {signal.kline_info.high.toFixed(2)} / {signal.kline_info.low.toFixed(2)}
                </span>
              </div>
              <div className="signal-card__kline-row">
                <span className="signal-card__kline-label">上影线比例:</span>
                <span className="signal-card__kline-value">
                  {signal.kline_info.upper_shadow_ratio}%
                </span>
              </div>
            </div>
          )}

          <div className="signal-card__details-text">
            {signal.details}
          </div>
        </div>
      </div>
    );
  };

  if (isLoading) {
    return (
      <div className="momentum-signals-view">
        <div className="momentum-signals-view__loading">加载中...</div>
      </div>
    );
  }

  if (error) {
    return (
      <div className="momentum-signals-view">
        <div className="momentum-signals-view__error">
          加载失败: {error.message}
        </div>
      </div>
    );
  }

  const surgeSignals = data?.signals.filter(s => s.signal_type === "surge") || [];
  const klineSignals = data?.signals.filter(s => s.signal_type === "kline_pattern") || [];

  return (
    <div className="momentum-signals-view">
      <div className="momentum-signals-view__header">
        <h1 className="momentum-signals-view__title">动量信号监控</h1>
        <div className="momentum-signals-view__controls">
          <label className="momentum-signals-view__auto-refresh">
            <input
              type="checkbox"
              checked={autoRefresh}
              onChange={(e) => setAutoRefresh(e.target.checked)}
            />
            自动刷新 (60秒)
          </label>
          <button
            className="momentum-signals-view__refresh-btn"
            onClick={() => refetch()}
          >
            手动刷新
          </button>
        </div>
      </div>

      <div className="momentum-signals-view__stats">
        <div className="momentum-signals-view__stat-card">
          <span className="momentum-signals-view__stat-label">总信号数</span>
          <span className="momentum-signals-view__stat-value">{data?.total_signals || 0}</span>
        </div>
        <div className="momentum-signals-view__stat-card momentum-signals-view__stat-card--surge">
          <span className="momentum-signals-view__stat-label">上涨激增</span>
          <span className="momentum-signals-view__stat-value">{data?.surge_signals_count || 0}</span>
        </div>
        <div className="momentum-signals-view__stat-card momentum-signals-view__stat-card--kline">
          <span className="momentum-signals-view__stat-label">K线形态</span>
          <span className="momentum-signals-view__stat-value">{data?.kline_signals_count || 0}</span>
        </div>
        <div className="momentum-signals-view__stat-card momentum-signals-view__stat-card--time">
          <span className="momentum-signals-view__stat-label">更新时间</span>
          <span className="momentum-signals-view__stat-value">{data?.timestamp || "-"}</span>
        </div>
      </div>

      {data?.total_signals === 0 ? (
        <div className="momentum-signals-view__empty">
          <p>暂无动量信号</p>
          <p className="momentum-signals-view__empty-hint">
            系统将每60秒检测一次，当板块出现上涨激增或特定K线形态时会自动触发信号
          </p>
        </div>
      ) : (
        <>
          {surgeSignals.length > 0 && (
            <div className="momentum-signals-view__section">
              <h2 className="momentum-signals-view__section-title">
                上涨激增信号 ({surgeSignals.length})
              </h2>
              <div className="momentum-signals-view__grid">
                {surgeSignals.map((signal, index) => renderSignalCard(signal, index))}
              </div>
            </div>
          )}

          {klineSignals.length > 0 && (
            <div className="momentum-signals-view__section">
              <h2 className="momentum-signals-view__section-title">
                K线形态信号 ({klineSignals.length})
              </h2>
              <div className="momentum-signals-view__grid">
                {klineSignals.map((signal, index) => renderSignalCard(signal, index))}
              </div>
            </div>
          )}
        </>
      )}
    </div>
  );
}
