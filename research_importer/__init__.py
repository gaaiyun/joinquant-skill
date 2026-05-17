"""
research_importer — 把券商研报 PDF / 文本变成聚宽可跑的策略代码。

Pipeline
--------

```
                    +---------- akshare 源（公开研报）
   PDF / TXT  ─────►| extractor.pdf / extractor.text
                    +---------- 用户本地 PDF
        │
        ▼  原始文本
+--------------------+
| parser.llm_factor  | ──► ExtractedFactor[]
| parser.llm_strategy| ──► ExtractedStrategy（含 factors / universe / 调仓 / 风控）
+--------------------+
        │
        ▼
+--------------------+
| generator.factor   | ──► factors/<category>/<name>.py
| generator.strategy | ──► strategies/<name>/strategy.py + _meta.yaml
+--------------------+
        │
        ▼
   scripts.strategy_lint (复用) → 自动校验生成代码

```

合规说明
--------
本仓库**不内置任何券商研报 PDF**。用户必须：
- 自己拥有合法获取的 PDF 副本，**或**
- 通过 akshare 等公开渠道拉公开研报

详见 [`disclaimer.md`](./disclaimer.md)。
"""
from __future__ import annotations

from research_importer.parser.schema import ExtractedFactor, ExtractedStrategy  # noqa: F401
