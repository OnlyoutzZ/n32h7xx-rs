#!/usr/bin/env python3
"""
对比原始 SVD 和补丁后的 SVD，生成寄存器地址和中断编号的差异报告。
用法: python3 scripts/diff_report.py <原始svd> <补丁后svd> <设备名> <输出目录>
"""

import xml.etree.ElementTree as ET
import json, sys
from pathlib import Path
from datetime import datetime

def extract_peripherals(svd_path: str) -> dict:
    tree = ET.parse(svd_path)
    result = {}
    for p in tree.getroot().findall('.//peripheral'):
        name = p.findtext('name', '?')
        base = p.findtext('baseAddress', '0x0')
        result[name] = {
            'baseAddress': int(base, 0),
            'registers': {
                r.findtext('name', '?'): int(r.findtext('addressOffset', '0'), 0)
                for r in p.findall('.//register')
            }
        }
    return result

def extract_interrupts(svd_path: str) -> dict:
    tree = ET.parse(svd_path)
    result = {}
    for p in tree.getroot().findall('.//peripheral'):
        for irq in p.findall('.//interrupt'):
            name = irq.findtext('name', '?')
            num = int(irq.findtext('value', '-1'))
            result[num] = name
    return result

def generate_report(vendor_svd, patched_svd, device, output_dir):
    vendor_periph = extract_peripherals(vendor_svd)
    patched_periph = extract_peripherals(patched_svd)
    vendor_irqs = extract_interrupts(vendor_svd)
    patched_irqs = extract_interrupts(patched_svd)

    report = {
        'device': device,
        'timestamp': datetime.now().isoformat(),
        'peripheral_diff': {},
        'interrupt_diff': {}
    }

    all_periphs = set(vendor_periph) | set(patched_periph)
    for p in sorted(all_periphs):
        if p not in vendor_periph:
            report['peripheral_diff'][p] = {'status': 'ADDED'}
        elif p not in patched_periph:
            report['peripheral_diff'][p] = {'status': 'REMOVED'}
        elif vendor_periph[p]['baseAddress'] != patched_periph[p]['baseAddress']:
            report['peripheral_diff'][p] = {
                'status': 'ADDRESS_CHANGED',
                'vendor': hex(vendor_periph[p]['baseAddress']),
                'patched': hex(patched_periph[p]['baseAddress'])
            }

    all_irqs = set(vendor_irqs) | set(patched_irqs)
    for irq_num in sorted(all_irqs):
        v_name = vendor_irqs.get(irq_num)
        p_name = patched_irqs.get(irq_num)
        if v_name != p_name:
            report['interrupt_diff'][str(irq_num)] = {
                'vendor': v_name, 'patched': p_name
            }

    out = Path(output_dir)
    out.mkdir(parents=True, exist_ok=True)
    report_path = out / f"{device}-diff-report.json"
    report_path.write_text(json.dumps(report, indent=2, ensure_ascii=False))

    print(f"差异报告: {report_path}")
    print(f"  外设差异: {len(report['peripheral_diff'])} 项")
    print(f"  中断差异: {len(report['interrupt_diff'])} 项")
    return report

if __name__ == '__main__':
    generate_report(sys.argv[1], sys.argv[2], sys.argv[3], sys.argv[4])
