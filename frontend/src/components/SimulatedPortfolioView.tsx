import { useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { apiFetch } from "../utils/api";

interface AccountData {
  initial_capital: number;
  cash: number;
  position_value: number;
  total_value: number;
  total_pnl: number;
  total_pnl_pct: number;
  position_count: number;
}

interface PositionItem {
  ticker: string;
  stock_name: string;
  shares: number;
  cost_price: number;
  cost_amount: number;
  current_price: number | null;
  current_value: number;
  pnl: number;
  pnl_pct: number;
  position_pct: number;
  first_buy_date: string;
  holding_days: number;
}

interface TradeItem {
  id: number;
  ticker: string;
  stock_name: string;
  trade_type: string;
  trade_date: string;
  trade_price: number;
  shares: number;
  amount: number;
  position_pct: number | null;
  realized_pnl: number | null;
  realized_pnl_pct: number | null;
  note: string | null;
  created_at: string | null;
}

async function fetchAccount(): Promise<AccountData> {
  const response = await apiFetch("/api/simulated/account");
  if (!response.ok) throw new Error("Failed to fetch account");
  return response.json();
}

async function fetchPositions(): Promise<{ positions: PositionItem[]; total: number }> {
  const response = await apiFetch("/api/simulated/positions");
  if (!response.ok) throw new Error("Failed to fetch positions");
  return response.json();
}

async function fetchTrades(limit: number): Promise<{ trades: TradeItem[]; total: number }> {
  const response = await apiFetch(`/api/simulated/trades?limit=${limit}`);
  if (!response.ok) throw new Error("Failed to fetch trades");
  return response.json();
}

function formatNumber(num: number): string {
  if (num >= 100000000) {
    return (num / 100000000).toFixed(2) + "亿";
  }
  if (num >= 10000) {
    return (num / 10000).toFixed(2) + "万";
  }
  return num.toLocaleString("zh-CN", { maximumFractionDigits: 2 });
}

function formatCurrency(num: number): string {
  return "¥" + formatNumber(num);
}

export function SimulatedPortfolioView() {
  const [activeTab, setActiveTab] = useState<"positions" | "trades">("positions");

  const { data: account, isLoading: accountLoading } = useQuery({
    queryKey: ["simulated-account"],
    queryFn: fetchAccount,
    staleTime: 30000,
    refetchInterval: 30000,
  });

  const { data: positionsData, isLoading: positionsLoading } = useQuery({
    queryKey: ["simulated-positions"],
    queryFn: fetchPositions,
    staleTime: 30000,
    refetchInterval: 30000,
  });

  const { data: tradesData, isLoading: tradesLoading } = useQuery({
    queryKey: ["simulated-trades"],
    queryFn: () => fetchTrades(100),
    staleTime: 60000,
  });

  const positions = positionsData?.positions ?? [];
  const trades = tradesData?.trades ?? [];

  return (
    <div className="simulated-portfolio">
      {/* 账户概览 */}
      <div className="simulated-portfolio__header">
        <h2 className="simulated-portfolio__title">持仓</h2>
        {accountLoading ? (
          <div className="simulated-portfolio__loading">加载中...</div>
        ) : account ? (
          <div className="simulated-portfolio__account">
            <div className="account-card">
              <div className="account-card__label">总资产</div>
              <div className="account-card__value account-card__value--large">
                {formatCurrency(account.total_value)}
              </div>
            </div>
            <div className="account-card">
              <div className="account-card__label">总盈亏</div>
              <div
                className={`account-card__value ${
                  account.total_pnl >= 0 ? "account-card__value--positive" : "account-card__value--negative"
                }`}
              >
                {account.total_pnl >= 0 ? "+" : ""}
                {formatCurrency(account.total_pnl)}
                <span className="account-card__pct">
                  ({account.total_pnl >= 0 ? "+" : ""}
                  {account.total_pnl_pct.toFixed(2)}%)
                </span>
              </div>
            </div>
            <div className="account-card">
              <div className="account-card__label">可用现金</div>
              <div className="account-card__value">{formatCurrency(account.cash)}</div>
            </div>
            <div className="account-card">
              <div className="account-card__label">持仓市值</div>
              <div className="account-card__value">{formatCurrency(account.position_value)}</div>
            </div>
            <div className="account-card">
              <div className="account-card__label">持仓数</div>
              <div className="account-card__value">{account.position_count}</div>
            </div>
          </div>
        ) : null}
      </div>

      {/* Tab 切换 */}
      <div className="simulated-portfolio__tabs">
        <button
          className={`simulated-portfolio__tab ${activeTab === "positions" ? "simulated-portfolio__tab--active" : ""}`}
          onClick={() => setActiveTab("positions")}
        >
          当前持仓 ({positions.length})
        </button>
        <button
          className={`simulated-portfolio__tab ${activeTab === "trades" ? "simulated-portfolio__tab--active" : ""}`}
          onClick={() => setActiveTab("trades")}
        >
          交易记录 ({tradesData?.total ?? 0})
        </button>
      </div>

      {/* 持仓列表 */}
      {activeTab === "positions" && (
        <div className="simulated-portfolio__content">
          {positionsLoading ? (
            <div className="simulated-portfolio__loading">加载中...</div>
          ) : positions.length === 0 ? (
            <div className="simulated-portfolio__empty">暂无持仓</div>
          ) : (
            <table className="positions-table">
              <thead>
                <tr>
                  <th>股票</th>
                  <th>持仓</th>
                  <th>成本价</th>
                  <th>现价</th>
                  <th>市值</th>
                  <th>盈亏</th>
                  <th>仓位</th>
                  <th>持有天数</th>
                </tr>
              </thead>
              <tbody>
                {positions.map((pos) => (
                  <tr key={pos.ticker}>
                    <td>
                      <div className="positions-table__stock">
                        <span className="positions-table__name">{pos.stock_name}</span>
                        <span className="positions-table__ticker">{pos.ticker}</span>
                      </div>
                    </td>
                    <td>{pos.shares.toLocaleString()}</td>
                    <td>¥{pos.cost_price.toFixed(2)}</td>
                    <td>¥{pos.current_price?.toFixed(2) ?? "-"}</td>
                    <td>{formatCurrency(pos.current_value)}</td>
                    <td
                      className={pos.pnl >= 0 ? "positions-table__positive" : "positions-table__negative"}
                    >
                      {pos.pnl >= 0 ? "+" : ""}
                      {formatCurrency(pos.pnl)}
                      <br />
                      <span className="positions-table__pct">
                        ({pos.pnl >= 0 ? "+" : ""}
                        {pos.pnl_pct.toFixed(2)}%)
                      </span>
                    </td>
                    <td>{pos.position_pct.toFixed(1)}%</td>
                    <td>{pos.holding_days}天</td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}
        </div>
      )}

      {/* 交易记录 */}
      {activeTab === "trades" && (
        <div className="simulated-portfolio__content">
          {tradesLoading ? (
            <div className="simulated-portfolio__loading">加载中...</div>
          ) : trades.length === 0 ? (
            <div className="simulated-portfolio__empty">暂无交易记录</div>
          ) : (
            <table className="trades-table">
              <thead>
                <tr>
                  <th>日期</th>
                  <th>股票</th>
                  <th>类型</th>
                  <th>价格</th>
                  <th>数量</th>
                  <th>金额</th>
                  <th>盈亏</th>
                  <th>备注</th>
                </tr>
              </thead>
              <tbody>
                {trades.map((trade) => (
                  <tr key={trade.id}>
                    <td>{trade.trade_date}</td>
                    <td>
                      <div className="trades-table__stock">
                        <span className="trades-table__name">{trade.stock_name}</span>
                        <span className="trades-table__ticker">{trade.ticker}</span>
                      </div>
                    </td>
                    <td>
                      <span
                        className={`trades-table__type ${
                          trade.trade_type === "buy"
                            ? "trades-table__type--buy"
                            : "trades-table__type--sell"
                        }`}
                      >
                        {trade.trade_type === "buy" ? "买入" : "卖出"}
                      </span>
                    </td>
                    <td>¥{trade.trade_price.toFixed(2)}</td>
                    <td>{trade.shares.toLocaleString()}</td>
                    <td>{formatCurrency(trade.amount)}</td>
                    <td>
                      {trade.realized_pnl !== null ? (
                        <span
                          className={
                            trade.realized_pnl >= 0 ? "trades-table__positive" : "trades-table__negative"
                          }
                        >
                          {trade.realized_pnl >= 0 ? "+" : ""}
                          {formatCurrency(trade.realized_pnl)}
                          <br />
                          <span className="trades-table__pct">
                            ({trade.realized_pnl >= 0 ? "+" : ""}
                            {trade.realized_pnl_pct?.toFixed(2)}%)
                          </span>
                        </span>
                      ) : (
                        "-"
                      )}
                    </td>
                    <td className="trades-table__note">{trade.note ?? "-"}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}
        </div>
      )}
    </div>
  );
}
