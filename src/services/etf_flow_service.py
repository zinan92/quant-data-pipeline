from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

import pandas as pd

from src.config import get_settings


@dataclass
class EtfTrendData:
    """ETF趋势指标数据"""
    change_7d: Optional[float] = None
    change_30d: Optional[float] = None
    avg_amount_7d: Optional[float] = None
    avg_amount_30d: Optional[float] = None
    vol_ratio_7d: Optional[float] = None
    vol_ratio_30d: Optional[float] = None
    ma5: Optional[float] = None
    ma10: Optional[float] = None
    ma20: Optional[float] = None
    flow_7d: Optional[float] = None  # 7日累计净流入（亿）
    flow_30d: Optional[float] = None  # 30日累计净流入（亿）

    def to_dict(self) -> Dict[str, Any]:
        return {
            "change_7d": self.change_7d,
            "change_30d": self.change_30d,
            "avg_amount_7d": self.avg_amount_7d,
            "avg_amount_30d": self.avg_amount_30d,
            "vol_ratio_7d": self.vol_ratio_7d,
            "vol_ratio_30d": self.vol_ratio_30d,
            "ma5": self.ma5,
            "ma10": self.ma10,
            "ma20": self.ma20,
            "flow_7d": self.flow_7d,
            "flow_30d": self.flow_30d,
        }


@dataclass
class EtfFlowItem:
    name: str
    ticker: str
    flow_billion: float
    turnover_billion: Optional[float]
    change_pct: Optional[float]
    market_cap_billion: Optional[float]
    exposure: Optional[str]
    flow_ratio_pct: Optional[float]
    trend: Optional[EtfTrendData] = None

    def to_dict(self) -> Dict[str, Any]:
        result = {
            "name": self.name,
            "ticker": self.ticker,
            "flow_billion": self.flow_billion,
            "turnover_billion": self.turnover_billion,
            "change_pct": self.change_pct,
            "market_cap_billion": self.market_cap_billion,
            "exposure": self.exposure,
            "flow_ratio_pct": self.flow_ratio_pct,
        }
        if self.trend:
            result["trend"] = self.trend.to_dict()
        return result


class EtfFlowService:
    """Load ETF flow snapshot from the filtered daily CSV."""

    REQUIRED_COLUMNS = {
        "ETF名称",
        "Ticker",
        "资金流入流出(亿)",
        "成交额(亿)",
        "当日涨幅(%)",
        "总市值(亿)",
        "流入占总值比(%)",
        "超级行业组",
    }

    def __init__(self, data_file: Optional[Path] = None) -> None:
        settings = get_settings()
        self.data_file = data_file or settings.data_dir / "etf_daily_summary_filtered.csv"
        self.trend_file = settings.data_dir / "etf_trend_summary.csv"
        self.kline_dir = settings.data_dir / "etf_klines"
        self._trend_data: Optional[pd.DataFrame] = None

    def _load_trend_data(self) -> pd.DataFrame:
        """加载趋势指标数据"""
        if self._trend_data is not None:
            return self._trend_data

        if not self.trend_file.exists():
            return pd.DataFrame()

        self._trend_data = pd.read_csv(self.trend_file)
        return self._trend_data

    def _get_trend_for_ticker(self, ticker: str) -> Optional[EtfTrendData]:
        """获取单个ETF的趋势指标"""
        df_trend = self._load_trend_data()
        if df_trend.empty:
            return None

        row = df_trend[df_trend["ticker"] == ticker]
        if row.empty:
            return None

        row = row.iloc[0]
        return EtfTrendData(
            change_7d=self._safe_number(row.get("change_7d")),
            change_30d=self._safe_number(row.get("change_30d")),
            avg_amount_7d=self._safe_number(row.get("avg_amount_7d")),
            avg_amount_30d=self._safe_number(row.get("avg_amount_30d")),
            vol_ratio_7d=self._safe_number(row.get("vol_ratio_7d")),
            vol_ratio_30d=self._safe_number(row.get("vol_ratio_30d")),
            ma5=self._safe_number(row.get("ma5")),
            ma10=self._safe_number(row.get("ma10")),
            ma20=self._safe_number(row.get("ma20")),
            flow_7d=self._safe_number(row.get("flow_7d")),
            flow_30d=self._safe_number(row.get("flow_30d")),
        )

    def get_etf_kline(self, ticker: str, limit: int = 60) -> Optional[List[Dict[str, Any]]]:
        """获取单个ETF的K线数据"""
        # 将 ticker 转换为文件名格式
        filename = ticker.replace(".", "_") + ".csv"
        kline_file = self.kline_dir / filename

        if not kline_file.exists():
            return None

        df = pd.read_csv(kline_file)
        if df.empty:
            return None

        # 取最近 limit 条数据
        df = df.tail(limit)

        klines = []
        for _, row in df.iterrows():
            klines.append({
                "date": str(row["date"]),
                "open": float(row["open"]),
                "high": float(row["high"]),
                "low": float(row["low"]),
                "close": float(row["close"]),
                "volume": float(row.get("volume", 0)),
                "amount": float(row.get("amount_billion", 0)),
            })

        return klines

    def get_flow_summary(self, top_n: int = 5) -> Dict[str, Any]:
        df = self._load_dataframe()

        flows = df["资金流入流出(亿)"]
        turnovers = df["成交额(亿)"]
        avg_change_pct = df["当日涨幅(%)"].mean()

        inflow_total = float(flows[flows > 0].sum())
        outflow_total = float(flows[flows < 0].sum())
        net_flow = float(flows.sum())
        total_turnover = float(turnovers.sum())

        flow_denominator = inflow_total + abs(outflow_total)
        inflow_ratio = inflow_total / flow_denominator if flow_denominator > 0 else 0.0

        # 宽基指数 - 不再显示
        broad_index_names = ["沪深300ETF", "创业板ETF", "科创50ETF", "恒生科技ETF"]

        # 行业ETF（非宽基指数），按涨跌幅降序排列（先涨后跌）
        industry_df = df[~df["ETF名称"].isin(broad_index_names)]
        sorted_df = industry_df.sort_values("当日涨幅(%)", ascending=False)
        all_etfs = self._build_items(sorted_df)

        file_mtime = datetime.fromtimestamp(self.data_file.stat().st_mtime)

        return {
            "as_of": file_mtime.strftime("%Y-%m-%d"),
            "source": self.data_file.name,
            "summary": {
                "net_flow_billion": round(net_flow, 2),
                "inflow_billion": round(inflow_total, 2),
                "outflow_billion": round(outflow_total, 2),
                "turnover_billion": round(total_turnover, 2),
                "avg_change_pct": round(avg_change_pct, 2) if pd.notna(avg_change_pct) else None,
                "inflow_ratio": round(inflow_ratio, 4),
            },
            "all_etfs": [item.to_dict() for item in all_etfs],
        }

    def _load_dataframe(self) -> pd.DataFrame:
        if not self.data_file.exists():
            raise FileNotFoundError(f"ETF summary file not found: {self.data_file}")

        df = pd.read_csv(self.data_file)
        missing_cols = self.REQUIRED_COLUMNS - set(df.columns)
        if missing_cols:
            raise ValueError(f"ETF summary file missing columns: {', '.join(sorted(missing_cols))}")

        numeric_cols = ["资金流入流出(亿)", "成交额(亿)", "当日涨幅(%)", "总市值(亿)", "流入占总值比(%)"]
        for col in numeric_cols:
            df[col] = pd.to_numeric(df[col], errors="coerce").fillna(0)

        df["ETF名称"] = df["ETF名称"].fillna("未知ETF")
        df["Ticker"] = df["Ticker"].fillna("未知代码")
        df["超级行业组"] = df["超级行业组"].fillna("")

        return df

    def _build_items(self, df: pd.DataFrame) -> List[EtfFlowItem]:
        items: List[EtfFlowItem] = []
        for _, row in df.iterrows():
            ticker = str(row["Ticker"])
            trend = self._get_trend_for_ticker(ticker)
            items.append(
                EtfFlowItem(
                    name=str(row["ETF名称"]),
                    ticker=ticker,
                    flow_billion=round(float(row["资金流入流出(亿)"]), 2),
                    turnover_billion=self._safe_number(row["成交额(亿)"]),
                    change_pct=self._safe_number(row["当日涨幅(%)"]),
                    market_cap_billion=self._safe_number(row["总市值(亿)"]),
                    exposure=str(row["超级行业组"]) if pd.notna(row["超级行业组"]) else None,
                    flow_ratio_pct=self._safe_number(row["流入占总值比(%)"]),
                    trend=trend,
                )
            )
        return items

    @staticmethod
    def _safe_number(value: Any) -> Optional[float]:
        if pd.isna(value):
            return None
        return round(float(value), 2)
