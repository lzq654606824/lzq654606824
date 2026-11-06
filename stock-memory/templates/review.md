---
# 交易复盘模板。推荐用 `python3 tools/memory.py new review --title "..."` 生成；
# 手工写时复制到 reviews/<年>/<日期>-<短标题>.md，替换下面的占位值。字段含义见 SCHEMA.md。
# date 填平仓日；还没平仓就填复盘当天，result 写 open。
id: R-YYYYMMDD-HHMM
type: review
title: ""
date: YYYY-MM-DD
created: YYYY-MM-DDTHH:MM:SS+08:00
symbols: []
tags: []
source: self
source_ref:
related: []
direction:
opened: YYYY-MM-DD
closed:
result:
pnl_pct:
---

## 当时的理由

<!-- 为什么进场，依据是什么；如果来自某条线索，把线索 id 写进 related -->

## 执行过程

<!-- 计划与实际执行的差别 -->

## 结果

<!-- 发生了什么；框架不设金额、持仓数量字段 -->

## 做对了什么

## 做错了什么

## 下次怎么做

<!-- 提炼成一两条可以复用的规则 -->
