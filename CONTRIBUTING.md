# 贡献指南

感谢你想为 n32h7xx-rs 出力。本仓库生成国民技术 N32H7xx 系列的 Rust PAC
(peripheral access crate)，采用「单 crate + 每设备 feature」的组织方式。

## 开始之前

* 先在本仓库的 issue/PR 里搜一搜，再查 svdtools 的文档与 issue：
  你要修的寄存器/字段是否已有现成补丁，能搬就搬。
* 改动落在哪里：
  * SVD 结构修复（增删寄存器、改字段、改地址）→ `devices/*.yaml`（设备级）
    或 `devices/patches/*.yaml`（全系列共用）；
  * 字段的枚举值与写约束 → `devices/fields/`（如 `gpio.yaml`）；
    把一组重复寄存器/字段收成数组 → `devices/collect/`；
  * 生成配置（编号风格、atomics、defmt 等）→ 根目录 `svd2rust.toml`，
    改动会令全部产物变化，动手前请先开 issue 说明动机。
* 工具版本是锁定的（见 README：svd2rust 0.37.1 / svdtools 0.5.0 / form 0.13.0），
  不要升级工具后直接提交产物——版本变更需单独讨论。

## 改补丁的流程

1. 编辑 `devices/` 下的 YAML（svdtools patch 格式）；
2. `make all`（或 `make build/svds/n32h760.svd.patched`）重新打补丁、生成 PAC；
3. `make regression` 确认关键地址/中断与基准快照一致；出现意外变化要先在
   issue/PR 里解释清楚；
4. `make diff-report` 生成"原厂 vs 补丁后"差异报告，确认差异恰好就是你这次改的内容；
5. 若发现方案文档与实际工具/数据不符，请同步更新 README 的「对方案文档的勘误」表。

## Windows / MSYS 注意事项

* **Makefile recipe 一律 ASCII**：本机 MSYS sh 在 GBK 代码页下会把含非 ASCII 且带
  多引号结构（`if…fi` 等）的 recipe 拆坏（详见 README 故障排查表）。
  自动生成的同义逻辑请放 Python 脚本里，用输出代替。
* 工具安装用 `scripts/tool_install.sh`（cargo install，版本锁定），
  不要 `pip install svdtools`（PyPI 版过旧且命令不兼容）。
