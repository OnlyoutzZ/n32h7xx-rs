# n32h7xx-rs

国民技术 N32H7xx（Cortex-M7，78x 为 M7+M4 双核）的 Rust PAC 生成流水线。

组织方式是**单 crate + 每设备 feature**：`devices/*.yaml` 补丁入口、共用
`devices/patches/`、`svd2rust.toml` 统一生成配置、`scripts/makecrates.py` 生成
crate 骨架、Makefile 与 Makefile.toml（cargo-make）双轨构建。另有一套本仓库特有
的验收闸门（校验/回归/差异报告/可重复性）。

流程：厂商 DFP → 校验 SVD → svdtools 补丁修复 → svd2rust 生成 → form 拆分模块树 →
cargo check → 自动比对关键地址/中断 → 为 probe-rs 生成 target 描述。

## 快速开始

```bash
# 1) 环境安装（见下节，工具版本必须锁定）
bash scripts/tool_install.sh

# 2) 单命令生成全部 PAC（n32h7 crate，含 n32h760 + n32h785 两个设备 feature）
make all                # = validate + pacs

# 3) 冒烟验证
make check              # 逐设备 cargo check（真编译，不是只看生成成功）
make regression         # 关键地址/中断与基准快照比对
make diff-report        # 生成 原厂 vs 补丁后 的差异报告
make target_n32h760     # 生成 probe-rs 可加载的 target YAML（含双核修复）

# 等价的双轨入口（cargo-make）：
cargo make all && cargo make check
```

## 环境安装（版本锁定是硬要求）

方案 §8 的验收标准之一：**同一 SVD + 同一工具版本，两次生成产物必须一致**。
因此以下版本号不要随意升级（`scripts/tool_install.sh` 已锁定并一键安装）：

```bash
cargo install svd2rust --version 0.37.1
cargo install svdtools --version 0.5.0     # 注意：不是 pip install！
cargo install form     --version 0.13.0
rustup target add thumbv7em-none-eabihf    # PAC 构建需要
# Python 侧：本仓库脚本只用标准库（xml.etree 等），无需 pip 装任何东西
```

> **svdtools 必须是 Rust 版（cargo 安装）**。PyPI 上的 svdtools 停在 0.1.27，命令名是
> `svd`，且 `svd patch` 没有输出路径参数，与本文档所有命令不兼容。

## 仓库结构

```
n32h7xx-rs/
├── svd/vendor/                    # 厂商原始文件（不修改）
│   ├── Nationstech.N32H7xx_DFP.1.3.0.pack
│   ├── N32H7xx.svd                # extract_dfp.py 产出（全系列共用一个 SVD）
│   ├── Nationstech.N32H7xx_DFP.pdsc
│   └── flash_algo/*.FLM           # 4 个烧录算法（76x/78x × 2048/4096 KB）
├── devices/                       # 设备补丁入口（每个型号一个）
│   ├── n32h760.yaml
│   ├── n32h785.yaml
│   └── patches/common.yaml        # 全设备共用补丁
├── svd2rust.toml                  # svd2rust 生成配置（legacy 编号风格 + atomics +
│                                  #   defmt + reexport_core_peripherals + strict +
│                                  #   make_mod/generic_mod）
├── Makefile                       # make 轨道（纯 ASCII recipe，见故障排查表）
├── Makefile.toml                  # cargo-make 轨道（任务名与 make 对齐）
├── scripts/
│   ├── tool_install.sh            # 锁版工具安装（cargo install 方式，Windows 兼容）
│   ├── extract_dfp.py             # DFP(.pack) → SVD/FLM/PDSC
│   ├── validate_svd.py            # SVD 基础校验（字段/地址冲突/中断编号）
│   ├── diff_report.py             # 原厂 vs 补丁后 差异报告
│   ├── generate_baseline.py       # 生成回归快照（expected 或 current）
│   ├── gen_target.py              # probe-rs target 生成入口（target-gen 包装）
│   ├── make_dual_yaml.py          # 78x 双核 target 修复（内存塌陷 + 算法缺份）
│   ├── makecrates.py              # crate 骨架生成（Cargo.toml/build.rs/lib.rs/README）
│   └── makesettings.sh            # svd2rust --settings（crate_path）
├── regression/
│   ├── expected/                  # 基准快照（人工确认后提交）
│   ├── current/                   # 当前产物快照（gitignore）
│   └── test_regression.py
├── n32h7/                         # 生成的 PAC crate（gitignore，make 重建）
│   ├── src/n32h760/  n32h785/     # 每设备模块树（form 拆分产物）
│   └── src/generic.rs             # 全设备共用泛型寄存器代码
├── settings/                      # svd2rust --settings 生成文件（gitignore）
├── build/                         # 生成产物（gitignore）
│   ├── svds/<设备>.svd.patched
│   ├── reports/                   # 差异报告 JSON
│   └── targets/                   # probe-rs target YAML
└── .github/workflows/ci.yml
```

## 单 crate + 每设备 feature 模型

`n32h7` 是唯一 crate。每个设备是其**一个 Cargo feature**，代码生成到
`n32h7/src/<设备>/`（独立模块树），互不干扰；用户按需启用：

```toml
[dependencies.n32h7]
version = "1.0.0"
features = ["n32h760"]
```

```rust
let p = n32h7::n32h760::Peripherals::take().unwrap();
let _adc1 = &p.ADC1;   // legacy 编号风格：外设/寄存器名保持原样
```

生成链路：

1. `make crates` → `makecrates.py` 写 `n32h7/{Cargo.toml,build.rs,src/lib.rs,README.md}`
   （lib.rs 里 `#[cfg(feature = "n32h760")] pub mod n32h760;`）
2. 逐设备 `svd2rust -c ../../../svd2rust.toml -i ../../../build/svds/<设备>.svd.patched
   --settings "../../../settings/<设备>.yaml"`（`make_mod=true` → 直接产 `mod.rs`），
   `generic.rs` 上移到 crate `src/` 共用、删除逐设备 `build.rs`
3. `form -f -i mod.rs -o <设备目录>` 拆成模块树，产物 `lib.rs` 改名回 `mod.rs`
4. `cargo check --target thumbv7em-none-eabihf --features rt,atomics,<设备>`

`settings/<设备>.yaml` 由 `scripts/makesettings.sh` 生成，内容只有
`crate_path: crate::<设备>`（svd2rust 生成跨模块类型路径时要用，是功能性设置）。
svd2rust 的 settings 还支持 `html_url`（指向已发布的寄存器文档），本仓库暂无
已发布文档，故省略（该字段只影响文档注释）。

## 双轨构建：Makefile 与 Makefile.toml

两条轨道产物等价、任务名对齐（`patch`/`crates`/`svd2rust`/`form`/`check-patched`/
`clean-*`），戳记文件（`.form`/`.check`）互相可见：

| 目的 | make | cargo-make |
|------|------|-----------|
| 补丁 | `make build/svds/<设备>.svd.patched` | `cargo make patch` |
| 全量生成 | `make all` | `cargo make all`（default = pacs，all 补全校验） |
| 编译验证 | `make check` | `cargo make check` |
| 验收闸门 | `validate`/`regression`/`diff-report`/`repro-check` | 同名任务（转发到 make） |

## 补丁系统：当前修了什么

补丁文件不是一次写完的，按 svd2rust 报错和校验报告逐项追加。目前修了 4 处
（都在 `devices/patches/common.yaml`，因为全系列共用一个 SVD）：

1. **缺失 `<cpu>` 段**（svd2rust 直接报 `Cannot find cpu`）。
   厂商 SVD 顶层只有 vendor/name/version/addressUnitBits/width。
   补丁补齐 CM7：`mpuPresent/fpuPresent/nvicPrioBits/vendorSystickConfig` 等。
   注意 `vendorSystickConfig` 是 svd-rs 从零构建 Cpu 时的**必需**字段，缺了会报
   `has_vendor_systick must be initialized`。

2. **P2H 外设缺陷**：`P2H` 声明为 `<peripheral derivedFrom="H2P">`，其余 91 个派生
   外设都规范地省略 `<registers>` 元素（继承基外设），唯独 P2H 带了个空的
   `<registers />`。空元素把"继承"覆盖成"显式零寄存器"，svd2rust 于是在
   `Peripherals` 里生成 `pub p2h: P2h` 却不生成 `P2h` 类型，编译报
   `cannot find type P2h`。修法：`_copy` 把 H2P 的寄存器复制进 P2H
   （保留 P2H 自己的 baseAddress 0x50090400 与中断，清掉 derivedFrom）。

3. **LPUART1.LPUART_CTRL 的 resetMask 自相矛盾**（svd2rust **strict 模式**报
   `Reset value 0x200 conflicts with mask '0x1fffdff'`）。
   厂商 resetValue=0x200（bit9=1），但 resetMask=0x01fffdff 恰好不含 bit9；
   bit9 属于 RTST 字段（bit 8..9），全部字段并集为 0x01FFFFFF。
   厂商笔误漏了一位，补法：`resetMask` 补全为字段并集（resetMask 只参与 SVD
   校验、不进入生成代码，复位值 0x200 保持不动）。

4. **GPV.GPV_FERID4 字段名 `4KBCOT` 非法**（strict 模式报
   `Name check error: ... contains unexpected symbol`）：数字开头不是合法 Rust
   标识符，且全 SVD 扫描后这是唯一一处非法名。改名为 `_4KBCOT`（加下划线前缀
   保留原名）。该字段在 GPV（Global programmer view，芯片 ID/外设 ID 寄存器）
   里，名字本身无更多语义。

第 3、4 处是**启用 `strict = true` 之后才暴露的**厂商缺陷：旧的宽松
配置把它们容忍过去了。第 4 类（非法标识符）已做全量扫描，第 3 类（resetMask
冲突）同样全量扫描过——整份 SVD 各只有一处。

## 结构对齐范围（已裁决的 8 项 + 落地差异）

对齐项：① svd2rust 全套配置（`svd2rust.toml`）② 单 crate + 每设备
feature ③ 仓库 git 化 ④ Makefile.toml 双轨 ⑤ 规范文件全套（LICENSE-MIT/APACHE、
CONTRIBUTING、CHANGELOG、.gitattributes、.prettierrc.toml）⑥ `devices/patches/`
布局 ⑦ `make_dual_yaml.py` 纳入并挂钩 ⑧ crate 名 `n32h7`。

**有意差异（为可操作性保留）：**

| # | 惯常做法 | 本仓库 | 原因 |
|---|--------------|--------|------|
| 1 | 补丁产物 `svd/*.svd.patched` | `build/svds/*.svd.patched` | 生成产物统一进 build/（gitignore 一处收口） |
| 2 | `svdtools makedeps` 精确依赖 | `devices/patches/*.yaml` 粗粒度依赖 | makedeps 在 Windows 输出 `\\?\` 开头的 verbatim 路径，make 报 `target pattern contains no '%'` |
| 3 | 无 `.SECONDARY`（settings/*.yaml 被 make 当中间文件删除） | `.SECONDARY:` 置空 | 否则每轮构建都会因 settings 重建触发全链重生成，且失败时把戳记清掉 |
| 4 | `default = patch` | `default = pacs` | 本仓库主产物即 PAC，没有 mmaps/html 等辅助轨 |
| 5 | settings 由 Makefile.toml 内联 writefile 生成 | `scripts/makesettings.sh` 共用 | 双轨生成同一文件，逻辑只留一份；无 html_url（无已发布文档） |
| 6 | `tool_install.sh` 下载 Linux 预编译二进制 | `cargo install` 锁版 | Windows 兼容 |
| 7 | 无验收闸门 | `validate`/`regression`/`diff-report`/`repro-check` | 方案 §8 的验收交付物 |

注：`make` 每轮都会全量重建生成物（`crates` 为 phony → `Cargo.toml` 被重写 →
依赖链过期）。这是该结构下的固有行为（make 语义决定），未做例外处理；
增量迭代请用 `cargo make form`/`cargo make check-patched`（带 mtime 判断）。

## 对方案文档的勘误（均为实测确认）

落地过程中发现方案文档若干处与真实工具/真实数据不符，此处逐条记录。Makefile 与
脚本已按"实测事实"实现。

| # | 方案原文 | 实测事实 | 本仓库的处理 |
|---|---------|---------|-------------|
| 1 | `pip3 install svdtools`（§4.1.1） | PyPI 最高 0.1.27；方案 §7 自己又要求 0.5.0。0.5.0 是 Rust 工具，需 cargo 安装 | 文档与 Makefile 一律用 `svdtools`（cargo 版） |
| 2 | `svd patch $< -o $@`（§4.6.3） | `svdtools patch <yaml> <输出路径>`：输出是**位置参数**，没有 `-o` | Makefile 改位置参数 |
| 3 | `form ... && rm src/lib.rs`（§4.6.1 步骤 4） | form 会把 `src/lib.rs` **原地重写成模块树根**（`pub mod xxx;` 列表）。把它删掉等于删掉 crate 根，PAC 直接编译不了 | 保留 `src/lib.rs`（同类 PAC 仓库同样做法） |
| 4 | PAC 的 Make 目标 = `src/lib.rs`（§4.6.3） | 该文件由配方自身改写/存在与否不稳定，Make 会反复重建，失去增量意义 | 改用 `.form`/`.check` 戳记 |
| 5 | 改外设地址示例 `_modify: GPIOA:` （§4.5.1 注释） | svdtools 的外设级改写在 `_modify._peripherals` 下；根的 `_modify` 键保留给设备级字段（cpu/version/name…） | 示例注释已改正 |
| 6 | Makefile 补丁规则只依赖 `devices/%.yaml`（§4.9） | 改了 `_include` 引用的公共补丁不会触发重新打补丁（陈旧产物静默） | 依赖集合加入 `devices/patches/*.yaml`（常见做法是 `svdtools makedeps`，但本机输出 verbatim 路径不可用，故粗粒度） |
| 7 | `make validate` 以原厂 SVD 为闸门（§4.9） | 原厂 SVD **必然**有问题（缺 cpu），闸门永远不可能通过，`make all` 死锁 | 原厂=非阻断报告；补丁后产物=阻断性闸门 |
| 8 | 按设备分别提供 `N32H760.svd`/`N32H785.svd`（§4.2） | 厂商 DFP 只提供一个 `N32H7xx.svd`，覆盖 730/735/760/762/765/785/787 全系列 | 两个 `devices/*.yaml` 的 `_svd` 指向同一文件 |
| 9 | 未给 PAC 的 `Cargo.toml` 内容（§4.6） | 实测依赖：`cortex-m` 必需；`cortex-m-rt`（rt feature）、`critical-section`、`defmt`、`portable-atomic`（atomics）可选；`vcell` 必需（藏在拆分后的 `src/generic.rs` 里，只看 lib.rs 会漏） | `scripts/makecrates.py` 生成（含 docs.rs 元数据） |
| 10 | 脚本一律 `python3`（§4 全部示例） | 部分 Windows 环境的 `python3` 是应用商店坏壳（运行即报错） | Makefile 运行时探测可用解释器 |
| 11 | 脚本输出 `⚠`/`✓`（§4.4/§4.7.3） | Windows GBK 控制台下 `UnicodeEncodeError` 直接崩溃 | 两处脚本加 stdout UTF-8 重配置 |
| 12 | 根 `Cargo.toml` workspace（§4.2） | 与单 crate 模型冲突：单 crate 直接放仓库根、**没有** workspace；且 workspace 承载多 crate 时与"每设备 feature"自相矛盾 | 删除根 Cargo.toml/Cargo.lock，crate `n32h7` 直接放仓库根（.gitignore `/n32h7/`） |
| 13 | 补丁文件顶层可直接写寄存器名（最初推断） | svdtools 顶层键**与所处位置绑定**：device 顶层的键只能是外设名/设备级属性（`_modify`/`_copy`/`_include`…），直接写寄存器名报 ``Could not find `LPUART_CTRL`. Present peripherals: …``；参考实现里"顶层寄存器名"的补丁文件都是被 `_include` 嵌入到外设层级下展开的 | 寄存器修改写在外设键下（`LPUART1: _modify: LPUART_CTRL:`），字段修改再下一层（`GPV: GPV_FERID4: _modify:`） |
| 14 | 宽松 svd2rust 配置可容忍厂商 SVD（隐性假设） | 启用 `strict = true` 后新暴露 2 处厂商缺陷：LPUART_CTRL resetMask 缺位、GPV_FERID4 字段名 `4KBCOT` 数字开头。均已在 common.yaml 修复并各自全量扫描确认唯一 | 见「补丁系统」3、4 条 |

方案 §4.7.2 的 `generate_baseline.py` 只写 `regression/expected/`，但 §4.7.3 的回归
测试需要 `regression/current/`——方案没有给出生成 current 的入口。本仓库为
`generate_baseline.py` 增加了可选第 3 参数（默认行为不变），由 `make regression` 先
刷新 current 再比对。

## probe-rs target

```bash
make target_n32h760     # 型号名只是触发性参数；实际从厂商 DFP 一次性生成全部系列
```

产物是 **系列级文件**（不是按型号 17 个）：PDSC 的 `<family>`/型号结构决定输出粒度，
每个文件内部是 `name:（家族）+ variants:[各 17 个型号分散在三处] + flash_algorithms:`：

| 文件 | 内部变体 | 算法条目 |
|------|---------|---------|
| `build/targets/N32H73x_Series.yaml` | N32H730xIx7、N32H735xIx7、N32H735xIx7EC | n32h76x_2048 |
| `build/targets/N32H76x_Series.yaml` | N32H760/762/765 ×(Ix7/Kx7/EC)，8 个 | n32h76x_2048 / n32h76x_4096 |
| `build/targets/N32H78x_Series.yaml` | N32H785/787 ×(Ix7/Kx7/EC)，6 个 | n32h78x_2048 / n32h78x_4096 |
| `build/targets/N32H78x_Series_dual.yaml` | 同上 | 同上（**双核修复版，推荐用这个**） |

`target_%` 的第二步自动派生 `N32H78x_Series_dual.yaml`（见下）。加载方式
（`--chip-description-path` 吃文件，也可用环境变量吃目录）：

```bash
probe-rs info --chip N32H785xIx7 --chip-description-path build/targets/N32H78x_Series_dual.yaml
PROBE_RS_CHIP_DESCRIPTION_PATH=build/targets/ probe-rs info --chip N32H785xIx7
```

注意 `probe-rs chip list` **不读** chip description path（只列内置注册表），拿它做
加载验证会得出假阴性；离线验证必须用连接类命令（info/reset/download 等）。

### 78x 双核产物的两个缺陷（target-gen 上游问题，已实测定位）

原始 target-gen 产物对 N32H78x 双核变体有 2 处缺陷；73x/76x 两文件不受影响。

1. **CM7 的 IRAM1 丢失**：cmsis-pack 的内存表以名字为键，厂商 PDSC 里 CM7/CM4
   两块 RAM 都叫 IRAM1，CM7 那块（0x24000000..0x24020000）被覆盖。实测本流水线
   产物里 `0x24000000` 出现 **0 次** —— CM7 变体没有自己的 RAM。
2. **烧录算法缺一份、且未标 cores**：厂商 PDSC 为 CM7/CM4 各配一份算法（同一个
   FLM，只有 RAMstart 不同），实测产物只剩 1 份，`load_address: 0x24000008`
   （CM7 的 RAM）、覆盖整个 Bank1（0x15000000..0x151e0000）、无 `cores:` 字段。
   按 probe-rs 的算法筛选规则（`address_range.contains_range(region) && cores
   .contains(core_name)`），CM4 的 FLASH_Bank2 区间会错选这份算法——从 CM7 的
   RAM 里启动烧录算法，实跑不通。

**修复**（`scripts/make_dual_yaml.py`，已纳入本流水线并由 `make target_%` 自动调用）：
补回 CM7 IRAM 块、按同一个 FLM 复制出 CM4 的算法并把两份都标上 `cores:` 消歧
（算法名加 `_cm7`/`_cm4` 后缀，CM4 那份 load_address=0x30000008、区间改成厂商给
CM4 的 Bank2）。脚本带自检断言（依赖 78x pack 的确定结构），包升级导致结构变化时
报错而不是静默产出坏文件。

**验证**：修复后产物与「probe-rs 内置、真板实测可用」的
`probe-rs/targets/N32H7xx_Series.yaml` 逐字段比对：**23/23 项逐字符一致**
（17 个型号变体 + 6 个算法条目），73x/76x 两文件未修正即逐字符一致。
结论：`target-gen 产物 + make_dual_yaml.py == 真板可用文件`。

注意：Bank2 (0x15080000..) 落在 Bank1 (0x15000000..) 范围内，这是厂商 PDSC
原样，不是缺陷。

## 故障排查

| 症状 | 原因 | 处理 |
|------|------|------|
| `svdtools: command not found` | 装成了 Python 版或没装 | `cargo install svdtools --version 0.5.0` |
| `svd2rust` 报 `Cannot find cpu` | SVD 缺 `<cpu>` | 已由 `devices/patches/common.yaml` 补齐 |
| `has_vendor_systick must be initialized` | 补 cpu 段时漏了 `vendorSystickConfig` | 同上（必需字段） |
| `cannot find type P2h` | P2H 派生外设带空 `<registers/>` | 已由 common.yaml 的 `_copy` 修复 |
| `Reset value 0x200 conflicts with mask` | 厂商 resetMask 缺位（strict 模式） | 已由 common.yaml 的 LPUART1 修复 |
| `Name check error ... unexpected symbol` | 字段/枚举值名非法标识符（strict 模式） | 已由 common.yaml 的 GPV 修复；新缺陷先全量扫描再改名 |
| `Could not find \`XXX\`. Present peripherals: …`（svdtools） | 补丁顶层键被当外设名 | 寄存器修改写在外设键下、字段修改写在寄存器键下（见勘误 #13） |
| `settings/*.yaml` 莫名消失 | make 把 pattern 规则产物当中间文件清理 | 已用 `.SECONDARY:` 置空（见结构差异表 #3） |
| `error[E0433]: unresolved crate vcell` | crate 清单缺 vcell 依赖 | makecrates.py 已加（重跑 `make crates` 后清单会被重写） |
| 改 `common.yaml` 后产物没变 | 依赖缺口 | 已修（依赖集合含 `devices/patches/*.yaml`）；如仍不生效 `make clean` 后重跑 |
| `unexpected EOF while looking for matching quote`，且报错前缀的"程序名"变成 `else:`/`exit:` 之类的词 | Windows + GBK 代码页 + MSYS sh 下，recipe 里含非 ASCII 且带 `if…fi` 等多引号结构时，MSYS 的 argv 转换把命令行拆坏、脚本被截断（本机已复现定位到行为层面） | recipe 一律 ASCII；中文消息放 Python 脚本输出。本仓库 `repro-check` 已按此改写 |
| `UnicodeEncodeError: 'gbk' codec` | 在 GBK 控制台跑老脚本 | 本仓库脚本已自愈；自写脚本可加 `sys.stdout.reconfigure(encoding="utf-8")` |
| `target pattern contains no '%'` | 用了 `svdtools makedeps` 的 Windows 输出 | 本仓库不使用 makedeps |
| 回归测试说"基准文件不存在" | 首次运行 | `make baseline`（人工确认后），expected/ 应入库 |

## 交付物对照（方案 §8）

| 交付物 | 验收标准 | 本仓库对应 |
|--------|---------|-----------|
| 单命令生成 PAC | 补丁→可编译 PAC 全自动 | `make all`（= validate + pacs） |
| 生成结果可重复 | 同输入同工具两跑 SHA256 一致 | `make repro-check` |
| 关键地址/中断自动比对 | 与基准快照比对 | `make regression` |
| 工具使用说明完整 | 安装/流程/排查 | 本 README + `scripts/tool_install.sh` |
| 差异报告 | JSON 落盘 | `make diff-report` → `build/reports/` |
| probe-rs 入口 | 可加载的 target YAML | `make target_n32h760` → `build/targets/`（双核修复版已与真板实测可用的内置文件逐字符比对：23/23 一致） |
