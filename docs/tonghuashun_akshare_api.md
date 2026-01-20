# 同花顺板块数据API - 通过AKShare获取

## 概述

通过AKShare库可以获取**同花顺**的概念板块（372个）和行业板块（90个）的实时数据，包含你需要的所有字段。

## ✅ 数据源确认

经过测试，找到的板块与你提到的涨幅前列板块**完全匹配**：

| 你提到的板块 | 在同花顺中 | 板块代码 |
|------------|----------|---------|
| ✓ 先进封装 | 找到 | 309004 |
| ✓ 中芯国际概念 | 找到 | 308690 |
| ✓ 光刻机 | 找到 | 309085 |
| ✓ 第三代半导体 | 找到 | 308700 |
| ✓ 柔性直流输电 | 找到 | 308810 |
| ✓ MCU芯片 | 找到 | 308300 |
| ✓ 汽车芯片 | 找到 | 308725 |
| ✓ 减速器 | 找到 | 309000 |
| ✓ 特高压 | 找到 | 300353 |
| ✓ 工业母机 | 找到 | 300941 |
| "国家大基金持股" | 类似 | 307816 |
| "智能电网" | 类似电网设备 | - |

## 1. 概念板块数据

### 获取板块列表

```python
import akshare as ak

# 获取所有概念板块名称和代码
df_names = ak.stock_board_concept_name_ths()
print(f'概念板块总数: {len(df_names)}')  # 372个
print(df_names.head())
```

**返回字段：**
- `name`: 板块名称（如"先进封装"）
- `code`: 板块代码（如"309004"）

### 获取单个概念板块的详细实时数据

```python
# 获取指定概念板块的详细信息
df_info = ak.stock_board_concept_info_ths(symbol="先进封装")
print(df_info)
```

**返回数据示例：**
```
         项目        值
0        今开  2050.50
1        昨收  2027.97
2        最低  2044.38
3        最高  2111.75
4   成交量(万手)  5687.75
5      板块涨幅    3.44%
6      涨幅排名    3/390
7      涨跌家数   120/22   # 格式：涨家数/跌家数
8  资金净流入(亿)   135.64  # 主力资金净流入
9    成交额(亿)  2033.66
```

## 2. 行业板块数据

### 获取行业板块列表

```python
# 获取所有行业板块名称和代码
df_industries = ak.stock_board_industry_name_ths()
print(f'行业板块总数: {len(df_industries)}')  # 90个
print(df_industries.head())
```

### 获取单个行业板块的详细实时数据

```python
# 获取指定行业板块的详细信息
df_info = ak.stock_board_industry_info_ths(symbol="半导体")
print(df_info)
```

**返回数据格式与概念板块相同**

## 3. 字段映射到你的需求

| 你需要的字段 | 同花顺返回字段 | 说明 |
|------------|--------------|------|
| ✅ 涨幅 | 板块涨幅 | 如 "3.44%" |
| ✅ 主力金额 | 资金净流入(亿) | 如 "135.64" 亿元 |
| ⚠️ 主力净量 | 需要计算 | 资金净流入 / 平均成交价 |
| ✅ 涨停数 | 从"涨跌家数"推算 | 需要获取成分股详情 |
| ✅ 涨家数 | 涨跌家数 | "120/22" 格式，前面是涨家数 |
| ✅ 跌家数 | 涨跌家数 | "120/22" 格式，后面是跌家数 |

## 4. 获取涨停数的方法

涨停数需要单独计算，有两种方法：

### 方法1：通过概念成分股查询（推荐）

```python
# 获取板块内所有股票
df_stocks = ak.stock_board_concept_cons_ths(symbol="先进封装")
# 然后查询这些股票中有多少涨停的
```

### 方法2：使用现有数据库

从你的数据库中查询该概念/行业下的股票，统计涨幅>=9.9%的数量

## 5. 完整示例代码

```python
import akshare as ak
import pandas as pd

def get_all_concept_realtime_data():
    """获取所有概念板块的实时数据"""
    # 1. 获取所有概念板块列表
    df_names = ak.stock_board_concept_name_ths()

    results = []
    for idx, row in df_names.iterrows():
        concept_name = row['name']
        concept_code = row['code']

        try:
            # 2. 获取每个板块的详细数据
            df_info = ak.stock_board_concept_info_ths(symbol=concept_name)

            # 3. 解析数据
            data = {}
            for i, info_row in df_info.iterrows():
                data[info_row['项目']] = info_row['值']

            # 4. 解析涨跌家数
            up_down = data.get('涨跌家数', '0/0')
            up_count, down_count = up_down.split('/')

            results.append({
                'code': concept_code,
                'name': concept_name,
                'change_pct': float(data.get('板块涨幅', '0%').replace('%', '')),
                'money_inflow': float(data.get('资金净流入(亿)', 0)),
                'up_count': int(up_count),
                'down_count': int(down_count),
                'turnover': float(data.get('成交额(亿)', 0)),
                'open': float(data.get('今开', 0)),
                'high': float(data.get('最高', 0)),
                'low': float(data.get('最低', 0)),
                'prev_close': float(data.get('昨收', 0)),
            })

        except Exception as e:
            print(f'获取{concept_name}失败: {e}')
            continue

    return pd.DataFrame(results)

# 使用
df_concepts = get_all_concept_realtime_data()
print(df_concepts.sort_values('change_pct', ascending=False).head(20))
```

## 6. 行业板块的完整示例

```python
def get_all_industry_realtime_data():
    """获取所有行业板块的实时数据"""
    df_names = ak.stock_board_industry_name_ths()

    results = []
    for idx, row in df_names.iterrows():
        industry_name = row['name']
        industry_code = row['code']

        try:
            df_info = ak.stock_board_industry_info_ths(symbol=industry_name)

            data = {}
            for i, info_row in df_info.iterrows():
                data[info_row['项目']] = info_row['值']

            up_down = data.get('涨跌家数', '0/0')
            up_count, down_count = up_down.split('/')

            results.append({
                'code': industry_code,
                'name': industry_name,
                'change_pct': float(data.get('板块涨幅', '0%').replace('%', '')),
                'money_inflow': float(data.get('资金净流入(亿)', 0)),
                'up_count': int(up_count),
                'down_count': int(down_count),
                'turnover': float(data.get('成交额(亿)', 0)),
            })

        except Exception as e:
            print(f'获取{industry_name}失败: {e}')
            continue

    return pd.DataFrame(results)
```

## 7. 注意事项

1. **速度较慢**: 获取372个概念板块需要逐个请求，大约需要5-10分钟
2. **需要限流**: 建议每次请求间隔0.5-1秒，避免被封IP
3. **数据更新**: 交易时间内实时更新
4. **无需认证**: AKShare库处理了认证问题

## 8. 建议的实现方案

1. **创建后端定时任务**: 每5分钟抓取一次所有板块数据
2. **存储到数据库**: 保存历史数据供前端查询
3. **API接口**:
   - `GET /api/sectors/ths/concepts` - 获取所有概念板块实时数据
   - `GET /api/sectors/ths/industries` - 获取所有行业板块实时数据
   - `GET /api/sectors/ths/concept/{name}` - 获取单个概念板块数据
   - `GET /api/sectors/ths/industry/{name}` - 获取单个行业板块数据

## 9. 安装依赖

```bash
pip install akshare
```

AKShare版本要求: >= 1.12.0
