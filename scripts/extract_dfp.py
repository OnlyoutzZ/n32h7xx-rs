#!/usr/bin/env python3
"""
从 CMSIS-Pack (.pack，本质是 ZIP) 中提取 SVD、FLM 和 PDSC 文件。
用法: python3 scripts/extract_dfp.py <pack文件> <输出目录>
"""

import zipfile, shutil, sys
from pathlib import Path

def extract_dfp(pack_path: str, output_dir: str):
    pack = Path(pack_path)
    out = Path(output_dir)
    out.mkdir(parents=True, exist_ok=True)

    if not pack.exists():
        print(f"错误：找不到文件 {pack}")
        sys.exit(1)

    with zipfile.ZipFile(pack, 'r') as zf:
        svd_files = [n for n in zf.namelist() if n.lower().endswith('.svd')]
        flm_files = [n for n in zf.namelist() if n.lower().endswith('.flm')]
        pdsc_files = [n for n in zf.namelist() if n.lower().endswith('.pdsc')]

        if not svd_files:
            print("警告：pack 中未找到 SVD 文件！")
            print("该 pack 中的文件列表如下：")
            for n in zf.namelist():
                print(f"  {n}")
            return

        for f in svd_files:
            target = out / Path(f).name
            with zf.open(f) as src, open(target, 'wb') as dst:
                shutil.copyfileobj(src, dst)
            print(f"[SVD]  {f}  →  {target}")

        for f in flm_files:
            target = out / 'flash_algo' / Path(f).name
            target.parent.mkdir(exist_ok=True)
            with zf.open(f) as src, open(target, 'wb') as dst:
                shutil.copyfileobj(src, dst)
            print(f"[FLM]  {f}  →  {target}")

        for f in pdsc_files:
            target = out / Path(f).name
            with zf.open(f) as src, open(target, 'wb') as dst:
                shutil.copyfileobj(src, dst)
            print(f"[PDSC] {f}  →  {target}")

if __name__ == '__main__':
    if len(sys.argv) != 3:
        print("用法: python3 scripts/extract_dfp.py <pack文件> <输出目录>")
        sys.exit(1)
    extract_dfp(sys.argv[1], sys.argv[2])
