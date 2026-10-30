#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
从 target-gen 产物 N32H78x_Series.yaml 派生双核可烧录版本 N32H78x_Series_dual.yaml。

修两个已定位的缺陷（都不改厂商语义）：

  缺陷 1 —— 内存塌陷：cmsis-pack 的 Memories 是以名字为键的 HashMap，
            PDSC 里 CM7/CM4 两块内存都叫 IRAM1，CM7 那块被 CM4 覆盖掉了。
            本脚本把 CM7 的 IRAM1 (0x24000000..0x24020000) 补回来。
            两处都保留厂商原名 IRAM1 —— 运行时没有任何按键名查内存的代码
            （memory_region_by_address 按地址、memory_regions() 按 cores），
            重名无害。

  缺陷 2 —— 算法缺一份：PDSC 745/746 行 CM7/CM4 两份算法用同一个 FLM 文件，
            只有 RAMstart 不同（0x24000000 vs 0x30000000），target-gen 只留下了
            CM7 那份。本脚本按同一个 FLM 复制出 CM4 那份，load_address 改成
            0x30000008，address_range 改成厂商给 CM4 的 Bank2 区间。

            两份算法靠 `cores` 字段消歧：flashing/loader.rs:1105-1137 里
            core_name 取自「内存区的 cores」，算法过滤条件是
            `address_range.contains_range(region) && (cores.is_empty() || cores.contains(core_name))`。
            FLASH_Bank1 宽于 FLASH_Bank2（Bank2 ⊂ Bank1，厂商原样），
            所以标了 cores 之后每个区恰好匹配一份算法。

  注意：Bank2 (0x15080000..) 落在 Bank1 (0x15000000..) 范围内，这是厂商 PDSC
        原样，不是缺陷，不要"修"。

用法: python3 scripts/make_dual_yaml.py <src.yaml> <dst.yaml>
      （Makefile 的 target_% 目标在 target-gen 之后自动调用：
       build/targets/N32H78x_Series.yaml -> build/targets/N32H78x_Series_dual.yaml）

自检断言依赖 78x pack 的确定结构（2 份顶层算法 × 2 核、6 个变体各 2 块 IRAM1），
包升级导致结构变化时脚本会报错而不是静默产出坏文件。
"""

import sys
from pathlib import Path

CM7_RAM_START = 0x24000000
CM7_RAM_END = 0x24020000
CM7_LOAD_ADDR = "0x24000008"

CM4_RAM_START = 0x30000000
CM4_RAM_END = 0x30020000
CM4_LOAD_ADDR = "0x30000008"

BANK2_START = 0x15080000

# push back 阶段的延迟余量：CM7 的算法在 CM4 那份里跑不通，
# 反之亦然（RAM 基址不同），因此两份必须都存在。
CM7_IRAM_BLOCK = [
    "  - !Ram",
    "    name: IRAM1",
    "    range:",
    f"      start: 0x{CM7_RAM_START:08x}",
    f"      end: 0x{CM7_RAM_END:08x}",
    "    cores:",
    "    - cm7",
]

# CM4 的 IRAM 块原文（用于定位插入点）
CM4_RAM_MARKER = f"      start: 0x{CM4_RAM_START:08x}"


def split_algo_blocks(rest):
    """把顶层算法段按 `- name:` 切成块；返回 (前导行, 块列表, 尾部空行)。"""
    lead, blocks, cur = [], [], None
    for line in rest:
        if line.startswith("- name: "):
            if cur is not None:
                blocks.append(cur)
            cur = [line]
        elif cur is None:
            lead.append(line)
        else:
            cur.append(line)
    if cur is not None:
        blocks.append(cur)

    # 尾部空行还给文件级，不从最后一块里算
    if blocks:
        tail = []
        while blocks[-1] and blocks[-1][-1] == "":
            tail.insert(0, blocks[-1].pop())
    else:
        tail = []
    return lead, blocks, tail


def find_range(block):
    """从算法块里取出 flash_properties.address_range 的 (start, end) 行号与值。"""
    start_i = end_i = None
    for i, line in enumerate(block):
        s = line.strip()
        if s.startswith("start: 0x") and start_i is None:
            start_i = i
        elif s.startswith("end: 0x") and start_i is not None and end_i is None:
            end_i = i
    assert start_i is not None and end_i is not None, block[0]
    start = int(block[start_i].strip().split("0x")[1], 16)
    end = int(block[end_i].strip().split("0x")[1], 16)
    return start_i, end_i, start, end


def derive(block, core):
    """克隆一个算法块，改成 core（cm7 | cm4）专用的那一份。"""
    out = list(block)
    name = out[0].split("- name: ")[1]
    is_cm4 = core == "cm4"

    out[0] = f"- name: {name}_{core}"

    for i, line in enumerate(out):
        if line.startswith("  description: "):
            which = "CM4 / FLASH_Bank2" if is_cm4 else "CM7 / FLASH_Bank1"
            out[i] = f"{line} ({which})"
        elif line.startswith("  load_address: "):
            out[i] = f"  load_address: {CM4_LOAD_ADDR if is_cm4 else CM7_LOAD_ADDR}"

    start_i, _, start, end = find_range(out)
    if is_cm4:
        # 厂商 PDSC 746 行：CM4 那份 start=0x15080000，end 与 CM7 相同
        assert start == 0x15000000, f"{name}: 意外的 Bank1 起点 {start:#x}"
        out[start_i] = f"      start: 0x{BANK2_START:08x}"
        out[start_i + 1] = f"      end: 0x{end:08x}"
    out += ["  cores:", f"  - {core}"]
    return out


def main(src_path, dst_path):
    src, dst = Path(src_path), Path(dst_path)
    lines = src.read_text(encoding="utf-8").split("\n")

    fi = next(i for i, l in enumerate(lines) if l == "flash_algorithms:")
    head, rest = lines[: fi + 1], lines[fi + 1 :]

    lead, blocks, tail = split_algo_blocks(rest)
    assert len(blocks) == 2, f"期望 2 份顶层算法，实得 {len(blocks)}"

    new_algos = []
    for block in blocks:
        for core in ("cm7", "cm4"):
            new_algos.append(derive(block, core))

    # ---- 变体段：补回 CM7 的 IRAM1 + 让 flash_algorithms 两份都列上 ----
    out_head, i = [], 0
    while i < len(head):
        line = head[i]

        # 在 CM4 那整块 IRAM 之前插入 CM7 的那块。
        # 必须认 `- !Ram` 这一行（块的起点），不能在 `start:` 行前插入 ——
        # 那样会把 CM4 的块劈成两半。
        if (
            line == "  - !Ram"
            and i + 3 < len(head)
            and head[i + 1] == "    name: IRAM1"
            and head[i + 2] == "    range:"
            and head[i + 3] == CM4_RAM_MARKER
        ):
            out_head += CM7_IRAM_BLOCK

        # 变体级 flash_algorithms 列表：一行拆成两行
        if line.startswith("  - n32h78x_"):
            algo = line.strip().split("- ")[1]
            out_head.append(f"  - {algo}_cm7")
            out_head.append(f"  - {algo}_cm4")
            i += 1
            continue

        out_head.append(line)
        i += 1

    new = out_head + lead
    for block in new_algos:
        new += block
    new += tail

    dst.write_text("\n".join(new), encoding="utf-8")
    print(f"已写出 {dst}  ({len(new)} 行)")

    # ---- 自检 ----
    text = "\n".join(new)
    for want in ("- name: n32h78x_2048_cm7", "- name: n32h78x_2048_cm4",
                 "- name: n32h78x_4096_cm7", "- name: n32h78x_4096_cm4"):
        assert want in text, f"缺算法 {want}"
    assert text.count("name: IRAM1") == 12, \
        f"期望 6 个变体各 2 块 IRAM1 = 12，实得 {text.count('name: IRAM1')}"
    assert text.count("0x24000000") == 6, "CM7 IRAM 应出现 6 次（每变体一次）"
    assert "0x24000008" in text and "0x30000008" in text

    # 两块 IRAM 必须各自完整 —— 只数出现次数抓不住"吞掉一行"这类残缺
    cm7_block = "\n".join(CM7_IRAM_BLOCK)
    assert text.count(cm7_block) == 6, f"CM7 IRAM 块不完整，实得 {text.count(cm7_block)}"
    cm4_block = "\n".join(
        [
            "  - !Ram",
            "    name: IRAM1",
            "    range:",
            f"      start: 0x{CM4_RAM_START:08x}",
            f"      end: 0x{CM4_RAM_END:08x}",
            "    cores:",
            "    - cm4",
        ]
    )
    assert text.count(cm4_block) == 6, f"CM4 IRAM 块不完整，实得 {text.count(cm4_block)}"
    print("自检通过")


if __name__ == "__main__":
    if len(sys.argv) != 3:
        print("用法: python3 scripts/make_dual_yaml.py <src.yaml> <dst.yaml>", file=sys.stderr)
        sys.exit(1)
    main(sys.argv[1], sys.argv[2])
