# 股市记忆库

把行情笔记、交易复盘、值得记住的市场线索写成带字段的 Markdown 文件，之后能按标的、时间、标签找回来。

它只是记忆库：不接行情数据，不做预测，不给买卖建议。

> **注意：这个仓库目前是公开的**（也是 GitHub 个人主页仓库）。写进来的任何内容所有人都能看到。
> 记真实交易之前，先决定是把仓库改成私有，还是换一个私有仓库存放。

## 目录

```text
stock-memory/
├── README.md          # 本文件：怎么用
├── SCHEMA.md          # 字段定义和取值
├── notes/<年>/        # 行情笔记  note
├── reviews/<年>/      # 交易复盘  review
├── leads/<年>/        # 市场线索  lead
├── templates/         # 三类记忆的模板（note.md / review.md / lead.md）
└── tools/
    ├── memory.py      # 写入、找回、校验的命令行工具（只用 Python 标准库）
    └── test_memory.py # 工具的测试
```

## 一条记忆长什么样

```markdown
---
id: L-20261106-1037
type: lead
title: "回购公告"
date: 2026-11-06
created: 2026-11-06T10:37:03+08:00
symbols: [00700.HK]
tags: [回购]
source: announcement
source_ref: 港交所公告 2026-11-05
related: []
status: open
review_on: 2026-11-20
---

## 线索
……
```

字段含义、必填项和取值见 [SCHEMA.md](SCHEMA.md)。日期一律按上海时间（Asia/Shanghai）。

## 写入

需要 Python 3.8 以上，无需安装任何依赖。以下命令都在 `stock-memory/` 目录下执行。

```bash
# 行情笔记
python3 tools/memory.py new note --title "尾盘放量" \
  --symbols 600519.SH --tags 白酒,量价/放量 --source self

# 市场线索（到 review_on 那天提醒自己回头看）
python3 tools/memory.py new lead --title "回购公告" \
  --symbols 00700.HK --tags 回购 --source announcement \
  --source-ref "港交所公告 2026-11-05" --review-on 2026-11-20

# 交易复盘（date 填平仓日；可以只填一部分，之后在文件里补）
python3 tools/memory.py new review --title "白酒短线" --date 2026-11-03 \
  --symbols 600519.SH --direction long --opened 2026-10-20 \
  --closed 2026-11-03 --result loss --related L-20261020-0930
```

命令会按模板生成文件并打印路径，还没填的必填字段会列成「待补全」。接着：

1. 打开生成的文件，补全字段，在正文各小节写内容。
2. `python3 tools/memory.py check` 校验，有错误会指出文件和字段。
3. `git add` 并 `git commit` 保存。

不想用命令行时，也可以复制 `templates/` 里的模板，按 `<目录>/<年>/<日期>-<短标题>.md` 命名，手工填写。

## 找回

```bash
python3 tools/memory.py find --symbol 600519            # 某个标的（600519 能匹配 600519.SH）
python3 tools/memory.py find --tag 白酒                 # 某个标签（含 白酒/高端 这样的子标签）
python3 tools/memory.py find --from 2026-10-01 --to 2026-10-31   # 某段时间（按 date）
python3 tools/memory.py find --days 7                   # 最近 7 天
python3 tools/memory.py find --type review --result loss         # 亏损的复盘
python3 tools/memory.py find --type lead --status open           # 还在跟踪的线索
python3 tools/memory.py find --due                      # 到复查日期的线索
python3 tools/memory.py find --text 回购                # 全文查找标题和正文
python3 tools/memory.py find --symbol 600519 --tag 白酒 --days 90   # 条件可以组合（同时满足）

python3 tools/memory.py tags       # 所有标签及次数
python3 tools/memory.py symbols    # 所有标的及次数
```

结果按 `date` 从新到旧排列，每条显示日期、id、类别/状态、标的、标题、标签和文件路径。加 `--paths` 只输出路径，便于交给编辑器打开。

没有 Python 时也能用 `grep` / `rg` 找：

```bash
rg -l "600519.SH" notes reviews leads
rg -l "^date: 2026-11" notes reviews leads
```

## 不做的事

- 不接实时或历史行情，不抓价格、K 线、新闻。
- 不做预测、打分或信号，不给买卖建议。
- 不连接券商账户，不下单。
- 不设金额、持仓数量、账户等字段。
- 不是数据库或网页服务：只有文件和 git，历史由 git 保存。

## 测试

```bash
python3 -m unittest discover -s tools
```
