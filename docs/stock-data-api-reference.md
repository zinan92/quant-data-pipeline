# 股票数据免费API参考手册

## 概述

本文档汇总了国内主要金融数据平台的免费API接口，包括新浪、腾讯、网易、雪球、东方财富等。

---

## 1. 行情数据对比

| 平台 | 实时行情 | K线数据 | 资金流向 | 特点 |
|------|---------|--------|---------|------|
| **新浪财经** | ✅ `hq.sinajs.cn` | ✅ 分钟/日线 | ❌ | 需Referer头，速度快 |
| **腾讯财经** | ✅ `qt.gtimg.cn` | ✅ 分钟/日/周 | ✅ 主力/散户 | 最稳定，数据全 |
| **网易财经** | ✅ | ✅ CSV格式 | ❌ | 财务报表详细，不复权 |
| **雪球** | ✅ | ✅ | ✅ | 需登录token |
| **东方财富** | ✅ | ✅ | ✅ | AKShare封装最全 |

---

## 2. 新闻/公告/异动数据对比

| 数据类型 | 新浪 | 腾讯 | 网易 | 雪球 | 东方财富(AKShare) |
|---------|------|------|------|------|------------------|
| **个股新闻** | ❌ | ❌ | ❌ | ✅ | ✅ `stock_news_em` |
| **公司公告** | ❌ | ❌ | ❌ | ⚠️ | ✅ 巨潮资讯 |
| **盘口异动** | ❌ | ❌ | ❌ | ❌ | ✅ `stock_changes_em` |
| **龙虎榜** | ❌ | ❌ | ❌ | ❌ | ✅ `stock_lhb_detail_em` |
| **涨停板** | ❌ | ❌ | ❌ | ❌ | ✅ `stock_zt_pool_em` |
| **财经快讯** | ✅ | ❌ | ❌ | ✅ | ✅ 多来源 |

---

## 3. 同花顺事件分类 vs 免费API对应

| 同花顺分类 | 免费API替代 | 数据源 | 可用性 |
|-----------|------------|--------|-------|
| **异动解读** | `stock_changes_em()` | 东方财富 | ✅ 盘口异动(火箭发射、大笔买入等) |
| **快讯** | `stock_news_em()` | 东方财富 | ✅ 个股新闻快讯 |
| **官方发布** | `stock_notice_report()` | 巨潮资讯 | ✅ 公司公告 |
| **新增概念** | 无直接API | - | ❌ 需付费或爬虫 |
| **财务披露** | `stock_yjyg_em()` | 东方财富 | ✅ 业绩预告 |
| | `stock_yjkb_em()` | 东方财富 | ✅ 业绩快报 |
| | `stock_yysj_em()` | 东方财富 | ✅ 预约披露时间 |
| **分红融资** | `stock_fhps_em()` | 东方财富 | ✅ 分红配送 |
| | `stock_gpzy_pledge_ratio_em()` | 东方财富 | ✅ 股权质押 |
| **股权变动** | `stock_circulate_stock_holder()` | 东方财富 | ✅ 流通股东变动 |
| | `stock_main_stock_holder()` | 东方财富 | ✅ 主要股东变动 |
| **交易提示** | `stock_dzjy_mrtj()` | 东方财富 | ✅ 大宗交易 |
| | `stock_lhb_detail_em()` | 东方财富 | ✅ 龙虎榜 |
| **经营运作** | 无直接API | - | ⚠️ 需从公告中解析 |
| **重大事项** | `stock_notice_report()` | 巨潮资讯 | ⚠️ 需筛选重大公告 |
| **其他事项** | 无直接API | - | ❌ 避险宝/维权无免费API |

---

## 4. 各平台API详细示例

### 4.1 新浪财经

**实时行情**
```python
import requests

headers = {"Referer": "https://finance.sina.com.cn/"}
url = "https://hq.sinajs.cn/list=sz000001,sh600519"
resp = requests.get(url, headers=headers)
print(resp.text)

# 返回格式:
# var hq_str_sz000001="平安银行,10.50,10.45,10.75,10.80,10.40,10.74,10.75,123456789,1350000000,..."
```

**K线数据**
```python
# 30分钟K线
url = "https://quotes.sina.cn/cn/api/json_v2.php/CN_MarketDataService.getKLineData"
params = {
    "symbol": "sz000001",
    "scale": 30,      # 30分钟
    "ma": "no",
    "datalen": 80
}
resp = requests.get(url, params=params)
```

**参考文档**: https://www.cnblogs.com/zeroes/p/sina_stock_api.html

---

### 4.2 腾讯财经

**实时行情**
```python
# 单只股票
url = "http://qt.gtimg.cn/q=sz000858"

# 多只股票
url = "http://qt.gtimg.cn/q=sz000858,sh600519,sz000001"

# 返回字段: 股票名称、今开、昨收、当前价、最高、最低、买一价、卖一价、成交量、成交额...
```

**资金流向**
```python
# 资金流向
url = "http://qt.gtimg.cn/q=ff_sz000858"
# 返回: 主力流入、主力流出、主力净流入、散户流入、散户流出...

# 盘口分析
url = "http://qt.gtimg.cn/q=s_pksz000858"
# 返回: 买盘大单、买盘小单、卖盘大单、卖盘小单
```

**K线数据**
```python
# 日K线
url = "http://data.gtimg.cn/flashdata/hushen/latest/daily/sz000002.js"

# 周K线
url = "http://data.gtimg.cn/flashdata/hushen/latest/weekly/sz000002.js"

# 分时图
url = "http://data.gtimg.cn/flashdata/hushen/minute/sz000001.js"

# 五天分时图
url = "http://data.gtimg.cn/flashdata/hushen/4day/sz/sz000002.js"

# 指定年份日K线 (17=2017年)
url = "http://data.gtimg.cn/flashdata/hushen/daily/17/sz000750.js"
```

**分时查询**
```python
url = "https://web.ifzq.gtimg.cn/appstock/app/minute/query?code=sh600519"
```

**参考文档**: https://developer.aliyun.com/article/545892

---

### 4.3 网易财经

**历史成交数据 (CSV格式)**
```python
# code: 0=上海, 1=深圳
# 601398 -> 0601398 (上海)
# 000001 -> 1000001 (深圳)

url = "http://quotes.money.163.com/service/chddata.html"
params = {
    "code": "0601398",
    "start": "20240101",
    "end": "20240601",
    "fields": "TCLOSE;HIGH;LOW;TOPEN;LCLOSE;CHG;PCHG;TURNOVER;VOTURNOVER;VATURNOVER;TCAP;MCAP"
}

# 字段说明:
# TCLOSE=收盘价, HIGH=最高价, LOW=最低价, TOPEN=开盘价
# LCLOSE=前收盘价, CHG=涨跌额, PCHG=涨跌幅
# TURNOVER=换手率, VOTURNOVER=成交量, VATURNOVER=成交金额
# TCAP=总市值, MCAP=流通市值
```

**财务报表**
```python
# 财务指标
url = "http://quotes.money.163.com/service/zycwzb_601398.html"

# 资产负债表
url = "http://quotes.money.163.com/service/zcfzb_601398.html"

# 利润表
url = "http://quotes.money.163.com/service/lrb_601398.html"

# 现金流表
url = "http://quotes.money.163.com/service/xjllb_601398.html"
```

**实时数据**
```python
url = "http://api.money.126.net/data/feed/0000001,0601857,1002024,money.api"
```

**注意**: 网易数据为不复权数据

**参考文档**: https://cloud.tencent.com/developer/article/2063536

---

### 4.4 雪球

**安装 pysnowball**
```bash
pip install pysnowball
```

**使用示例**
```python
import pysnowball as ball

# 需要先登录雪球网站获取token
ball.set_token('xq_a_token=651af***************031c96a315c;')

# 获取股票详情
ball.quote_detail('SH600519')

# 获取现金流
ball.cash_flow('SH600000')

# 获取K线
ball.kline('SH600519', begin='1664553600000', period='day', count=-120)
```

**直接API调用**
```python
# K线数据
url = "https://stock.xueqiu.com/v5/stock/chart/kline.json"
params = {
    "symbol": "SZ300396",
    "begin": "1664553600000",  # 13位时间戳
    "period": "day",           # day/week/month
    "type": "before",          # before=前复权
    "count": -120,
    "indicator": "kline"
}

# 分时数据
url = "https://stock.xueqiu.com/v5/stock/chart/minute.json?symbol=SZ002239&period=1d"

# 注意: 需要先访问 https://xueqiu.com/ 获取cookie
```

**参考文档**: https://github.com/uname-yang/pysnowball

---

### 4.5 东方财富 (通过AKShare)

**安装 AKShare**
```bash
pip install akshare
```

**盘口异动**
```python
import akshare as ak

# 盘口异动 (火箭发射、大笔买入、封涨停板等)
df = ak.stock_changes_em(symbol="sz000001")
print(df)
```

**个股新闻**
```python
df = ak.stock_news_em(symbol="000001")
```

**涨停板系列**
```python
# 涨停股池
df = ak.stock_zt_pool_em(date="20240106")

# 昨日涨停股池
df = ak.stock_zt_pool_previous_em(date="20240106")

# 强势股池
df = ak.stock_zt_pool_strong_em(date="20240106")

# 次新股池
df = ak.stock_zt_pool_sub_new_em(date="20240106")

# 炸板股池
df = ak.stock_zt_pool_zbgc_em(date="20240106")

# 跌停股池
df = ak.stock_zt_pool_dtgc_em(date="20240106")
```

**龙虎榜**
```python
df = ak.stock_lhb_detail_em(start_date="20240101", end_date="20240106")
```

**大宗交易**
```python
df = ak.stock_dzjy_mrtj(start_date="20240101", end_date="20240106")
```

**业绩预告/快报**
```python
# 业绩预告
df = ak.stock_yjyg_em(date="20240331")

# 业绩快报
df = ak.stock_yjkb_em(date="20240331")

# 预约披露时间
df = ak.stock_yysj_em(date="20240331")
```

**分红配送**
```python
df = ak.stock_fhps_em(date="20240630")
```

**股东信息**
```python
# 流通股东
df = ak.stock_circulate_stock_holder(symbol="000001")

# 主要股东
df = ak.stock_main_stock_holder(symbol="000001")
```

**财经快讯**
```python
# 财联社电报
df = ak.stock_info_global_cls()

# 新浪财经快讯
df = ak.stock_info_global_sina()

# 富途快讯
df = ak.stock_info_global_futu()

# 同花顺直播
df = ak.stock_info_global_ths()
```

**参考文档**: https://akshare.akfamily.xyz/data/stock/stock.html

---

## 5. 推荐方案

| 需求 | 推荐方案 | 备选方案 |
|-----|---------|---------|
| **实时行情** | 腾讯 `qt.gtimg.cn` | 新浪 (双源备份) |
| **K线数据** | 东方财富(AKShare) | 腾讯 |
| **资金流向** | 腾讯 `ff_` 接口 | 东方财富 |
| **个股新闻** | 东方财富 `stock_news_em` | 雪球 |
| **盘口异动** | 东方财富 `stock_changes_em` | - |
| **公司公告** | 巨潮资讯(AKShare) | - |
| **财经快讯** | 财联社/新浪/同花顺 | - |
| **财务报表** | 网易财经(CSV) | 东方财富 |
| **龙虎榜** | 东方财富 `stock_lhb_detail_em` | - |
| **涨停分析** | 东方财富 `stock_zt_pool_*` | - |

---

## 6. 注意事项

1. **新浪接口变更**: 2022年后需添加 `Referer: https://finance.sina.com.cn/` 头
2. **雪球需登录**: 使用前需访问官网获取cookie/token
3. **网易数据**: 只提供不复权数据，适合获取市值等基础信息
4. **频率限制**: 各平台都有不同程度的访问频率限制，建议添加延时
5. **数据一致性**: 不同数据源的数据可能有细微差异，建议以交易所官方数据为准

---

## 7. 开源工具库

| 库名 | 语言 | 数据源 | GitHub |
|-----|------|-------|--------|
| **AKShare** | Python | 多源聚合 | https://github.com/akfamily/akshare |
| **Ashare** | Python | 新浪+腾讯 | https://github.com/mpquant/Ashare |
| **pysnowball** | Python | 雪球 | https://github.com/uname-yang/pysnowball |
| **stock-api** | JavaScript | 多源 | https://github.com/zhangxiangliang/stock-api |
| **Tushare** | Python | 多源 | https://tushare.pro |
| **Baostock** | Python | 证券宝 | http://baostock.com |

---

*文档更新时间: 2026-01-06*
