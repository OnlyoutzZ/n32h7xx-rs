#!/usr/bin/env python3
"""
SVD 基础校验：检查必需字段、地址冲突、中断编号。
用法: python3 scripts/validate_svd.py <svd文件>
"""

import xml.etree.ElementTree as ET
import sys

# Windows 控制台默认 GBK(cp936)，输出 ⚠/✓ 会 UnicodeEncodeError 崩溃。
# 统一改用 UTF-8 输出；终端显示乱码不致命，崩溃致命。
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

def validate(svd_path: str) -> list[str]:
    issues = []
    try:
        tree = ET.parse(svd_path)
    except ET.ParseError as e:
        return [f"XML 解析失败: {e}"]

    root = tree.getroot()

    for field in ['name', 'version', 'cpu', 'addressUnitBits', 'width']:
        if root.find(field) is None:
            issues.append(f"缺少顶层字段: <{field}>")

    peripherals = root.findall('.//peripheral')
    if not peripherals:
        issues.append("未找到任何 <peripheral> 定义")
        return issues

    addresses = {}
    for p in peripherals:
        name = p.findtext('name', '?')
        base = p.findtext('baseAddress')
        if base is None:
            issues.append(f"外设 '{name}': 缺少 baseAddress")
            continue
        base_int = int(base, 0)
        if base_int in addresses:
            issues.append(
                f"地址冲突: 0x{base_int:08X} 同时被 "
                f"'{addresses[base_int]}' 和 '{name}' 使用"
            )
        addresses[base_int] = name

    for p in peripherals:
        name = p.findtext('name', '?')
        for irq in p.findall('.//interrupt'):
            num_text = irq.findtext('value', '-1')
            try:
                num = int(num_text, 0)
            except ValueError:
                issues.append(f"'{name}': 中断 value='{num_text}' 不是有效数字")
                continue
            if num < 0 or num > 512:
                issues.append(f"'{name}': 中断编号 {num} 异常（应在 0-512 范围内）")

    return issues

if __name__ == '__main__':
    if len(sys.argv) < 2:
        print("用法: python3 scripts/validate_svd.py <svd文件>")
        sys.exit(1)

    path = sys.argv[1]
    issues = validate(path)
    if issues:
        print(f"发现 {len(issues)} 个问题:")
        for i in issues:
            print(f"  ⚠  {i}")
        sys.exit(1)
    else:
        print(f"✓ {path} 校验通过")
