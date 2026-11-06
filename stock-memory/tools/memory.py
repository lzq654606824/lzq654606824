#!/usr/bin/env python3
"""股市记忆库命令行工具：写入（new）、找回（find / tags / symbols）、校验（check）。

只依赖 Python 3.8+ 标准库。所有日期按 Asia/Shanghai 理解。
"""
from __future__ import annotations

import argparse
import re
import sys
from collections import Counter
from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Dict, List, Optional, Tuple

# 上海自 1991 年起不再使用夏令时，固定 UTC+8 与 Asia/Shanghai 等价，且不依赖系统 tzdata。
SHANGHAI = timezone(timedelta(hours=8), "Asia/Shanghai")
DEFAULT_ROOT = Path(__file__).resolve().parent.parent

TYPES = {
    "note": {"dir": "notes", "prefix": "N", "label": "笔记"},
    "review": {"dir": "reviews", "prefix": "R", "label": "复盘"},
    "lead": {"dir": "leads", "prefix": "L", "label": "线索"},
}
SOURCES = ["self", "announcement", "news", "research", "data", "social", "people", "other"]
DIRECTIONS = ["long", "short"]
RESULTS = ["open", "win", "loss", "flat"]
LEAD_STATUSES = ["open", "confirmed", "invalidated", "expired"]

COMMON_FIELDS = ["id", "type", "title", "date", "created", "symbols", "tags", "source", "source_ref", "related"]
TYPE_FIELDS = {
    "note": [],
    "review": ["direction", "opened", "closed", "result", "pnl_pct"],
    "lead": ["status", "review_on"],
}
COMMON_REQUIRED = ["id", "type", "title", "date", "created", "source"]
TYPE_REQUIRED = {"note": [], "review": ["direction", "opened", "result"], "lead": ["status"]}
LIST_FIELDS = {"symbols", "tags", "related"}

ID_RE = re.compile(r"^([NRL])-(\d{8})-(\d{4})(-\d+)?$")
SYMBOL_RE = re.compile(r"^[0-9A-Z]+\.[A-Z]+$")


# ---------- frontmatter ----------

def _unquote(value: str) -> str:
    if len(value) >= 2 and value[0] == value[-1] == '"':
        return value[1:-1].replace('\\"', '"').replace("\\\\", "\\")
    if len(value) >= 2 and value[0] == value[-1] == "'":
        return value[1:-1].replace("''", "'")
    return value


def _parse_value(value: str):
    if value.startswith("[") and value.endswith("]"):
        items = [_unquote(part.strip()) for part in value[1:-1].split(",")]
        return [item for item in items if item]
    return _unquote(value)


def parse_frontmatter(text: str) -> Tuple[Dict[str, object], str]:
    """解析 `---` 包围的 frontmatter，只支持模板用到的 YAML 子集：
    `键: 值`、`键: [a, b]`、`键:` 后跟 `- 项` 的列表、整行 `#` 注释。"""
    lines = text.splitlines()
    if not lines or lines[0].strip() != "---":
        raise ValueError("文件必须以 --- 开头的 frontmatter 开始")
    end = next((i for i in range(1, len(lines)) if lines[i].strip() == "---"), None)
    if end is None:
        raise ValueError("frontmatter 缺少结束的 ---")

    meta: Dict[str, object] = {}
    list_key: Optional[str] = None
    for raw in lines[1:end]:
        stripped = raw.strip()
        if not stripped or stripped.startswith("#"):
            continue
        if stripped == "-" or stripped.startswith("- "):
            if list_key is None:
                raise ValueError(f"列表项前缺少字段名：{raw}")
            if not isinstance(meta[list_key], list):
                meta[list_key] = []
            item = _unquote(stripped[1:].strip())
            if item:
                meta[list_key].append(item)  # type: ignore[union-attr]
            continue
        key, sep, value = raw.partition(":")
        if not sep or not key.strip() or key[0].isspace():
            raise ValueError(f"无法解析的行：{raw}")
        key, value = key.strip(), value.strip()
        meta[key] = _parse_value(value)
        list_key = key if value == "" else None

    for key in LIST_FIELDS:
        value = meta.get(key)
        if isinstance(value, str):
            meta[key] = [value] if value else []
    body = "\n".join(lines[end + 1:])
    return meta, body


def _needs_quote(value: str) -> bool:
    return (
        (value[:1] != "" and value[:1] in "[]{}\"'#&*!|>%@`,:")
        or value.startswith("- ")
        or ": " in value
        or " #" in value
        or value.endswith(":")
        or value != value.strip()
    )


def _dump_scalar(value: str, force_quote: bool = False) -> str:
    if force_quote or _needs_quote(value):
        return '"' + value.replace("\\", "\\\\").replace('"', '\\"') + '"'
    return value


def dump_frontmatter(meta: Dict[str, object]) -> str:
    lines = ["---"]
    for key, value in meta.items():
        if isinstance(value, list):
            lines.append(f"{key}: [" + ", ".join(_dump_scalar(str(v)) for v in value) + "]")
        elif value is None or value == "":
            lines.append(f"{key}:")
        else:
            lines.append(f"{key}: {_dump_scalar(str(value), force_quote=(key == 'title'))}")
    lines.append("---")
    return "\n".join(lines) + "\n"


# ---------- 记忆条目 ----------

@dataclass
class Entry:
    path: Path
    meta: Dict[str, object]
    body: str

    def get(self, key: str) -> str:
        value = self.meta.get(key, "")
        return value if isinstance(value, str) else ""

    def list(self, key: str) -> List[str]:
        value = self.meta.get(key, [])
        return value if isinstance(value, list) else []

    @property
    def date(self) -> Optional[date]:
        return parse_date(self.get("date"))


def parse_date(value: str) -> Optional[date]:
    try:
        return date.fromisoformat(value)
    except (TypeError, ValueError):
        return None


def today_shanghai() -> date:
    return datetime.now(SHANGHAI).date()


def load_entries(root: Path) -> Tuple[List[Entry], List[Tuple[Path, str]]]:
    entries: List[Entry] = []
    failures: List[Tuple[Path, str]] = []
    for info in TYPES.values():
        for path in sorted((root / info["dir"]).rglob("*.md")):
            try:
                meta, body = parse_frontmatter(path.read_text(encoding="utf-8"))
            except (OSError, UnicodeDecodeError, ValueError) as exc:
                failures.append((path, str(exc)))
                continue
            entries.append(Entry(path, meta, body))
    return entries, failures


def validate(entry: Entry, root: Path) -> Tuple[List[str], List[str]]:
    errors: List[str] = []
    warnings: List[str] = []
    m = entry.meta
    entry_type = entry.get("type")

    for key in COMMON_REQUIRED + TYPE_REQUIRED.get(entry_type, []):
        if not entry.get(key):
            errors.append(f"缺少必填字段 {key}")
    for key in LIST_FIELDS:
        if key in ("symbols", "tags") and key not in m:
            errors.append(f"缺少字段 {key}（没有就写 {key}: []）")

    if entry_type and entry_type not in TYPES:
        errors.append(f"type 只能是 {' / '.join(TYPES)}，当前为 {entry_type}")
    elif entry_type:
        info = TYPES[entry_type]
        rel = entry.path.relative_to(root)
        if rel.parts[0] != info["dir"]:
            errors.append(f"{entry_type} 类型应放在 {info['dir']}/ 下")
        match = ID_RE.match(entry.get("id"))
        if entry.get("id") and not match:
            errors.append("id 格式应为 <N|R|L>-YYYYMMDD-HHMM，例如 N-20261106-1430")
        elif match and match.group(1) != info["prefix"]:
            errors.append(f"{entry_type} 的 id 应以 {info['prefix']}- 开头")

    entry_date = entry.date
    if entry.get("date") and entry_date is None:
        errors.append("date 应为 YYYY-MM-DD")
    elif entry_date is not None:
        rel = entry.path.relative_to(root)
        if len(rel.parts) < 3 or rel.parts[1] != str(entry_date.year):
            warnings.append(f"按 date 应放在 {rel.parts[0]}/{entry_date.year}/ 下")
        if not entry.path.name.startswith(entry_date.isoformat()):
            warnings.append(f"文件名建议以 date（{entry_date.isoformat()}）开头")

    created = entry.get("created")
    if created:
        try:
            created_at = datetime.fromisoformat(created)
            if created_at.tzinfo is None:
                warnings.append("created 建议带时区，例如 +08:00")
        except ValueError:
            errors.append("created 应为 ISO 时间，例如 2026-11-06T14:30:00+08:00")

    if entry.get("source") and entry.get("source") not in SOURCES:
        errors.append(f"source 只能是 {' / '.join(SOURCES)}")
    for symbol in entry.list("symbols"):
        if not SYMBOL_RE.match(symbol):
            warnings.append(f"标的 {symbol} 建议写成 代码.市场（大写），例如 600519.SH")
    for tag in entry.list("tags"):
        if tag.startswith("#") or " " in tag:
            warnings.append(f"标签 {tag} 不要带 # 或空格")

    if entry_type == "review":
        if entry.get("direction") and entry.get("direction") not in DIRECTIONS:
            errors.append(f"direction 只能是 {' / '.join(DIRECTIONS)}")
        result = entry.get("result")
        if result and result not in RESULTS:
            errors.append(f"result 只能是 {' / '.join(RESULTS)}")
        opened = parse_date(entry.get("opened"))
        if entry.get("opened") and opened is None:
            errors.append("opened 应为 YYYY-MM-DD")
        closed = parse_date(entry.get("closed"))
        if entry.get("closed") and closed is None:
            errors.append("closed 应为 YYYY-MM-DD")
        if result and result != "open" and not entry.get("closed"):
            errors.append("已平仓（result 不是 open）时必须填 closed")
        if opened and closed and closed < opened:
            errors.append("closed 不能早于 opened")
        if entry.get("pnl_pct"):
            try:
                float(entry.get("pnl_pct"))
            except ValueError:
                errors.append("pnl_pct 应为数字（百分比，不带 %），例如 -3.5")

    if entry_type == "lead":
        if entry.get("status") and entry.get("status") not in LEAD_STATUSES:
            errors.append(f"status 只能是 {' / '.join(LEAD_STATUSES)}")
        if entry.get("review_on") and parse_date(entry.get("review_on")) is None:
            errors.append("review_on 应为 YYYY-MM-DD")

    return errors, warnings


# ---------- 命令 ----------

def _split_csv(value: Optional[str]) -> List[str]:
    if not value:
        return []
    return [part.strip() for part in re.split(r"[,，]", value) if part.strip()]


def _slugify(text: str) -> str:
    slug = re.sub(r"[^\w-]+", "-", text, flags=re.UNICODE).strip("-_")
    slug = re.sub(r"-{2,}", "-", slug)[:40].strip("-")
    return slug or "untitled"


def _template_body(root: Path, entry_type: str) -> str:
    path = root / "templates" / f"{entry_type}.md"
    if not path.exists():
        return ""
    return parse_frontmatter(path.read_text(encoding="utf-8"))[1].rstrip("\n") + "\n"


def cmd_new(args: argparse.Namespace, root: Path) -> int:
    now = datetime.now(SHANGHAI).replace(microsecond=0)
    entry_date = parse_date(args.date) if args.date else now.date()
    if entry_date is None:
        print("--date 应为 YYYY-MM-DD", file=sys.stderr)
        return 2
    info = TYPES[args.type]

    entries, _ = load_entries(root)
    existing_ids = {e.get("id") for e in entries}
    base_id = f"{info['prefix']}-{now:%Y%m%d-%H%M}"
    entry_id, n = base_id, 2
    while entry_id in existing_ids:
        entry_id, n = f"{base_id}-{n}", n + 1

    source = args.source or ("self" if args.type == "review" else "")
    meta: Dict[str, object] = {
        "id": entry_id,
        "type": args.type,
        "title": args.title,
        "date": entry_date.isoformat(),
        "created": now.isoformat(),
        "symbols": [s.upper() for s in _split_csv(args.symbols)],
        "tags": _split_csv(args.tags),
        "source": source,
        "source_ref": args.source_ref or "",
        "related": _split_csv(args.related),
    }
    if args.type == "review":
        meta.update(
            direction=args.direction or "",
            opened=args.opened or "",
            closed=args.closed or "",
            result=args.result or "",
            pnl_pct=args.pnl_pct or "",
        )
    elif args.type == "lead":
        meta.update(status=args.status or "open", review_on=args.review_on or "")

    folder = root / info["dir"] / str(entry_date.year)
    folder.mkdir(parents=True, exist_ok=True)
    stem = f"{entry_date.isoformat()}-{_slugify(args.slug or args.title)}"
    path, n = folder / f"{stem}.md", 2
    while path.exists():
        path, n = folder / f"{stem}-{n}.md", n + 1
    path.write_text(dump_frontmatter(meta) + _template_body(root, args.type), encoding="utf-8")

    print(path.relative_to(root).as_posix())
    errors, _ = validate(Entry(path, meta, ""), root)
    for message in errors:
        print(f"  待补全：{message}")
    return 0


def _matches(entry: Entry, args: argparse.Namespace, today: date) -> bool:
    if args.type and entry.get("type") != args.type:
        return False
    if args.id and entry.get("id") != args.id:
        return False
    if args.symbol:
        query = args.symbol.upper()
        if not any(s.upper() == query or s.upper().split(".")[0] == query for s in entry.list("symbols")):
            return False
    for tag in args.tag or []:
        if not any(t == tag or t.startswith(tag + "/") for t in entry.list("tags")):
            return False
    entry_date = entry.date
    since = parse_date(args.since) if args.since else None
    if args.days is not None:
        recent = today - timedelta(days=args.days - 1)
        since = max(since, recent) if since else recent
    if since and (entry_date is None or entry_date < since):
        return False
    until = parse_date(args.until) if args.until else None
    if until and (entry_date is None or entry_date > until):
        return False
    if args.source and entry.get("source") != args.source:
        return False
    if args.status and entry.get("status") != args.status:
        return False
    if args.result and entry.get("result") != args.result:
        return False
    if args.due:
        review_on = parse_date(entry.get("review_on"))
        if entry.get("type") != "lead" or entry.get("status") != "open" or not review_on or review_on > today:
            return False
    if args.text:
        haystack = (entry.get("title") + "\n" + entry.body).lower()
        if args.text.lower() not in haystack:
            return False
    return True


def _format_line(entry: Entry) -> str:
    entry_type = entry.get("type")
    label = TYPES.get(entry_type, {}).get("label", entry_type or "?")
    state = entry.get("result") if entry_type == "review" else entry.get("status") if entry_type == "lead" else ""
    if state:
        label = f"{label}/{state}"
    symbols = ",".join(entry.list("symbols")) or "-"
    tags = " ".join(f"#{t}" for t in entry.list("tags"))
    parts = [entry.get("date") or "????-??-??", entry.get("id") or "?", label, symbols, entry.get("title")]
    if tags:
        parts.append(tags)
    return "  ".join(parts)


def cmd_find(args: argparse.Namespace, root: Path) -> int:
    for value, flag in ((args.since, "--from"), (args.until, "--to")):
        if value and parse_date(value) is None:
            print(f"{flag} 应为 YYYY-MM-DD", file=sys.stderr)
            return 2
    if args.days is not None and args.days < 1:
        print("--days 至少为 1", file=sys.stderr)
        return 2
    entries, failures = load_entries(root)
    for path, message in failures:
        print(f"跳过无法解析的文件 {path.relative_to(root).as_posix()}：{message}", file=sys.stderr)

    today = today_shanghai()
    hits = [e for e in entries if _matches(e, args, today)]
    hits.sort(key=lambda e: (e.get("date"), e.get("created")), reverse=True)
    if args.limit:
        hits = hits[: args.limit]

    for entry in hits:
        rel = entry.path.relative_to(root).as_posix()
        if args.paths:
            print(rel)
        else:
            print(_format_line(entry))
            print(f"    {rel}")
    if not args.paths:
        print(f"共 {len(hits)} 条")
    return 0


def _cmd_count(field: str, args: argparse.Namespace, root: Path) -> int:
    entries, _ = load_entries(root)
    counter: Counter = Counter()
    for entry in entries:
        if args.type and entry.get("type") != args.type:
            continue
        counter.update(entry.list(field))
    for value, count in sorted(counter.items(), key=lambda item: (-item[1], item[0])):
        print(f"{count:>4}  {value}")
    return 0


def cmd_check(args: argparse.Namespace, root: Path) -> int:
    entries, failures = load_entries(root)
    error_count = len(failures)
    for path, message in failures:
        print(f"[错误] {path.relative_to(root).as_posix()}：{message}")

    ids: Dict[str, List[Entry]] = {}
    for entry in entries:
        ids.setdefault(entry.get("id"), []).append(entry)

    for entry in entries:
        rel = entry.path.relative_to(root).as_posix()
        errors, warnings = validate(entry, root)
        if entry.get("id") and len(ids[entry.get("id")]) > 1:
            errors.append(f"id {entry.get('id')} 重复")
        for ref in entry.list("related"):
            if ref not in ids:
                warnings.append(f"related 中的 {ref} 在库里找不到")
        for message in errors:
            print(f"[错误] {rel}：{message}")
        for message in warnings:
            print(f"[提醒] {rel}：{message}")
        error_count += len(errors)

    if error_count:
        print(f"发现 {error_count} 个错误，共 {len(entries) + len(failures)} 个文件")
        return 1
    print(f"检查通过：{len(entries)} 条记忆")
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="memory.py",
        description="股市记忆库：写入并找回行情笔记、交易复盘、市场线索。",
    )
    parser.add_argument("--root", type=Path, default=DEFAULT_ROOT, help="记忆库根目录（默认是 tools/ 的上一级）")
    sub = parser.add_subparsers(dest="command", required=True)

    new = sub.add_parser("new", help="新建一条记忆，生成文件后再补正文")
    new.add_argument("type", choices=list(TYPES), help="note=行情笔记 review=交易复盘 lead=市场线索")
    new.add_argument("--title", required=True, help="一句话标题")
    new.add_argument("--date", help="对应的市场日期 YYYY-MM-DD，默认上海时间今天")
    new.add_argument("--symbols", help="标的，逗号分隔，例如 600519.SH,00700.HK")
    new.add_argument("--tags", help="标签，逗号分隔")
    new.add_argument("--source", choices=SOURCES, help="信息来源类别")
    new.add_argument("--source-ref", help="出处：链接、文件名或一句说明")
    new.add_argument("--related", help="相关记忆的 id，逗号分隔")
    new.add_argument("--slug", help="文件名里的短标题，默认取 title")
    new.add_argument("--direction", choices=DIRECTIONS, help="复盘：long 做多 / short 做空")
    new.add_argument("--opened", help="复盘：开仓日期 YYYY-MM-DD")
    new.add_argument("--closed", help="复盘：平仓日期 YYYY-MM-DD")
    new.add_argument("--result", choices=RESULTS, help="复盘：open 未平 / win 盈 / loss 亏 / flat 平")
    new.add_argument("--pnl-pct", help="复盘：收益率（百分比数字，可选）")
    new.add_argument("--status", choices=LEAD_STATUSES, help="线索：状态，默认 open")
    new.add_argument("--review-on", help="线索：计划复查日期 YYYY-MM-DD")

    find = sub.add_parser("find", help="按标的 / 时间 / 标签等条件找回记忆")
    find.add_argument("--type", choices=list(TYPES))
    find.add_argument("--symbol", help="标的代码，600519 可匹配 600519.SH")
    find.add_argument("--tag", action="append", help="标签，可重复（同时满足）；父标签匹配子标签")
    find.add_argument("--from", dest="since", metavar="YYYY-MM-DD", help="起始日期（含）")
    find.add_argument("--to", dest="until", metavar="YYYY-MM-DD", help="结束日期（含）")
    find.add_argument("--days", type=int, help="最近 N 天（含今天，上海时间）")
    find.add_argument("--source", choices=SOURCES)
    find.add_argument("--status", choices=LEAD_STATUSES, help="线索状态")
    find.add_argument("--result", choices=RESULTS, help="复盘结果")
    find.add_argument("--due", action="store_true", help="到期该复查的线索（status=open 且 review_on 不晚于今天）")
    find.add_argument("--text", help="在标题和正文里全文查找")
    find.add_argument("--id", help="按 id 精确查找")
    find.add_argument("--limit", type=int, help="最多显示条数")
    find.add_argument("--paths", action="store_true", help="只输出文件路径")

    for name, label in (("tags", "标签"), ("symbols", "标的")):
        counter = sub.add_parser(name, help=f"列出所有{label}及出现次数")
        counter.add_argument("--type", choices=list(TYPES))

    sub.add_parser("check", help="校验所有记忆的字段和存放位置")
    return parser


def main(argv: Optional[List[str]] = None) -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(errors="replace")
    args = build_parser().parse_args(argv)
    root = args.root.resolve()
    if args.command == "new":
        return cmd_new(args, root)
    if args.command == "find":
        return cmd_find(args, root)
    if args.command in ("tags", "symbols"):
        return _cmd_count(args.command, args, root)
    return cmd_check(args, root)


if __name__ == "__main__":
    sys.exit(main())
