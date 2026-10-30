#!/usr/bin/env python3
"""
为 probe-rs 生成 target 描述 YAML。
用法: python3 scripts/gen_target.py <pack文件> <输出目录>
"""

import subprocess, sys
from pathlib import Path

def gen_target(pack_path: str, output_dir: str):
    out = Path(output_dir)
    out.mkdir(parents=True, exist_ok=True)

    result = subprocess.run(
        ['target-gen', 'pack', pack_path, output_dir],
        capture_output=True, text=True
    )

    if result.returncode != 0:
        print(f"target-gen 失败:\n{result.stderr}")
        sys.exit(1)

    print(f"Target YAML 已生成到 {output_dir}")
    for f in sorted(out.glob('*.yaml')):
        print(f"  - {f.name}")

if __name__ == '__main__':
    if len(sys.argv) != 3:
        print("用法: python3 scripts/gen_target.py <pack文件> <输出目录>")
        sys.exit(1)
    gen_target(sys.argv[1], sys.argv[2])
