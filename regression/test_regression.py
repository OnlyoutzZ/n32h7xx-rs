#!/usr/bin/env python3
"""
回归比对：将当前生成结果的地址/中断与基准快照对比。
用法: python3 regression/test_regression.py <设备名>
"""

import json, sys
from pathlib import Path

# Windows 控制台默认 GBK(cp936)，输出 ✓/✗/⚠ 会 UnicodeEncodeError 崩溃。
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

def load_json(path: str) -> dict:
    return json.loads(Path(path).read_text())

def compare(device: str):
    expected_dir = Path("regression/expected")
    current_dir = Path("regression/current")
    failures = []

    exp_addr_file = expected_dir / f"{device}-addresses.json"
    if not exp_addr_file.exists():
        print(f"⚠ 基准文件不存在: {exp_addr_file}")
        print("  这可能是第一次运行。请先用 generate_baseline.py 生成基准快照。")
        sys.exit(0)

    exp_addr = load_json(exp_addr_file)
    cur_addr = load_json(current_dir / f"{device}-addresses.json")

    for key, addr in exp_addr.get('peripherals', {}).items():
        cur = cur_addr.get('peripherals', {}).get(key)
        if cur != addr:
            failures.append(f"地址不匹配 {key}: 期望 {addr}, 实际 {cur}")

    exp_irq_file = expected_dir / f"{device}-interrupts.json"
    if exp_irq_file.exists():
        exp_irq = load_json(exp_irq_file)
        cur_irq = load_json(current_dir / f"{device}-interrupts.json")
        for irq_num, name in exp_irq.items():
            cur = cur_irq.get(irq_num)
            if cur != name:
                failures.append(f"中断不匹配 #{irq_num}: 期望 {name}, 实际 {cur}")

    if failures:
        print(f"✗ 回归测试失败（{len(failures)} 个问题）:")
        for f in failures:
            print(f"  - {f}")
        sys.exit(1)
    else:
        print(f"✓ {device} 回归测试通过")

if __name__ == '__main__':
    compare(sys.argv[1])
