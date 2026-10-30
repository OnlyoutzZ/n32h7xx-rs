# N32H7xx PAC 生成流水线 —— 顶层编排
#
# 结构（Makefile、crate_template、--settings 机制）：
#   - 单 crate n32h7 + 每设备 feature（n32h760 / n32h785）
#   - svd2rust 读根目录 svd2rust.toml（make_mod / generic_mod / legacy 编号风格 /
#     atomics / defmt / 内核外设重导出），逐设备生成到 n32h7/src/<设备>/mod.rs，
#     再由 form 拆成模块树；Cargo.toml / build.rs / src/lib.rs / README.md 由
#     scripts/makecrates.py 生成；settings/<设备>.yaml 由 makesettings.sh 生成
# 本仓库特有的验收门控：
#   validate / baseline / regression / diff-report / repro-check / target_%
#
# 注意：recipe 一律 ASCII —— 本机 Windows GBK 代码页 + MSYS 下，含非 ASCII 且带
# if…fi 等引号结构的 recipe 会被拆坏（详见 README 故障排查表）。
#
# 两处有意选择：
#   1. 不用 `svdtools makedeps`（Windows 输出 `\\?\` 开头的 verbatim 路径，make 无法
#      解析，报 `target pattern contains no '%'`），改用 devices/patches/*.yaml 粗粒度依赖
#   2. validate/regression 等验收目标保留，作为方案文档的验收标准

SHELL := /usr/bin/env bash

CRATES ?= n32h7
DEVICES := $(patsubst devices/%.yaml,%,$(wildcard devices/*.yaml))

# 厂商 DFP 包（只此一个，覆盖 N32H7xx 全系列）
PACK := svd/vendor/Nationstech.N32H7xx_DFP.1.3.0.pack

PYTHON   ?= $(shell python3 -c "import sys" >/dev/null 2>&1 && echo python3 || echo python)
SVDTOOLS ?= svdtools
SVD2RUST ?= svd2rust
FORM     ?= form

# 设备 yaml 按 crate 前缀匹配（devices/<crate>*.yaml）
yamlsearch = $(wildcard devices/$(1)*.yaml)
YAMLS := $(foreach crate,$(CRATES),$(call yamlsearch,$(crate)))

PATCHED_SVDS := $(patsubst devices/%.yaml,build/svds/%.svd.patched,$(YAMLS))
RUST_SRCS := $(foreach crate,$(CRATES),$(patsubst devices/$(crate)%.yaml,$(crate)/src/$(crate)%/mod.rs,$(call yamlsearch,$(crate))))
FORM_SRCS := $(foreach crate,$(CRATES),$(patsubst devices/$(crate)%.yaml,$(crate)/src/$(crate)%/.form,$(call yamlsearch,$(crate))))
CHECK_SRCS := $(foreach crate,$(CRATES),$(patsubst devices/$(crate)%.yaml,$(crate)/src/$(crate)%/.check,$(call yamlsearch,$(crate))))

PATCH_INPUTS := $(wildcard devices/patches/*.yaml)

.PHONY: all validate crates svd2rust form check pacs baseline regression diff-report repro-check install clean

# 防止 make 把 pattern 规则生成的文件当「中间文件」清理（不置空的话：
# settings/*.yaml 每次构建结束后被删，下轮重建时 mtime 变新导致全链重生成；
# 失败时也会被清）。置空 .SECONDARY = 一切目标都不自动删除。
.SECONDARY:

all: validate pacs

# ---- 补丁：厂商 SVD -> 补丁后 SVD ----
build/svds/%.svd.patched: devices/%.yaml $(PATCH_INPUTS) svd/vendor/N32H7xx.svd
	@echo "--- patch: $* ---"
	@mkdir -p $(dir $@)
	$(SVDTOOLS) patch $< $@

# ---- crate 骨架：Cargo.toml / build.rs / src/lib.rs / README.md ----
crates:
	$(PYTHON) scripts/makecrates.py devices/ -y --families $(CRATES)

# ---- 逐设备生成（crate_template）----
define crate_template
$(1)/src/%/mod.rs: build/svds/%.svd.patched settings/%.yaml $(1)/Cargo.toml
	@mkdir -p $$(@D)
	cd $$(@D) && $(SVD2RUST) -c ../../../svd2rust.toml -i ../../../$$< --settings "../../../$$(word 2,$$^)"
	rustfmt $$@
	rm $$(@D)/build.rs
	mv -f $$(@D)/generic.rs $$(@D)/../

settings/%.yaml: build/svds/%.svd.patched
	@mkdir -p settings
	bash scripts/makesettings.sh $$* $$@

$(1)/src/%/.form: $(1)/src/%/mod.rs
	$(FORM) -f -i $$< -o $$(@D)
	rm $$<
	mv $$(@D)/lib.rs $$<
	rustfmt $$<
	@touch $$@

$(1)/src/%/.check: $(1)/src/%/.form
	cd $(1) && cargo check --target thumbv7em-none-eabihf --features rt,atomics,$$*
	@touch $$@

$(1)/Cargo.toml: crates

endef

$(foreach crate,$(CRATES),$(eval $(call crate_template,$(crate))))

# svd2rust / form 为逐步目标；pacs = 生成 + 拆分后的完整可用 crate
svd2rust: $(RUST_SRCS) crates

form: $(FORM_SRCS) crates

pacs: $(FORM_SRCS)

check: $(CHECK_SRCS)

# ---- 校验（vendor 非阻断 / 补丁后阻断；方案 §4.9 的修正版）----
validate: $(PATCHED_SVDS)
	@echo "--- vendor SVD (non-blocking, known issues) ---"
	@for f in svd/vendor/*.svd; do $(PYTHON) scripts/validate_svd.py "$$f" || true; done
	@echo "--- patched SVD (blocking) ---"
	@for f in $(PATCHED_SVDS); do $(PYTHON) scripts/validate_svd.py "$$f"; done
	@echo "OK: patched SVDs validated"

# ---- 回归基准快照（方案 §6 步骤 8；人工确认后运行一次；expected/ 入库）----
baseline: $(PATCHED_SVDS)
	@for d in $(DEVICES); do \
		$(PYTHON) scripts/generate_baseline.py build/svds/$$d.svd.patched $$d; \
	done

# ---- 回归：先用当前补丁产物刷新 regression/current/，再与基准比对 ----
regression: $(PATCHED_SVDS)
	@for d in $(DEVICES); do \
		$(PYTHON) scripts/generate_baseline.py build/svds/$$d.svd.patched $$d regression/current; \
		$(PYTHON) regression/test_regression.py $$d; \
	done

diff-report: $(PATCHED_SVDS)
	@for d in $(DEVICES); do \
		$(PYTHON) scripts/diff_report.py \
			svd/vendor/N32H7xx.svd \
			build/svds/$$d.svd.patched \
			$$d \
			build/reports/; \
	done

# 单个 DFP 包覆盖全系列，target_<任意型号名> 均从同一 pack 生成（见 README）。
# 第二步派生双核可烧录版：pack 的 CM7/CM4 同名 IRAM1 在 cmsis-pack 里互相覆盖、
# CM4 的算法缺一份，由 make_dual_yaml.py 修复（细节见脚本 docstring）。
target_%:
	@mkdir -p build/targets
	$(PYTHON) scripts/gen_target.py $(PACK) build/targets/
	$(PYTHON) scripts/make_dual_yaml.py build/targets/N32H78x_Series.yaml build/targets/N32H78x_Series_dual.yaml

# 可重复性验收（方案 §8）：同一输入 + 同一工具版本，两次生成产物 SHA256 一致。
# 必须删掉 crate 再生成第二次 —— 否则 Make 戳记会让第二次变成空操作，什么都没验到。
# 哈希集合必须排除 n32h7/target/：cargo check 的 build 产物里也有同名 device.x，
# 第一次运行若残留旧构建产物就会被扫进去，第二次没有（crate 被删过），造成假失败。
# 配方刻意 ASCII + 单行 if：见文件头注释与 README 故障排查表。
repro-check:
	@echo "== run 1: generate =="
	@$(MAKE) --no-print-directory pacs
	@find n32h7 ! -path 'n32h7/target/*' -type f \( -name "*.rs" -o -name "Cargo.toml" -o -name "build.rs" -o -name "device.x" -o -name "README.md" \) | sort | xargs sha256sum > build/repro-1.sha256
	@rm -rf n32h7
	@echo "== run 2: regenerate =="
	@$(MAKE) --no-print-directory pacs
	@find n32h7 ! -path 'n32h7/target/*' -type f \( -name "*.rs" -o -name "Cargo.toml" -o -name "build.rs" -o -name "device.x" -o -name "README.md" \) | sort | xargs sha256sum > build/repro-2.sha256
	@if diff -q build/repro-1.sha256 build/repro-2.sha256 >/dev/null; then echo "REPRO OK: $$(wc -l < build/repro-1.sha256) files identical across two runs"; else echo "REPRO FAIL, diff:"; diff build/repro-1.sha256 build/repro-2.sha256 | head -20; exit 1; fi

install:
	bash scripts/tool_install.sh

clean:
	rm -rf build n32h7 settings
