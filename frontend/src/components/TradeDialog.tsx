import { useState, useEffect, useMemo } from "react";
import { useQueryClient } from "@tanstack/react-query";
import { apiFetch } from "../utils/api";

interface Props {
  type: "buy" | "sell";
  ticker: string;
  stockName: string;
  currentPrice: number | null;
  availableCash?: number;
  holdingShares?: number;
  costPrice?: number;
  onClose: () => void;
  onSuccess?: () => void;
}

export function TradeDialog({
  type,
  ticker,
  stockName,
  currentPrice,
  availableCash = 0,
  holdingShares = 0,
  costPrice = 0,
  onClose,
  onSuccess,
}: Props) {
  const [price, setPrice] = useState<string>(currentPrice?.toFixed(2) ?? "");
  const [pct, setPct] = useState<string>("20");
  const [note, setNote] = useState<string>("");
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [result, setResult] = useState<{ success: boolean; message: string } | null>(null);
  const queryClient = useQueryClient();

  // 计算预览信息
  const preview = useMemo(() => {
    const priceNum = parseFloat(price);
    const pctNum = parseFloat(pct);

    if (isNaN(priceNum) || priceNum <= 0 || isNaN(pctNum) || pctNum <= 0) {
      return null;
    }

    if (type === "buy") {
      const buyAmount = availableCash * (pctNum / 100);
      const shares = Math.floor(buyAmount / priceNum / 100) * 100;
      const actualAmount = shares * priceNum;

      return {
        shares,
        amount: actualAmount,
        afterCash: availableCash - actualAmount,
      };
    } else {
      // 卖出
      const sellShares = pctNum === 100 ? holdingShares : Math.floor(holdingShares * (pctNum / 100) / 100) * 100;
      const sellAmount = sellShares * priceNum;
      const costOfSold = (sellShares / holdingShares) * costPrice * holdingShares;
      const pnl = sellAmount - costOfSold;
      const pnlPct = costOfSold > 0 ? (pnl / costOfSold) * 100 : 0;

      return {
        shares: sellShares,
        amount: sellAmount,
        pnl,
        pnlPct,
        remainingShares: holdingShares - sellShares,
      };
    }
  }, [type, price, pct, availableCash, holdingShares, costPrice]);

  const handleSubmit = async () => {
    if (!preview || preview.shares <= 0) return;

    setIsSubmitting(true);
    setResult(null);

    try {
      const endpoint = type === "buy" ? "/api/simulated/buy" : "/api/simulated/sell";
      const body = type === "buy"
        ? {
            ticker,
            price: parseFloat(price),
            position_pct: parseFloat(pct),
            note: note || null,
          }
        : {
            ticker,
            price: parseFloat(price),
            sell_pct: parseFloat(pct),
            note: note || null,
          };

      const response = await apiFetch(endpoint, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(body),
      });

      const data = await response.json();

      if (data.success) {
        setResult({ success: true, message: data.message });
        // 刷新相关数据
        queryClient.invalidateQueries({ queryKey: ["simulated-account"] });
        queryClient.invalidateQueries({ queryKey: ["simulated-positions"] });
        queryClient.invalidateQueries({ queryKey: ["simulated-trades"] });

        if (onSuccess) {
          setTimeout(() => {
            onSuccess();
            onClose();
          }, 1500);
        }
      } else {
        setResult({ success: false, message: data.error || "操作失败" });
      }
    } catch (error) {
      setResult({
        success: false,
        message: error instanceof Error ? error.message : "操作失败",
      });
    } finally {
      setIsSubmitting(false);
    }
  };

  const quickPcts = type === "buy" ? [10, 20, 30, 50, 100] : [25, 50, 75, 100];

  return (
    <div className="trade-dialog-overlay" onClick={onClose}>
      <div className="trade-dialog" onClick={(e) => e.stopPropagation()}>
        <div className="trade-dialog__header">
          <h3 className="trade-dialog__title">
            {type === "buy" ? "买入" : "卖出"}
          </h3>
          <button className="trade-dialog__close" onClick={onClose}>
            ×
          </button>
        </div>

        <div className="trade-dialog__stock-info">
          <span className="trade-dialog__stock-name">{stockName}</span>
          <span className="trade-dialog__stock-ticker">{ticker}</span>
          <div className="trade-dialog__current-price">
            现价: <span>¥{currentPrice?.toFixed(2) ?? "-"}</span>
          </div>
          {type === "buy" && (
            <div className="trade-dialog__current-price">
              可用现金: <span>¥{availableCash.toLocaleString()}</span>
            </div>
          )}
          {type === "sell" && (
            <div className="trade-dialog__current-price">
              持有: <span>{holdingShares.toLocaleString()}股</span> 成本: <span>¥{costPrice.toFixed(2)}</span>
            </div>
          )}
        </div>

        <div className="trade-dialog__form-group">
          <label className="trade-dialog__label">
            {type === "buy" ? "买入价格" : "卖出价格"}
          </label>
          <input
            type="number"
            className="trade-dialog__input"
            value={price}
            onChange={(e) => setPrice(e.target.value)}
            placeholder="输入价格"
            step="0.01"
          />
        </div>

        <div className="trade-dialog__form-group">
          <label className="trade-dialog__label">
            {type === "buy" ? "仓位比例 (基于可用现金)" : "卖出比例 (基于持仓)"}
          </label>
          <input
            type="number"
            className="trade-dialog__input"
            value={pct}
            onChange={(e) => setPct(e.target.value)}
            placeholder="输入百分比"
            min={1}
            max={100}
          />
          <div className="trade-dialog__quick-btns">
            {quickPcts.map((p) => (
              <button
                key={p}
                type="button"
                className="trade-dialog__quick-btn"
                onClick={() => setPct(p.toString())}
              >
                {p}%
              </button>
            ))}
          </div>
        </div>

        <div className="trade-dialog__form-group">
          <label className="trade-dialog__label">备注（可选）</label>
          <input
            type="text"
            className="trade-dialog__input"
            value={note}
            onChange={(e) => setNote(e.target.value)}
            placeholder="如：突破买入、止盈卖出..."
          />
        </div>

        {preview && preview.shares > 0 && (
          <div className="trade-dialog__preview">
            <div className="trade-dialog__preview-row">
              <span className="trade-dialog__preview-label">
                {type === "buy" ? "买入数量" : "卖出数量"}
              </span>
              <span className="trade-dialog__preview-value">
                {preview.shares.toLocaleString()} 股
              </span>
            </div>
            <div className="trade-dialog__preview-row">
              <span className="trade-dialog__preview-label">成交金额</span>
              <span className="trade-dialog__preview-value">
                ¥{preview.amount.toLocaleString(undefined, { maximumFractionDigits: 2 })}
              </span>
            </div>
            {type === "buy" && preview.afterCash !== undefined && (
              <div className="trade-dialog__preview-row">
                <span className="trade-dialog__preview-label">剩余现金</span>
                <span className="trade-dialog__preview-value">
                  ¥{preview.afterCash.toLocaleString(undefined, { maximumFractionDigits: 2 })}
                </span>
              </div>
            )}
            {type === "sell" && preview.pnl !== undefined && (
              <>
                <div className="trade-dialog__preview-row">
                  <span className="trade-dialog__preview-label">预计盈亏</span>
                  <span
                    className="trade-dialog__preview-value"
                    style={{ color: preview.pnl >= 0 ? "#ef5f7c" : "#4dd4ac" }}
                  >
                    {preview.pnl >= 0 ? "+" : ""}
                    ¥{preview.pnl.toLocaleString(undefined, { maximumFractionDigits: 2 })}
                    ({preview.pnl >= 0 ? "+" : ""}
                    {preview.pnlPct?.toFixed(2)}%)
                  </span>
                </div>
                <div className="trade-dialog__preview-row">
                  <span className="trade-dialog__preview-label">剩余持仓</span>
                  <span className="trade-dialog__preview-value">
                    {preview.remainingShares?.toLocaleString()} 股
                  </span>
                </div>
              </>
            )}
          </div>
        )}

        {result && (
          <div
            className={`trade-dialog__result ${
              result.success ? "trade-dialog__result--success" : "trade-dialog__result--error"
            }`}
          >
            {result.message}
          </div>
        )}

        <div className="trade-dialog__actions">
          <button
            type="button"
            className="trade-dialog__btn trade-dialog__btn--cancel"
            onClick={onClose}
          >
            取消
          </button>
          <button
            type="button"
            className={`trade-dialog__btn trade-dialog__btn--${type}`}
            onClick={handleSubmit}
            disabled={isSubmitting || !preview || preview.shares <= 0}
          >
            {isSubmitting
              ? "处理中..."
              : type === "buy"
              ? "确认买入"
              : "确认卖出"}
          </button>
        </div>
      </div>
    </div>
  );
}
