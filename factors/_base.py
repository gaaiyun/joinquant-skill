"""
factors/_base.py — 因子元数据与注册基础设施。

因子在本仓库的角色是「**给 AI agent 提供"能直接复制到聚宽编辑器跑"的代码 + 严格的元数据**」。

注意：本模块不在聚宽云上跑（聚宽不允许 import 子目录文件），它的作用是给：

1. Cursor / Claude Code 通过 SKILL.md 检索因子时拿到元数据
2. `factor_lab/` 在本地（jqdatasdk + akshare）做单因子分析时调用
3. `research_importer/` 生成新因子代码时填充模板

每个因子文件应当导出：

- `META`：本模块的 `FactorMeta` 实例
- `compute_jq(date, universe) -> pd.Series`：可粘贴到聚宽编辑器跑
- `compute_local(date, universe) -> pd.Series` [可选]：本地 jqdatasdk 实现
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Callable, Literal, Optional


Category = Literal[
    "value", "momentum", "quality", "growth",
    "volatility", "size", "reversal", "liquidity",
    "sentiment", "alternative",
]

Direction = Literal["ascending", "descending"]


@dataclass(frozen=True)
class FactorMeta:
    """
    单个因子的元数据。

    Attributes
    ----------
    name : str
        简短英文名，同时是 registry key，必须全局唯一。
    chinese_name : str
        显示给用户看的中文名。
    category : Category
        Barra 风格 7 大类之一（外加 sentiment / alternative）。
    description : str
        2-5 句话解释经济直觉。
    paper_refs : list[str]
        学术 / 研报出处。允许"中信证券《选股因子系列》2021" 这种非论文引用。
    direction : Direction
        因子值越高 → 预期收益越高 (ascending) 还是越低 (descending)。
    jq_dependencies : list[str]
        聚宽 API 依赖，如 ["valuation.pe_ratio", "income.np_parent_company_owners"]。
        给 agent 看：知道这个因子需要拉哪些数据。
    recommended_neutralization : list[str]
        推荐做中性化处理的维度，如 ["market_cap", "industry"]。
    universe_hint : str
        建议适用的股票池，如 "中证 800" / "全 A".
    known_issues : list[str]
        已知问题或局限，用大白话讲。
    """

    name: str
    chinese_name: str
    category: Category
    description: str
    paper_refs: tuple[str, ...]
    direction: Direction
    jq_dependencies: tuple[str, ...] = ()
    recommended_neutralization: tuple[str, ...] = ()
    universe_hint: str = "中证 800"
    known_issues: tuple[str, ...] = ()


@dataclass
class FactorEntry:
    """注册表中的一个条目：meta + compute 函数引用。"""

    meta: FactorMeta
    compute_jq: Optional[Callable] = None
    compute_local: Optional[Callable] = None
    module: str = ""             # 来源模块，给 importlib / introspection 用


# ---------------------------------------------------------------------------
# 全局注册表（factor name → FactorEntry）
# ---------------------------------------------------------------------------

_REGISTRY: dict[str, FactorEntry] = {}


def register(entry: FactorEntry) -> None:
    """注册一个因子。重复 name 直接 raise（不允许悄悄覆盖）。"""
    if entry.meta.name in _REGISTRY:
        raise ValueError(
            f"重复注册因子: {entry.meta.name}（已在 {_REGISTRY[entry.meta.name].module}）"
        )
    _REGISTRY[entry.meta.name] = entry


def get(name: str) -> FactorEntry:
    if name not in _REGISTRY:
        raise KeyError(f"未注册的因子: {name}（已注册: {sorted(_REGISTRY)}）")
    return _REGISTRY[name]


def all_factors() -> list[FactorEntry]:
    return list(_REGISTRY.values())


def by_category(category: Category) -> list[FactorEntry]:
    return [e for e in _REGISTRY.values() if e.meta.category == category]


def search(keyword: str) -> list[FactorEntry]:
    """按 name / chinese_name / description / paper_refs 做模糊匹配。"""
    kw = keyword.lower()
    out = []
    for e in _REGISTRY.values():
        haystack = " ".join([
            e.meta.name,
            e.meta.chinese_name,
            e.meta.description,
            *e.meta.paper_refs,
        ]).lower()
        if kw in haystack:
            out.append(e)
    return out


def reset_registry() -> None:
    """仅用于测试。"""
    _REGISTRY.clear()
