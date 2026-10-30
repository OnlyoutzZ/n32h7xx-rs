# Changelog

本项目的变化记录在这里。格式参考
[Keep a Changelog](https://keepachangelog.com/zh-CN/1.1.0/)。

## [Unreleased]

### Changed

* **结构对齐**（此前裁决的 8 项全部落地）：
  * svd2rust 配置全套落定（`svd2rust.toml`：legacy 编号风格 + atomics +
    defmt + reexport_core_peripherals + **strict**）
  * crate 组织改为**单 crate `n32h7` + 每设备 feature**（n32h760 / n32h785），
    删除根 workspace `Cargo.toml` / `Cargo.lock`
  * 补丁目录 `svd/patches/` → `devices/patches/`；补丁后 SVD 产物 →
    `build/svds/`；`settings/<设备>.yaml` 由 `scripts/makesettings.sh` 生成
  * Makefile 重写（`crate_template` 机制，含 `.form`/`.check`
    戳记）；新增 `Makefile.toml`（cargo-make）双轨，任务名与 make 对齐
  * `scripts/makecrates.py` 重写（docs.rs 元数据、device.x
    选择、`rt`/`atomics` feature 门控）
  * README 重写：新增「结构对齐范围（有意差异表）」章节，
    勘误表扩充（svdtools 补丁层级语义、strict 暴露的厂商缺陷等）
* strict 模式新暴露 2 处厂商 SVD 缺陷（已在 `devices/patches/common.yaml`
  修复，两类各自全量扫描确认整份 SVD 内唯一）：
  * `LPUART1.LPUART_CTRL` 的 resetMask `0x01fffdff` 漏了 bit9（字段并集应为
    `0x01FFFFFF`），与 resetValue `0x200` 冲突
  * `GPV.GPV_FERID4` 字段名 `4KBCOT` 数字开头、非法 Rust 标识符，改名
    `_4KBCOT`
* `make_dual_yaml.py` 从仓库外纳入 `scripts/`（参数化为 `src → dst` 两个
  位置参数），由 `make target_%` 自动调用；产物与真板实测可用文件复验
  23/23 逐字符一致

### Fixed

* repro-check 的哈希集合排除 `n32h7/target/`：cargo check 的构建产物里也有
  同名 `device.x`，第一次运行时残留会被扫入而第二次没有（crate 被删过），
  造成假失败
* Makefile 增加空 `.SECONDARY:`（缺此防护时 settings/*.yaml 会被 make 当
  中间文件删除 → 每轮构建全链重生成、失败时还会清掉戳记）

### Added

* 初始流水线（`make all` 全链）：DFP 解包、SVD 校验、svdtools 补丁、
  svd2rust PAC 生成、回归快照比对、差异报告、可重复性校验、
  probe-rs target 生成
* 设备补丁入口 `devices/n32h760.yaml`、`devices/n32h785.yaml`
  + 全系列共用补丁（缺失 `<cpu>` 段、P2H 空 `<registers/>` 两处基础修复）
* probe-rs target 产物与真板实测可用文件逐字段比对通过
  （78x 双核修复脚本：23/23 逐字符一致）
* 仓库规范文件：MIT/Apache-2.0 双许可、CONTRIBUTING、本 CHANGELOG、
  `.gitattributes` / `.prettierrc.toml`、CI（GitHub Actions）
