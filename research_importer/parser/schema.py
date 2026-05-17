"""
research_importer/parser/schema.py — LLM 抽取结果的结构化定义。

为什么用 dataclass 而不是 Pydantic？
本仓库的 zero-dependency 原则——只用标准库 + （可选）jq* / akshare。
Pydantic 是好东西但属于"非必要依赖"。如果未来要做 FastAPI / 严格运行时
校验，可以一行 import + 子类化转 Pydantic。
"""
from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from typing import Literal, Optional


Category = Literal[
    "value", "momentum", "quality", "growth",
    "volatility", "size", "reversal", "liquidity",
    "sentiment", "alternative",
]


RebalanceFreq = Literal["daily", "weekly", "monthly", "quarterly", "ad_hoc"]


@dataclass
class ExtractedFactor:
    """从研报里抽出来的"一个因子"。"""

    name: str                        # snake_case，全局唯一（agent 后续可去重）
    chinese_name: str
    category: Category
    definition: str                  # 自然语言定义（≤ 200 字）
    formula: Optional[str] = None    # 数学公式（如有）
    weight: Optional[float] = None   # 在多因子合成中的权重
    direction: Literal["ascending", "descending"] = "ascending"
    paper_excerpts: list[str] = field(default_factory=list)   # 原文片段（审计追溯用）
    jq_dependencies_guess: list[str] = field(default_factory=list)
    """LLM 推测在聚宽里需要哪些数据，如 ['valuation.pe_ratio']。"""


@dataclass
class ExtractedStrategy:
    """完整策略框架（一份研报通常对应一个）。"""

    title: str
    source: str                      # "中信证券《xxx》2024-09"
    rebalance_freq: RebalanceFreq
    universe: str                    # "中证 800" / "沪深 300" / "全 A 剔除 ST" 等
    primary_factors: list[ExtractedFactor]
    secondary_factors: list[ExtractedFactor] = field(default_factory=list)
    """次要因子（如有），不参与排序但用作过滤 / 增强。"""

    benchmark: Optional[str] = None
    fee_rate: Optional[float] = None
    slippage: Optional[float] = None
    risk_constraints: list[str] = field(default_factory=list)
    """如 "单股权重 ≤ 5%", "行业暴露 ≤ 1σ"。"""
    paper_excerpts: list[str] = field(default_factory=list)

    # 元数据
    extracted_at: Optional[str] = None      # ISO 时间戳
    llm_model: Optional[str] = None         # 抽取用的模型名
    confidence: Optional[float] = None      # LLM 自评 0~1

    def to_dict(self) -> dict:
        return asdict(self)

    def to_json(self, indent: int = 2) -> str:
        return json.dumps(self.to_dict(), ensure_ascii=False, indent=indent)

    @classmethod
    def from_json(cls, payload: str) -> "ExtractedStrategy":
        return cls.from_dict(json.loads(payload))

    @classmethod
    def from_dict(cls, d: dict) -> "ExtractedStrategy":
        primary = [ExtractedFactor(**f) for f in d.get("primary_factors", [])]
        secondary = [ExtractedFactor(**f) for f in d.get("secondary_factors", [])]
        meta = {k: v for k, v in d.items() if k not in {"primary_factors", "secondary_factors"}}
        return cls(primary_factors=primary, secondary_factors=secondary, **meta)
