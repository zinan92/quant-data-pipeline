import { useState } from "react";
import { Timeframe, MAConfig, MA_COLORS, MA_LABELS, hasAnyMAEnabled } from "../types";
import { TimeframeSwitcher } from "./TimeframeSwitcher";
import { useRefresh, useStatus } from "../hooks/useStatus";

interface Props {
  value: Timeframe;
  onChange: (timeframe: Timeframe) => void;
  options: Timeframe[];
  maConfig: MAConfig;
  onMAConfigChange: (config: MAConfig) => void;
  klineLimit: number;
  onKlineLimitChange: (limit: number) => void;
}

export function ControlPanel({ value, onChange, options, maConfig, onMAConfigChange, klineLimit, onKlineLimitChange }: Props) {
  const { data, isLoading, isError } = useStatus();
  const refresh = useRefresh();
  const [showMADropdown, setShowMADropdown] = useState(false);
  const [showKlineDropdown, setShowKlineDropdown] = useState(false);

  const lastUpdated = data?.last_refreshed
    ? new Date(data.last_refreshed).toLocaleString()
    : "尚未同步";

  const hasAnyMA = hasAnyMAEnabled(maConfig);

  const toggleMA = (key: keyof MAConfig) => {
    onMAConfigChange({
      ...maConfig,
      [key]: !maConfig[key]
    });
  };

  const toggleAllMA = () => {
    const newValue = !hasAnyMA;
    onMAConfigChange({
      ma5: newValue,
      ma10: newValue,
      ma20: newValue,
      ma50: newValue
    });
  };

  return (
    <div className="control-panel">
      <div className="control-panel__left">
        <TimeframeSwitcher value={value} options={options} onChange={onChange} />
        <div className="control-panel__ma-container">
          <button
            className={`control-panel__ma-toggle ${hasAnyMA ? "control-panel__ma-toggle--active" : ""}`}
            onClick={() => setShowMADropdown(!showMADropdown)}
          >
            MA均线 ▾
          </button>
          {showMADropdown && (
            <div className="control-panel__ma-dropdown">
              <button
                className="control-panel__ma-item control-panel__ma-item--all"
                onClick={toggleAllMA}
              >
                {hasAnyMA ? "全部关闭" : "全部开启"}
              </button>
              {(Object.keys(maConfig) as (keyof MAConfig)[]).map((key) => (
                <button
                  key={key}
                  className={`control-panel__ma-item ${maConfig[key] ? "control-panel__ma-item--active" : ""}`}
                  onClick={() => toggleMA(key)}
                >
                  <span
                    className="control-panel__ma-color"
                    style={{ backgroundColor: MA_COLORS[key] }}
                  />
                  {MA_LABELS[key]}
                  {maConfig[key] && <span className="control-panel__ma-check">✓</span>}
                </button>
              ))}
            </div>
          )}
        </div>
        <div className="control-panel__kline-container">
          <button
            className="control-panel__kline-toggle"
            onClick={() => setShowKlineDropdown(!showKlineDropdown)}
          >
            K线 {klineLimit}根 ▾
          </button>
          {showKlineDropdown && (
            <div className="control-panel__kline-dropdown">
              <div className="control-panel__kline-slider">
                <input
                  type="range"
                  min={50}
                  max={500}
                  step={10}
                  value={klineLimit}
                  onChange={(e) => onKlineLimitChange(parseInt(e.target.value, 10))}
                />
                <span className="control-panel__kline-value">{klineLimit}</span>
              </div>
              <div className="control-panel__kline-presets">
                {[100, 150, 200, 300, 500].map((v) => (
                  <button
                    key={v}
                    className={`control-panel__kline-preset ${klineLimit === v ? "control-panel__kline-preset--active" : ""}`}
                    onClick={() => onKlineLimitChange(v)}
                  >
                    {v}
                  </button>
                ))}
              </div>
            </div>
          )}
        </div>
      </div>
      <div className="control-panel__right">
        <span className="control-panel__status">
          {isLoading
            ? "状态加载中..."
            : isError
            ? "状态未知"
            : `最后更新：${lastUpdated}`}
        </span>
        <button
          className="control-panel__refresh"
          onClick={() => refresh.mutate()}
          disabled={refresh.isPending}
        >
          {refresh.isPending ? "刷新中..." : "手动刷新"}
        </button>
        {refresh.isError && (
          <span className="control-panel__error">刷新失败，请稍后重试</span>
        )}
      </div>
    </div>
  );
}
