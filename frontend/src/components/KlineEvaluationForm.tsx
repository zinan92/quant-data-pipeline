import { useState, useEffect } from "react";
import html2canvas from "html2canvas";
import { apiFetch } from "../utils/api";
import { TradeDialog } from "./TradeDialog";
import { useQuery } from "@tanstack/react-query";

interface Props {
  ticker: string;
  stockName: string;
  timeframe: string;
  klineEndDate: string;
  priceAtEval: number | null;
  klineData: any;  // K线数据JSON
  chartRef: React.RefObject<HTMLElement>;  // K线图容器的ref
  onSubmitSuccess?: () => void;
}

export function KlineEvaluationForm({
  ticker,
  stockName,
  timeframe,
  klineEndDate,
  priceAtEval,
  klineData,
  chartRef,
  onSubmitSuccess
}: Props) {
  const [description, setDescription] = useState("");
  const [score, setScore] = useState<number | "">("");
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [submitResult, setSubmitResult] = useState<{ success: boolean; message: string } | null>(null);
  const [existingEvalId, setExistingEvalId] = useState<number | null>(null);
  const [showBuyDialog, setShowBuyDialog] = useState(false);
  const [showBuyPrompt, setShowBuyPrompt] = useState(false);

  // 获取模拟账户信息
  const { data: accountData } = useQuery({
    queryKey: ["simulated-account"],
    queryFn: async () => {
      const response = await apiFetch("/api/simulated/account");
      if (!response.ok) return null;
      return response.json();
    },
    staleTime: 30000,
  });

  // 加载该股票最近的评估记录
  useEffect(() => {
    const loadExistingEvaluation = async () => {
      try {
        const response = await apiFetch(`/api/evaluations?ticker=${ticker}&limit=1`);
        if (response.ok) {
          const data = await response.json();
          if (data.evaluations && data.evaluations.length > 0) {
            const latest = data.evaluations[0];
            setDescription(latest.description || "");
            setScore(latest.score);
            setExistingEvalId(latest.id);
          }
        }
      } catch (e) {
        console.error("Failed to load existing evaluation:", e);
      }
    };

    if (ticker) {
      loadExistingEvaluation();
    }
  }, [ticker]);

  const handleSubmit = async () => {
    if (score === "" || score < 0 || score > 10) {
      setSubmitResult({ success: false, message: "请输入0-10的评分" });
      return;
    }

    setIsSubmitting(true);
    setSubmitResult(null);

    try {
      // 截图K线图
      let screenshotBase64 = null;
      if (chartRef.current) {
        try {
          const canvas = await html2canvas(chartRef.current, {
            backgroundColor: "#161b2b",
            scale: 2,  // 高清截图
            logging: false,
          });
          screenshotBase64 = canvas.toDataURL("image/png");
        } catch (e) {
          console.error("Screenshot failed:", e);
        }
      }

      const response = await apiFetch("/api/evaluations", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          ticker,
          stock_name: stockName,
          timeframe,
          kline_end_date: klineEndDate,
          description: description || null,
          score: Number(score),
          screenshot_base64: screenshotBase64,
          kline_data: klineData,
          price_at_eval: priceAtEval,
        }),
      });

      if (!response.ok) {
        const error = await response.json();
        throw new Error(error.detail || "提交失败");
      }

      const result = await response.json();
      const isUpdate = existingEvalId !== null;
      setSubmitResult({
        success: true,
        message: isUpdate
          ? `已更新！${result.tags?.length ? `标签: ${result.tags.join(", ")}` : ""}`
          : `已保存！${result.tags?.length ? `标签: ${result.tags.join(", ")}` : ""}`
      });

      // 更新 existingEvalId（新提交的记录ID）
      setExistingEvalId(result.id);

      // 不清空表单，保留描述和评分

      // 评分>=8时显示买入提示
      if (Number(score) >= 8) {
        setShowBuyPrompt(true);
      }

      if (onSubmitSuccess) {
        onSubmitSuccess();
      }
    } catch (error) {
      setSubmitResult({
        success: false,
        message: error instanceof Error ? error.message : "提交失败"
      });
    } finally {
      setIsSubmitting(false);
    }
  };

  const getScoreLabel = (s: number | ""): string => {
    if (s === "") return "";
    if (s >= 8) return "买入信号";
    if (s >= 5) return "观望";
    return "不操作";
  };

  const getScoreColor = (s: number | ""): string => {
    if (s === "") return "";
    if (s >= 8) return "#ef5f7c";  // 红色 - 买入
    if (s >= 5) return "#f5d05e";  // 黄色 - 观望
    return "#8f9bbd";  // 灰色 - 不操作
  };

  return (
    <div className="kline-eval-form">
      <div className="kline-eval-form__row">
        <textarea
          className="kline-eval-form__description"
          placeholder="描述K线特征（如：双底、MACD金叉、放量突破...）"
          value={description}
          onChange={(e) => setDescription(e.target.value)}
          rows={2}
        />
      </div>
      <div className="kline-eval-form__row kline-eval-form__row--inline">
        <div className="kline-eval-form__score-group">
          <label className="kline-eval-form__label">评分:</label>
          <input
            type="number"
            className="kline-eval-form__score-input"
            min={0}
            max={10}
            value={score}
            onChange={(e) => {
              const val = e.target.value;
              if (val === "") {
                setScore("");
              } else {
                const num = parseInt(val);
                if (!isNaN(num) && num >= 0 && num <= 10) {
                  setScore(num);
                }
              }
            }}
            placeholder="0-10"
          />
          {score !== "" && (
            <span
              className="kline-eval-form__score-label"
              style={{ color: getScoreColor(score) }}
            >
              {getScoreLabel(score)}
            </span>
          )}
        </div>
        <button
          className="kline-eval-form__submit"
          onClick={handleSubmit}
          disabled={isSubmitting || score === ""}
        >
          {isSubmitting ? "提交中..." : existingEvalId ? "更新标注" : "提交标注"}
        </button>
      </div>
      {submitResult && (
        <div
          className={`kline-eval-form__result ${submitResult.success ? "kline-eval-form__result--success" : "kline-eval-form__result--error"}`}
        >
          {submitResult.message}
        </div>
      )}

      {/* 评分>=8时的买入提示 */}
      {showBuyPrompt && accountData && accountData.cash > 0 && (
        <div className="kline-eval-form__buy-prompt">
          <span>评分达到买入信号，是否买入？</span>
          <button
            className="kline-eval-form__buy-btn"
            onClick={() => {
              setShowBuyPrompt(false);
              setShowBuyDialog(true);
            }}
          >
            立即买入
          </button>
          <button
            className="kline-eval-form__skip-btn"
            onClick={() => setShowBuyPrompt(false)}
          >
            跳过
          </button>
        </div>
      )}

      {/* 买入对话框 */}
      {showBuyDialog && (
        <TradeDialog
          type="buy"
          ticker={ticker}
          stockName={stockName}
          currentPrice={priceAtEval}
          availableCash={accountData?.cash ?? 0}
          onClose={() => setShowBuyDialog(false)}
        />
      )}
    </div>
  );
}
