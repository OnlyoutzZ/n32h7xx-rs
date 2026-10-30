# -*- coding: utf-8 -*-
"""从 N32H7xx 用户手册 Markdown 生成 svdtools 字段补丁（devices/fields/*.yaml）。

数据源：<md-dir>/NN.UM_N32H78X_<MODULE>.en.md 里的寄存器表：

    ### USART Control Register 1 Register (USART_CTRL1)
    Address offset: 0x00
    Reset value: 0x0000 0000
    |Bit Field|Name|Attribute|Description|
    |28|IFCEN|rw|Idle frame controllable enable.<br>0: Disable...<br>1: Enable...|

产物：外设体形式的 YAML（相对外设，供 devices/<device>.yaml 用 _include 引入）：

    USART1:
      USART_CTRL1:
        _modify:
          IFCEN: {description: "Idle frame controllable enable."}
        IFCEN:
          _name: IFCEN
          Disabled: [0, "Disable idle frame controllable adjustment"]
          Enabled: [1, "Enable idle frame controllable adjustment"]

占位符处理：手册用 DACxy_CTRL / TROVCyIEN / GPIOx_PMODE 这类通道占位符，
SVD 用具体实例（DAC12_CTRL / TROVC2IEN）。替换规则不写死，而是把手册寄存器名
与 SVD 寄存器名逐字符对齐反推（x->1, y->2），再套到字段名上；字段名同时尝试
原样与替换后两种写法，以 SVD 中真实存在的那个为准。

用法：
    python scripts/gen_um_fields.py --modules USART,RCC
    python scripts/gen_um_fields.py --all --out devices/fields
"""
import argparse
import collections
import glob
import io
import os
import re
import sys
import xml.etree.ElementTree as ET

try:
    import yaml
except ImportError:
    sys.exit('need pyyaml: pip install pyyaml')

# ---------------------------------------------------------------- 手册解析

HEAD = re.compile(r'^(#{3,6})\s+(.*)$')
PAREN = re.compile(r'\(([A-Za-z0-9_\\]+)\)')
OFF = re.compile(r'Address\s*offset\s*:\s*(0x[0-9A-Fa-f]+)', re.I)
RST = re.compile(r'Reset\s*value\s*:\s*(0x[0-9A-Fa-f][0-9A-Fa-f ]*)', re.I)
BIT = re.compile(r'^\[?\s*(\d+)(?:\s*:\s*(\d+))?\s*\]?$')
MARK = re.compile(r'^\s*\[[^\]]{1,4}\]\s*')
# 描述里的 0:/1:/00:/11: 枚举项
ENUM = re.compile(r'(?:^|<br>|\s)([01]{1,4})\s*[:：]\s*([^<]+)')


def unesc(s):
    return s.replace('\\_', '_').replace('\\', '')


def clean(s):
    s = unesc(s).replace('*', '').strip()
    return MARK.sub('', s).strip()


def field_name(s):
    s = clean(s)
    return re.sub(r'\s*\[[^\]]*\]\s*$', '', s).strip()


def reg_from_heading(text):
    text = text.replace('\uff08', '(').replace('\uff09', ')')
    names = [unesc(x).upper() for x in PAREN.findall(text)]
    for n in reversed(names):
        if '_' in n and not n.isdigit():
            return n
    return names[-1] if names else None


def is_bit_head(ln):
    cells = [clean(c).lower() for c in ln.strip().strip('|').split('|')]
    return len(cells) >= 3 and cells[0].replace(' ', '') in (
        'bit', 'bits', 'bitfield') and 'name' in cells


def parse_enums(desc):
    out = []
    for m in ENUM.finditer(desc):
        v, t = m.group(1), m.group(2).strip()
        if t:
            out.append((int(v, 2) if len(v) > 1 else int(v), t))
    return out


def first_sentence(desc):
    """字段描述只取枚举项之前的第一句，去掉 markdown 噪声。"""
    s = re.sub(r'<br\s*/?>', ' ', desc)
    s = re.split(r'\s[0-9]{1,4}\s*[:：]\s', s)[0]
    s = re.sub(r'[_~]', '', s)
    s = re.sub(r'\s+', ' ', s).strip(' .;')
    return s


def parse_manual(md_dir):
    """-> {module: {REG: {offset, reset, fields:[{hi,lo,name,attr,desc,enums}]}}}"""
    out = {}
    for path in sorted(glob.glob(os.path.join(md_dir, '*.en.md'))):
        module = os.path.basename(path).split('.', 1)[1].replace('.en.md', '')
        module = re.sub(r'^UM_N32H78X_', '', module)
        lines = io.open(path, encoding='utf-8', errors='replace').read().splitlines()
        regs = out.setdefault(module, {})
        i = 0
        while i < len(lines):
            hm = HEAD.match(lines[i])
            reg = reg_from_heading(hm.group(2)) if hm else None
            if not reg:
                i += 1
                continue
            off = rst = None
            fields = []
            in_tbl = False
            i += 1
            while i < len(lines) and not HEAD.match(lines[i]):
                ln = lines[i]
                o = OFF.search(ln)
                if o and off is None:
                    off = int(o.group(1), 16)
                r = RST.search(ln)
                if r and rst is None:
                    rst = r.group(1).strip()
                if ln.startswith('|') and is_bit_head(ln):
                    in_tbl = True
                elif in_tbl and not ln.startswith('|'):
                    in_tbl = False
                elif in_tbl and ln.startswith('|') and re.match(r'^\|\s*:?[-^]', ln):
                    pass
                elif in_tbl and ln.startswith('|'):
                    cells = [c.strip() for c in ln.strip().strip('|').split('|')]
                    if len(cells) >= 4:
                        bm = BIT.match(clean(cells[0]))
                        if bm:
                            hi = int(bm.group(1))
                            lo = int(bm.group(2)) if bm.group(2) else hi
                            desc = clean(cells[3])
                            nm = field_name(cells[1])
                            # 表格单元格里的换行/合并写法（"A<BR>AND B"）不是字段名
                            if '<' in nm.upper() or ' AND ' in nm.upper():
                                continue
                            fields.append({
                                'hi': hi, 'lo': lo,
                                'name': nm,
                                'attr': clean(cells[2]),
                                'desc': desc,
                                'enums': parse_enums(desc),
                            })
                i += 1
            if fields and reg not in regs:
                regs[reg] = {'offset': off, 'reset': rst, 'fields': fields}
    return out


# ---------------------------------------------------------------- SVD 索引

class Svd:
    """按 (外设, 寄存器) 建索引；同名寄存器在多个外设里出现时逐实例展开。"""

    def __init__(self, path):
        root = ET.parse(path).getroot()
        self.periphs = {}        # periph -> [regname]
        self.reg_owners = {}     # regname -> [periph, ...]（手册名靠它找实例）
        self.rinfo = {}          # (periph, regname) -> {offset, reset, fields{}}
        for p in root.iter('peripheral'):
            pn = p.findtext('name')
            names = []
            for r in p.iter('register'):
                rn = (r.findtext('name') or '').upper()
                if not rn:
                    continue
                names.append(rn)
                self.reg_owners.setdefault(rn, []).append(pn)
                fields = {}
                for f in r.iter('field'):
                    bo, bw = f.findtext('bitOffset'), f.findtext('bitWidth')
                    if bo is None or bw is None:
                        continue
                    fields[(f.findtext('name') or '').upper()] = (
                        int(bo, 0), int(bw, 0), f.findtext('access') or '',
                        f.findtext('description') or '')
                self.rinfo[(pn, rn)] = {
                    'offset': r.findtext('addressOffset'),
                    'reset': r.findtext('resetValue'),
                    'fields': fields,
                }
            if names:
                self.periphs[pn] = names


def sq(s):
    return re.sub(r'[^A-Z0-9]', '', s.upper())


def key(s):
    s = re.sub(r'[0-9]+', '#', sq(s))
    s = re.sub(r'(?<=[A-Z])[XYN](?=[A-Z]|$)', '#', s)
    return re.sub(r'#+', '#', s)


def reg_aliases(name):
    """精确别名集合（已 sq）：原名、去 _L/_H 半字后缀、定时器字母 -> 占位符。"""
    out = {name}
    m = re.match(r'^(.*?)_[LH]$', name)
    if m:
        out.add(m.group(1))
    m = re.search(r'_T([A-F])(?=[A-Z_])', name)
    if m:
        out.add(name[:m.start()] + '_Tx' + name[m.end():])
    return {sq(n) for n in out}


def placeholder_map(manual_name, svd_name):
    """逐字符对齐手册/SVD 寄存器名，反推 x/y/n -> 具体字符。"""
    a = [c for c in sq(manual_name) if c.isalnum()]
    b = [c for c in sq(svd_name) if c.isalnum()]
    if len(a) != len(b):
        return None
    m = {}
    for x, y in zip(a, b):
        if x in 'XYN' and x != y:
            if m.setdefault(x, y) != y:
                return None
    return m


def apply_map(name, mapping):
    if not mapping:
        return name
    return ''.join(mapping.get(c, c) for c in name)


# ---------------------------------------------------------------- 枚举命名

STOP = {'the', 'a', 'an', 'is', 'are', 'be', 'of', 'to', 'in', 'on', 'for',
        'and', 'or', 'by', 'with', 'as', 'at', 'from', 'this', 'that',
        'when', 'if', 'it', 'its', 'will', 'can', 'then', 'than'}


def camel(text, max_words=3, max_len=28):
    words = re.findall(r'[A-Za-z0-9]+', text)
    words = [w for w in words if w.lower() not in STOP]
    out = ''
    for w in words[:max_words]:
        out += w[0].upper() + w[1:]
        if len(out) >= max_len // 2:
            break
    out = out[:max_len] or 'Value'
    if out[0].isdigit():
        out = 'V' + out
    return out


def variant_names(values):
    """为枚举项起名：用描述首词 CamelCase，冲突则加序号。"""
    names, used = [], set()
    for (val, text) in values:
        base = camel(text)
        n, cur = 1, base
        while cur in used:
            n += 1
            cur = f'{base}{n}'
        used.add(cur)
        names.append(cur)
    return names


# ---------------------------------------------------------------- 生成

def gen_module(module, regs, svd, show=False, positional=True):
    """-> (yaml_dict, stats, problems)"""
    # 两级索引：精确（去下划线）优先，落空才退化到占位符归一。
    # 否则 USART_CTRL1/2/3 会被 key() 全部塌成 USARTCTRL#，字段互相串台。
    exact = collections.defaultdict(list)
    fuzzy = collections.defaultdict(list)
    for rn in svd.reg_owners:
        for a in reg_aliases(rn):
            exact[a].append(rn)
            fuzzy[key(a)].append(rn)

    doc = collections.OrderedDict()
    stats = collections.Counter()
    problems = []
    unmatched = collections.Counter()

    for mreg, reg in regs.items():
        hits = []
        for a in reg_aliases(mreg):
            hits.extend(exact.get(a, []))
        if not hits:
            for a in reg_aliases(mreg):
                hits.extend(fuzzy.get(key(a), []))
        hits = sorted(set(hits))
        if not hits:
            stats['reg_unmatched'] += 1
            problems.append(('reg_unmatched', mreg))
            continue

        for sreg in hits:
            pmap = placeholder_map(mreg, sreg)
            if pmap is None:
                # 名字差异不是占位符造成的（例如 _L/_H、拼写不同），不套替换
                pmap = {}
            # _L/_H 是同一本 64 位寄存器拆成的两个 32 位寄存器：
            # 手册按绝对位号描述整体，落到 _H 上要减 32。
            base_hit = None
            for suf, shift in (('_L', 0), ('_H', 32)):
                if sreg.endswith(suf) and sreg[:-2] + (
                        '_H' if suf == '_L' else '_L') in hits:
                    base_hit = shift
            for periph in svd.reg_owners[sreg]:
                pinfo = svd.rinfo[(periph, sreg)]
                fields_out = collections.OrderedDict()
                for f in reg['fields']:
                    fn = f['name'].upper()
                    if not fn or fn == 'RESERVED':
                        continue
                    lo, hi = f['lo'], f['hi']
                    if base_hit is not None:
                        if hi < 32:
                            if base_hit != 0:
                                continue
                        elif lo >= 32:
                            if base_hit != 32:
                                continue
                            lo, hi = lo - 32, hi - 32
                        else:
                            # 跨半字段对不上任何单个寄存器里的字段
                            stats['field_covered'] += 1
                            continue
                    cand = [fn]
                    if pmap:
                        cand.insert(0, apply_map(fn, pmap))
                    hit = next((c for c in cand if c in pinfo['fields']), None)
                    if hit is None:
                        stats['field_unmatched'] += 1
                        unmatched[f'{sreg}.{fn}'] += 1
                        # 分类：同位置改名 / 位段被别的字段占着 / SVD 没建模
                        span = (lo, hi - lo + 1)
                        same = [n for n, v in pinfo['fields'].items()
                                if (v[0], v[1]) == span]
                        if len(same) == 1:
                            stats['field_rename'] += 1
                            problems.append(('rename', sreg, fn,
                                             f'{f["hi"]}:{f["lo"]}', same[0]))
                            if positional:
                                hit = same[0]
                                stats['field_rename_applied'] += 1
                            else:
                                continue
                        elif any(v[0] <= lo and v[0] + v[1] - 1 >= hi
                                 for v in pinfo['fields'].values()):
                            stats['field_covered'] += 1
                            continue
                        else:
                            stats['field_missing'] += 1
                            problems.append(('missing', sreg, fn,
                                             f'{f["hi"]}:{f["lo"]}', ''))
                            continue
                    bo, bw, acc, sdesc = pinfo['fields'][hit]
                    if (hi - lo + 1) != bw:
                        stats['width_mismatch'] += 1
                        problems.append(('width', sreg, hit,
                                         f'{hi}:{lo}', f'{bo + bw - 1}:{bo}'))
                        continue

                    desc = first_sentence(f['desc'])
                    entry = collections.OrderedDict()
                    if desc and desc.upper() != hit:
                        entry['_description'] = desc
                    enums = f['enums']
                    if len(enums) >= 2:
                        vals = sorted(dict(enums).items())
                        if all(0 <= v < (1 << bw) for v, _ in vals):
                            names = variant_names(vals)
                            entry['_name'] = camel(desc, 3, 20) if desc else hit
                            for nm, (v, t) in zip(names, vals):
                                entry[nm] = [v, re.sub(r'\s+', ' ', t).strip()]
                            stats['enum_fields'] += 1
                            stats['enum_items'] += len(vals)
                    if entry:
                        fields_out[hit] = entry
                        stats['field_patched'] += 1

                if not fields_out:
                    continue
                body = collections.OrderedDict()
                mods = collections.OrderedDict()
                for fn, entry in fields_out.items():
                    desc = entry.pop('_description', None)
                    if desc:
                        mods[fn] = {'description': desc}
                if mods:
                    body['_modify'] = mods
                for fn, entry in fields_out.items():
                    body[fn] = entry
                doc.setdefault(periph, collections.OrderedDict())[sreg] = body

    # 每个外设内按寄存器名排序，保证可重复
    for pn in doc:
        doc[pn] = collections.OrderedDict(sorted(doc[pn].items()))
    if show:
        for k, v in unmatched.most_common(40):
            print(f'    unmatched {v:>3}x {k}')
    return doc, stats, problems


def dump_yaml(doc, path):
    """按统一风格输出：4 空格缩进、不写文档分隔符、UTF-8。"""
    text = yaml.safe_dump(dict(doc), sort_keys=False, allow_unicode=True,
                          default_flow_style=False, width=1000)
    header = ('# 由 scripts/gen_um_fields.py 从用户手册 Markdown 生成，勿手工编辑\n'
              '# 数据源：E:/probe-rs/3610/用户手册/用户手册/*.en.md\n')
    os.makedirs(os.path.dirname(path), exist_ok=True)
    io.open(path, 'w', encoding='utf-8', newline='\n').write(header + text)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--md-dir', default=r'E:/probe-rs/3610/用户手册/用户手册')
    ap.add_argument('--svd', default='svd/vendor/N32H7xx.svd')
    ap.add_argument('--out', default='devices/fields')
    ap.add_argument('--modules', default='')
    ap.add_argument('--all', action='store_true')
    ap.add_argument('--dry-run', action='store_true')
    ap.add_argument('--show', action='store_true', help='列出未匹配字段')
    ap.add_argument('--no-positional', action='store_true',
                    help='关掉同位置改名兜底匹配')
    args = ap.parse_args()

    manual = parse_manual(args.md_dir)
    svd = Svd(args.svd)

    if args.modules:
        mods = [m.strip() for m in args.modules.split(',') if m.strip()]
    elif args.all:
        mods = sorted(manual)
    else:
        sys.exit('need --modules or --all')

    total = collections.Counter()
    for m in mods:
        if m not in manual:
            print(f'!! 手册里没有模块 {m}')
            continue
        doc, stats, problems = gen_module(m, manual[m], svd, show=args.show,
                                          positional=not args.no_positional)
        total.update(stats)
        nfield = sum(len(r) - (1 if '_modify' in r else 0)
                     for p in doc.values() for r in p.values())
        print(f'{m:18} 外设 {len(doc):>3}  寄存器 '
              f'{sum(len(p) for p in doc.values()):>4}  字段 {nfield:>5}  '
              f'枚举 {stats["enum_fields"]:>4}  未匹配字段 {stats["field_unmatched"]:>4}'
              f' (改名 {stats["field_rename"]:>3}/被覆盖 {stats["field_covered"]:>4}'
              f'/缺建模 {stats["field_missing"]:>4})'
              f'  宽度不符 {stats["width_mismatch"]:>3}')
        if not args.dry_run and doc:
            dump_yaml(doc, os.path.join(args.out, f'{m.lower()}.yaml'))

    print()
    print('汇总：', dict(total))


if __name__ == '__main__':
    main()
