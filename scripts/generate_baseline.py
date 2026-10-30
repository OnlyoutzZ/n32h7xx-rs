#!/usr/bin/env python3
"""
从 SVD 中提取关键地址和中断，存入快照。
首次验证通过后运行一次即可（写入 regression/expected/）。
回归测试前再对"当前"补丁产物运行一次（带第 3 个参数指向 regression/current/）。

用法: python3 scripts/generate_baseline.py <svd> <设备名> [输出目录]

注：方案 §4.7.2 的原始版本只写 regression/expected/。回归测试
（regression/test_regression.py）需要对比 regression/current/，但方案没有
给出生成 current 的入口 —— 这里以可选第 3 参数补全，默认行为与方案一致。
"""

import xml.etree.ElementTree as ET
import json, sys
from pathlib import Path

def main(svd_path, device, out_dir=None):
    tree = ET.parse(svd_path)
    root = tree.getroot()

    peripherals = {}
    for p in root.findall('.//peripheral'):
        name = p.findtext('name', '?')
        base = p.findtext('baseAddress', '0x0')
        peripherals[name] = hex(int(base, 0))

    interrupts = {}
    for p in root.findall('.//peripheral'):
        for irq in p.findall('.//interrupt'):
            name = irq.findtext('name', '?')
            num = irq.findtext('value', '-1')
            interrupts[num] = name

    out_dir = Path(out_dir) if out_dir else Path("regression/expected")
    out_dir.mkdir(parents=True, exist_ok=True)

    (out_dir / f"{device}-addresses.json").write_text(
        json.dumps({"peripherals": peripherals}, indent=2, ensure_ascii=False)
    )
    (out_dir / f"{device}-interrupts.json").write_text(
        json.dumps(interrupts, indent=2, ensure_ascii=False)
    )

    print(f"基准快照已生成:")
    print(f"  {out_dir / f'{device}-addresses.json'} ({len(peripherals)} 个外设)")
    print(f"  {out_dir / f'{device}-interrupts.json'} ({len(interrupts)} 个中断)")

if __name__ == '__main__':
    main(sys.argv[1], sys.argv[2], sys.argv[3] if len(sys.argv) > 3 else None)
