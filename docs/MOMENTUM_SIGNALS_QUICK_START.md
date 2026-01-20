# 动量信号监控 - 快速开始指南

## 🚀 5分钟快速启动

### 步骤 1: 启动监控进程
```bash
# 进入项目目录
cd /Users/park/a-share-data

# 启动持续监控 (每60秒更新)
python3 scripts/monitor_no_flask.py
```

**预期输出**:
```
============================================================
🚀 板块监控启动（无需Flask版本）
============================================================
监控配置:
  - 涨幅前20概念
  - 自选概念: 10个
  - 更新间隔: 60秒 (1.0分钟)
  - 输出文件: /Users/park/a-share-data/docs/monitor/latest.json
============================================================

第1轮监控

开始更新 - 2026-01-19 14:30:00
============================================================
[14:30:00] 开始获取板块数据...
[14:30:15] 成功获取 450 个板块
...
🔔 检测到 3 个动量信号:
   - 上涨激增: 2个
   - K线形态: 1个
   [surge] 先进封装: 6只新增上涨 (阈值: 5只)
   [surge] 存储芯片: 4只新增上涨 (阈值: 3只)
   [kline_pattern] 光刻机: 阳线无上影线 (上影1.2%)
```

### 步骤 2: 启动后端服务
打开新终端窗口:
```bash
cd /Users/park/a-share-data
uvicorn src.main:app --reload --port 8000
```

### 步骤 3: 启动前端服务
打开第三个终端窗口:
```bash
cd /Users/park/a-share-data/frontend
npm run dev
```

### 步骤 4: 访问动量信号页面
1. 浏览器访问: http://localhost:5173
2. 点击顶部 "🔔 动量信号" 按钮
3. 查看实时信号!

---

## 📋 信号类型说明

### 🔴 上涨激增信号
**含义**: 板块内上涨股票数量在60秒内快速增加

**触发条件**:
- **大板块** (≥50只股票): 新增 ≥5只上涨
- **小板块** (<50只股票): 新增 ≥3只上涨

**示例**:
```
板块: 先进封装 (78只)
上涨变化: 32 → 38 (+6只)
类型: 大板块
阈值: 5只
结论: ✅ 触发信号
```

### 🟢 K线形态信号
**含义**: 最新30分钟K线呈现强势形态

**触发条件**:
1. 阳线: 收盘价 > 开盘价
2. 无上影线: 上影线长度 < 实体的5%

**示例**:
```
板块: 光刻机
K线时间: 2026-01-19 14:30
开/收/高/低: 1234.56 / 1255.00 / 1256.78 / 1230.00
实体大小: 1255.00 - 1234.56 = 20.44
上影线: 1256.78 - 1255.00 = 1.78
上影比例: 1.78 / 20.44 = 8.7%
结论: ❌ 未触发 (上影比例 > 5%)
```

---

## 🔧 常见问题

### Q1: 为什么没有看到任何信号?
**A**: 可能原因:
1. 市场较平静，未触发任何条件
2. 监控进程刚启动，需要等待60秒后第二次更新才能检测上涨激增
3. 数据库中没有30分钟K线数据 (需先运行K线更新任务)

**解决方法**:
```bash
# 检查信号文件是否存在
cat docs/monitor/momentum_signals.json

# 如果文件为空或total_signals为0，说明确实没有触发信号
# 等待下一轮更新 (60秒)
```

### Q2: 如何调整检测阈值?
**A**: 编辑 `scripts/monitor_no_flask.py`:

```python
# 第339行附近
is_large_board = total_stocks >= 50  # 大板块定义
threshold = 5 if is_large_board else 3  # 阈值

# 可修改为:
threshold = 3 if is_large_board else 2  # 降低阈值，更容易触发
```

### Q3: 如何调整上影线容忍度?
**A**: 编辑 `scripts/monitor_no_flask.py`:

```python
# 第283行附近
if upper_shadow_ratio < 0.05:  # 5%容忍度

# 可修改为:
if upper_shadow_ratio < 0.10:  # 10%容忍度，更容易触发
```

### Q4: 前端自动刷新太频繁/太慢?
**A**: 编辑 `frontend/src/components/MomentumSignalsView.tsx`:

```typescript
// 第45行附近
refetchInterval: autoRefresh ? 60000 : false, // 60秒

// 可修改为:
refetchInterval: autoRefresh ? 30000 : false, // 30秒 (更快)
// 或
refetchInterval: autoRefresh ? 120000 : false, // 2分钟 (更慢)
```

---

## 📊 API端点测试

### 获取动量信号
```bash
curl http://localhost:8000/api/concept-monitor/momentum-signals | jq
```

**响应示例**:
```json
{
  "success": true,
  "timestamp": "2026-01-19 14:30:00",
  "total_signals": 2,
  "surge_signals_count": 1,
  "kline_signals_count": 1,
  "signals": [
    {
      "concept_name": "先进封装",
      "concept_code": "886042",
      "signal_type": "surge",
      "total_stocks": 78,
      "prev_up_count": 32,
      "current_up_count": 38,
      "delta_up_count": 6,
      "threshold": 5,
      "board_type": "large",
      "timestamp": "2026-01-19 14:30:00",
      "details": "6只新增上涨 (阈值: 5只)"
    },
    {
      "concept_name": "光刻机",
      "concept_code": "886045",
      "signal_type": "kline_pattern",
      "total_stocks": 42,
      "current_change_pct": 2.87,
      "kline_info": {
        "trade_time": "2026-01-19 14:30",
        "open": 980.50,
        "high": 1005.20,
        "low": 978.00,
        "close": 1004.80,
        "upper_shadow_ratio": 1.6
      },
      "timestamp": "2026-01-19 14:30:00",
      "details": "阳线无上影线 (上影1.6%)"
    }
  ]
}
```

---

## 🎯 信号使用建议

### 上涨激增信号的使用场景
✅ **适合**:
- 捕捉板块启动初期
- 发现资金快速涌入的板块
- 短线交易机会

❌ **不适合**:
- 板块已经大幅上涨后
- 尾盘急拉时 (可能是诱多)

### K线形态信号的使用场景
✅ **适合**:
- 确认板块强势延续
- 趋势跟随策略
- 波段持仓信号

❌ **不适合**:
- 高位放量时 (可能是顶部)
- 单根K线判断 (需结合趋势)

### 组合使用建议
**最强信号**: 同一板块同时触发两种信号
- 上涨激增 + K线形态 → 资金涌入 + 形态强势
- 关注度: 🔥🔥🔥

**次强信号**: 仅触发上涨激增
- 快速启动，需观察后续K线
- 关注度: 🔥🔥

**参考信号**: 仅触发K线形态
- 强势延续，需确认资金流入
- 关注度: 🔥

---

## 📈 下一步优化方向

完成基础实施后，可考虑:

1. **信号强度评分**: 综合多个因素给信号打分
2. **历史回测**: 统计信号触发后的涨幅分布
3. **实时推送**: 微信/钉钉/Telegram机器人通知
4. **自定义策略**: 允许用户配置检测条件

---

## 📞 需要帮助?

- 检查日志: `tail -f logs/monitor.log` (如配置)
- 查看完整文档: `docs/MOMENTUM_SIGNALS_IMPLEMENTATION.md`
- API文档: http://localhost:8000/docs

---

**祝交易顺利! 📈**
