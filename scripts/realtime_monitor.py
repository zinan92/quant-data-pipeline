#!/usr/bin/env python3
"""
实时板块监控系统
- 监控自选热门概念
- 监控当日涨幅前20概念
- 2-3分钟更新一次
"""

import akshare as ak
import pandas as pd
import time
import json
from datetime import datetime
from pathlib import Path

class SectorMonitor:
    def __init__(self, watch_list=None, top_n=20, update_interval=150):
        """
        初始化监控器

        Args:
            watch_list: 自选热门概念列表
            top_n: 监控涨幅前N的概念
            update_interval: 更新间隔（秒）
        """
        self.watch_list = watch_list or []
        self.top_n = top_n
        self.update_interval = update_interval
        self.output_dir = Path('/Users/park/a-share-data/docs/monitor')
        self.output_dir.mkdir(exist_ok=True)

        # 历史数据记录
        self.history = []

    def get_all_concepts_data(self):
        """获取所有概念板块数据"""
        print(f"\n[{datetime.now().strftime('%H:%M:%S')}] 开始获取所有板块数据...")

        df_names = ak.stock_board_concept_name_ths()
        results = []

        for idx, row in df_names.iterrows():
            concept_name = row['name']
            concept_code = row['code']

            try:
                df_info = ak.stock_board_concept_info_ths(symbol=concept_name)

                # 解析数据
                data = {}
                for i, info_row in df_info.iterrows():
                    data[info_row['项目']] = info_row['值']

                # 解析涨跌家数
                up_down = data.get('涨跌家数', '0/0')
                up_count, down_count = map(int, up_down.split('/'))

                # 计算涨停数（从涨跌幅推算，需要进一步优化）
                total_stocks = up_count + down_count
                change_pct_str = data.get('板块涨幅', '0%').replace('%', '')
                money_inflow = float(data.get('资金净流入(亿)', 0))
                turnover = float(data.get('成交额(亿)', 0))
                volume = float(data.get('成交量(万手)', 0))

                # 主力净量
                if turnover > 0:
                    main_volume = (money_inflow / turnover) * volume
                else:
                    main_volume = 0

                results.append({
                    'code': concept_code,
                    'name': concept_name,
                    'change_pct': float(change_pct_str),
                    'money_inflow': money_inflow,
                    'main_volume': round(main_volume, 2),
                    'up_count': up_count,
                    'down_count': down_count,
                    'total_stocks': total_stocks,
                    'limit_up': 0,  # 占位，需要成分股数据
                    'turnover': turnover,
                    'volume': volume,
                    'open': float(data.get('今开', 0)),
                    'high': float(data.get('最高', 0)),
                    'low': float(data.get('最低', 0)),
                    'close': float(data.get('昨收', 0)),
                    'timestamp': datetime.now().strftime('%Y-%m-%d %H:%M:%S')
                })

                # 限流
                time.sleep(0.3)

            except Exception as e:
                print(f"  ✗ {concept_name}: {str(e)[:50]}")
                continue

        print(f"[{datetime.now().strftime('%H:%M:%S')}] 成功获取 {len(results)} 个板块")
        return pd.DataFrame(results)

    def calculate_limit_up_count(self, concept_name):
        """
        计算板块涨停数
        通过获取成分股数据统计
        """
        try:
            # 尝试东方财富接口
            df_stocks = ak.stock_board_concept_cons_em(symbol=concept_name)
            if df_stocks is not None and len(df_stocks) > 0:
                # 判断涨停：主板9.9%，科创板/创业板19.9%
                limit_up_count = 0
                for _, stock in df_stocks.iterrows():
                    change_pct = stock.get('涨跌幅', 0)
                    code = stock.get('代码', '')

                    # 科创板/创业板
                    if code.startswith('688') or code.startswith('300'):
                        if change_pct >= 19.9:
                            limit_up_count += 1
                    # 主板
                    else:
                        if change_pct >= 9.9:
                            limit_up_count += 1

                return limit_up_count, len(df_stocks)
        except:
            pass

        return 0, 0

    def get_top_concepts(self, df_all, n=20):
        """获取涨幅前N的概念"""
        return df_all.nlargest(n, 'change_pct')

    def get_watch_concepts(self, df_all):
        """获取自选概念数据"""
        return df_all[df_all['name'].isin(self.watch_list)]

    def enhance_with_limit_up(self, df):
        """
        为重点板块补充涨停数据
        """
        print(f"\n[{datetime.now().strftime('%H:%M:%S')}] 计算涨停数...")

        enhanced = []
        for idx, row in df.iterrows():
            concept_name = row['name']
            limit_up, total = self.calculate_limit_up_count(concept_name)

            row_dict = row.to_dict()
            row_dict['limit_up'] = limit_up
            row_dict['limit_up_rate'] = round(limit_up / total * 100, 2) if total > 0 else 0

            enhanced.append(row_dict)
            print(f"  {concept_name}: 涨停 {limit_up}/{total} ({row_dict['limit_up_rate']}%)")

            time.sleep(0.3)

        return pd.DataFrame(enhanced)

    def save_snapshot(self, df_top, df_watch):
        """保存当前快照"""
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        date_str = datetime.now().strftime('%Y-%m-%d')

        # 1. 保存JSON格式（供前端使用）
        snapshot = {
            'timestamp': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
            'top_concepts': df_top.to_dict('records'),
            'watch_concepts': df_watch.to_dict('records')
        }

        json_file = self.output_dir / 'latest.json'
        with open(json_file, 'w', encoding='utf-8') as f:
            json.dump(snapshot, f, ensure_ascii=False, indent=2)

        # 2. 保存历史JSON（按日期）
        history_file = self.output_dir / f'history_{date_str}.json'
        if history_file.exists():
            with open(history_file, 'r', encoding='utf-8') as f:
                history = json.load(f)
        else:
            history = []

        history.append(snapshot)

        with open(history_file, 'w', encoding='utf-8') as f:
            json.dump(history, f, ensure_ascii=False, indent=2)

        # 3. 保存CSV格式（供分析使用）
        csv_file = self.output_dir / f'snapshot_{timestamp}.csv'
        df_combined = pd.concat([df_top, df_watch]).drop_duplicates(subset=['code'])
        df_combined.to_csv(csv_file, index=False, encoding='utf-8-sig')

        print(f"\n[{datetime.now().strftime('%H:%M:%S')}] 数据已保存:")
        print(f"  - 最新快照: {json_file}")
        print(f"  - 历史数据: {history_file}")
        print(f"  - CSV备份: {csv_file}")

        return json_file

    def generate_summary_report(self, df_top, df_watch):
        """生成汇总报告"""
        report = []
        report.append("=" * 80)
        report.append(f"板块监控报告 - {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        report.append("=" * 80)

        # 涨幅前20
        report.append(f"\n📈 涨幅前{len(df_top)}概念板块:")
        report.append("-" * 80)
        for idx, row in df_top.iterrows():
            report.append(
                f"{idx+1:2d}. {row['name']:15s} "
                f"涨幅:{row['change_pct']:6.2f}% "
                f"资金:{row['money_inflow']:8.2f}亿 "
                f"涨停:{row['limit_up']:2d} "
                f"涨跌:{row['up_count']:3d}/{row['down_count']:2d}"
            )

        # 自选概念
        if len(df_watch) > 0:
            report.append(f"\n⭐ 自选热门概念 ({len(df_watch)}个):")
            report.append("-" * 80)
            for idx, row in df_watch.iterrows():
                report.append(
                    f"   {row['name']:15s} "
                    f"涨幅:{row['change_pct']:6.2f}% "
                    f"资金:{row['money_inflow']:8.2f}亿 "
                    f"涨停:{row['limit_up']:2d} "
                    f"涨跌:{row['up_count']:3d}/{row['down_count']:2d}"
                )

        report.append("\n" + "=" * 80)

        report_text = "\n".join(report)

        # 保存报告
        report_file = self.output_dir / 'latest_report.txt'
        with open(report_file, 'w', encoding='utf-8') as f:
            f.write(report_text)

        print(report_text)

        return report_text

    def run_once(self):
        """执行一次监控"""
        print("\n" + "=" * 80)
        print(f"开始监控轮询 - {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        print("=" * 80)

        # 1. 获取所有板块数据
        df_all = self.get_all_concepts_data()

        # 2. 提取涨幅前20
        df_top = self.get_top_concepts(df_all, self.top_n)

        # 3. 提取自选概念
        df_watch = self.get_watch_concepts(df_all)

        # 4. 合并需要深度分析的板块
        df_focus = pd.concat([df_top, df_watch]).drop_duplicates(subset=['code'])

        # 5. 补充涨停数据
        df_focus_enhanced = self.enhance_with_limit_up(df_focus)

        # 6. 分离回top和watch
        df_top_final = df_focus_enhanced[df_focus_enhanced['code'].isin(df_top['code'])]
        df_watch_final = df_focus_enhanced[df_focus_enhanced['code'].isin(df_watch['code'])]

        # 按涨幅排序
        df_top_final = df_top_final.sort_values('change_pct', ascending=False)
        df_watch_final = df_watch_final.sort_values('change_pct', ascending=False)

        # 7. 保存数据
        self.save_snapshot(df_top_final, df_watch_final)

        # 8. 生成报告
        self.generate_summary_report(df_top_final, df_watch_final)

        return df_top_final, df_watch_final

    def run_continuous(self):
        """持续监控"""
        print("=" * 80)
        print("🚀 启动实时板块监控系统")
        print("=" * 80)
        print(f"监控配置:")
        print(f"  - 涨幅前{self.top_n}概念")
        print(f"  - 自选概念: {len(self.watch_list)}个")
        print(f"  - 更新间隔: {self.update_interval}秒 ({self.update_interval/60:.1f}分钟)")
        print(f"  - 输出目录: {self.output_dir}")
        print("=" * 80)

        iteration = 0
        while True:
            try:
                iteration += 1
                print(f"\n第{iteration}轮监控")

                self.run_once()

                print(f"\n⏰ 等待 {self.update_interval} 秒后进行下一轮监控...")
                time.sleep(self.update_interval)

            except KeyboardInterrupt:
                print("\n\n⚠️  用户中断，停止监控")
                break
            except Exception as e:
                print(f"\n❌ 监控出错: {e}")
                print(f"等待30秒后重试...")
                time.sleep(30)


def main():
    """主函数"""

    # 定义自选热门概念
    watch_list = [
        "先进封装",
        "存储芯片",
        "光刻机",
        "第三代半导体",
        "国家大基金持股",
        "汽车芯片",
        "MCU芯片",
        "中芯国际概念",
        "人形机器人",
        "特高压"
    ]

    # 创建监控器
    monitor = SectorMonitor(
        watch_list=watch_list,
        top_n=20,
        update_interval=150  # 2.5分钟
    )

    # 选择运行模式
    import sys
    if len(sys.argv) > 1 and sys.argv[1] == '--once':
        # 单次运行
        print("运行模式: 单次监控")
        monitor.run_once()
    else:
        # 持续运行
        print("运行模式: 持续监控 (Ctrl+C 停止)")
        monitor.run_continuous()


if __name__ == '__main__':
    main()
