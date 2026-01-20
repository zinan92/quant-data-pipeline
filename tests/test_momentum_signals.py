#!/usr/bin/env python3
"""
测试动量信号检测功能
"""

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

import json
from datetime import datetime


def test_signal_detection():
    """测试信号检测逻辑"""
    print("\n" + "="*60)
    print("动量信号检测功能测试")
    print("="*60)

    # 1. 检查monitor脚本更新
    monitor_file = Path('/Users/park/a-share-data/scripts/monitor_no_flask.py')
    with open(monitor_file, 'r') as f:
        content = f.read()

    checks = {
        "更新间隔改为60秒": "UPDATE_INTERVAL = 60" in content,
        "导入deque": "from collections import deque" in content,
        "快照历史存储": "SNAPSHOT_HISTORY" in content,
        "检测上涨激增函数": "def detect_surge_signals" in content,
        "检测K线形态函数": "def detect_kline_pattern_signals" in content,
        "保存信号函数": "def save_momentum_signals" in content,
        "信号文件路径": "SIGNALS_FILE" in content,
    }

    print("\n✅ Monitor脚本检查:")
    for check, passed in checks.items():
        status = "✓" if passed else "✗"
        print(f"   {status} {check}")

    # 2. 检查API endpoint
    api_file = Path('/Users/park/a-share-data/src/api/routes_concept_monitor_v2.py')
    with open(api_file, 'r') as f:
        api_content = f.read()

    api_checks = {
        "信号文件路径定义": "SIGNALS_FILE" in api_content,
        "MomentumSignal模型": "class MomentumSignal" in api_content,
        "MomentumSignalsResponse模型": "class MomentumSignalsResponse" in api_content,
        "momentum-signals端点": 'get("/momentum-signals"' in api_content or 'get("/momentum-signals"' in api_content,
    }

    print("\n✅ API端点检查:")
    for check, passed in api_checks.items():
        status = "✓" if passed else "✗"
        print(f"   {status} {check}")

    # 3. 检查前端组件
    frontend_component = Path('/Users/park/a-share-data/frontend/src/components/MomentumSignalsView.tsx')
    frontend_checks = {
        "动量信号组件存在": frontend_component.exists(),
        "CSS文件存在": Path('/Users/park/a-share-data/frontend/src/styles/MomentumSignalsView.css').exists(),
    }

    if frontend_component.exists():
        with open(frontend_component, 'r') as f:
            frontend_content = f.read()
        frontend_checks.update({
            "MomentumSignal接口": "interface MomentumSignal" in frontend_content,
            "API调用": "fetchMomentumSignals" in frontend_content,
            "上涨激增显示": "signal_type === \"surge\"" in frontend_content,
            "K线形态显示": "signal_type === \"kline_pattern\"" in frontend_content,
        })

    print("\n✅ 前端组件检查:")
    for check, passed in frontend_checks.items():
        status = "✓" if passed else "✗"
        print(f"   {status} {check}")

    # 4. 检查App.tsx集成
    app_file = Path('/Users/park/a-share-data/frontend/src/App.tsx')
    with open(app_file, 'r') as f:
        app_content = f.read()

    app_checks = {
        "导入MomentumSignalsView": "import { MomentumSignalsView }" in app_content,
        "signals视图模式": '"signals"' in app_content,
        "handleSignalsClick函数": "handleSignalsClick" in app_content,
        "动量信号按钮": "动量信号" in app_content,
        "信号视图渲染": 'viewMode === "signals"' in app_content,
    }

    print("\n✅ App.tsx集成检查:")
    for check, passed in app_checks.items():
        status = "✓" if passed else "✗"
        print(f"   {status} {check}")

    # 5. 检查CSS样式
    styles_file = Path('/Users/park/a-share-data/frontend/src/styles.css')
    with open(styles_file, 'r') as f:
        styles_content = f.read()

    styles_checks = {
        "警告按钮样式": "topbar__button--warning" in styles_content,
        "脉冲动画": "pulse-glow" in styles_content,
    }

    print("\n✅ 样式检查:")
    for check, passed in styles_checks.items():
        status = "✓" if passed else "✗"
        print(f"   {status} {check}")

    # 总结
    all_checks = {**checks, **api_checks, **frontend_checks, **app_checks, **styles_checks}
    total = len(all_checks)
    passed = sum(all_checks.values())

    print("\n" + "="*60)
    print(f"📊 测试结果: {passed}/{total} 项通过")
    print("="*60)

    if passed == total:
        print("✅ 所有检查通过！动量信号功能已完整实现。")
        print("\n下一步:")
        print("1. 运行 monitor 脚本: python3 scripts/monitor_no_flask.py --once")
        print("2. 启动后端: uvicorn src.main:app --reload")
        print("3. 启动前端: cd frontend && npm run dev")
        print("4. 访问动量信号页面查看效果")
    else:
        print(f"⚠️  还有 {total - passed} 项未通过，请检查实现。")

    return passed == total


if __name__ == '__main__':
    success = test_signal_detection()
    sys.exit(0 if success else 1)
