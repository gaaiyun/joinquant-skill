"""
research_importer/generator/strategy_code.py — ExtractedStrategy → 聚宽策略 .py。

模板基于 templates/02-multi-factor.py 的样式，按 ExtractedStrategy 的 primary_factors
组合生成。生成完会自动调 scripts.strategy_lint 做一遍 lint。
"""
from __future__ import annotations

import re
from pathlib import Path
from typing import Optional

from research_importer.parser.schema import ExtractedStrategy


_TEMPLATE = '''"""
{title}
{source_line}

【自动生成】由 joinquant-skill/research_importer 从研报抽取生成。
生成前请人工 review 因子定义、universe、调仓频率是否正确再投入回测。

Generated factors: {factor_names}
Native jqfactor mapping: {native_id_table}
"""
from jqdata import *
from jqfactor import get_factor_values
import pandas as pd
import numpy as np


def initialize(context):
    """初始化策略参数。"""
    set_benchmark('{benchmark}')
    set_option('use_real_price', True)
    set_order_cost(OrderCost(
        open_tax=0, close_tax=0.001,
        open_commission=0.0003, close_commission=0.0003,
        close_today_commission=0, min_commission=5,
    ), type='stock')
    set_slippage(FixedSlippage(0.002), type='stock')

    g.hold_num = {hold_num}
    g.factor_weights = {factor_weights}
    g.factor_native_ids = {factor_native_ids}    # 本仓库因子名 → 聚宽 factor id

    # 调仓调度
{schedule}


def _get_universe(context):
    """股票池：{universe}。"""
    stocks = get_index_stocks('{universe_code}')
    current = get_current_data()
    # 过滤 ST、停牌
    stocks = [s for s in stocks if not current[s].is_st and not current[s].paused]
    return stocks


def _compute_factor_scores(context, stocks):
    """从聚宽官方因子库一次拉所有 native 因子；非 native 因子留作 TODO。"""
    df = pd.DataFrame(index=stocks)

    # 一次性拉 native 因子（end_date=context.previous_date 避免未来函数）
    native_pairs = {{k: v for k, v in g.factor_native_ids.items() if v is not None}}
    if native_pairs:
        native_factors = list(set(native_pairs.values()))
        try:
            data = get_factor_values(
                securities=stocks,
                factors=native_factors,
                end_date=context.previous_date,
                count=1,
            )
            for fname, fid in native_pairs.items():
                if fid in data and not data[fid].empty:
                    df[fname] = data[fid].iloc[-1]
        except Exception as exc:
            log.warn('get_factor_values failed: %s' % exc)

{factor_compute_blocks}

    # 标准化每个因子（rank + zscore），按方向调正
    scores = pd.Series(0.0, index=stocks)
    for fname, direction in {factor_directions}.items():
        if fname not in df.columns:
            continue
        col = df[fname].rank(method='average')
        sd = col.std(ddof=1)
        col = (col - col.mean()) / sd if sd > 0 else col * 0
        if direction == 'descending':
            col = -col
        scores = scores + g.factor_weights.get(fname, 0) * col.fillna(0)
    return scores


def rebalance(context):
    """调仓主入口。"""
    stocks = _get_universe(context)
    scores = _compute_factor_scores(context, stocks)
    target = scores.sort_values(ascending=False).head(g.hold_num).index.tolist()

    # 平掉不在目标里的持仓
    for s in list(context.portfolio.positions):
        if s not in target:
            order_target(s, 0)

    # 等权买入
    if target:
        cash_per_stock = context.portfolio.available_cash / len(target)
        for s in target:
            if s not in context.portfolio.positions:
                order_value(s, cash_per_stock)
'''


_SCHEDULE_SNIPPETS = {
    "daily": "    run_daily(rebalance, time='0930')",
    "weekly": "    run_weekly(rebalance, 1, time='0930')",
    "monthly": "    run_monthly(rebalance, 1, time='0930')",
    "quarterly": "    run_monthly(rebalance, 1, time='0930')  # 简化为月调，季度可加日期判断",
    "ad_hoc": "    run_daily(rebalance, time='0930')  # 按需调度，请手动改",
}


_UNIVERSE_MAP = {
    "沪深 300": "000300.XSHG",
    "中证 500": "000905.XSHG",
    "中证 800": "000906.XSHG",
    "中证 1000": "000852.XSHG",
}


_FACTOR_COMPUTE_TEMPLATES = {
    # 给非 native 因子的占位（native 已经在上面一次性 get_factor_values 拉好）
    "non_native_placeholder": (
        "    # 因子 '{name}' 没有聚宽 native id，需要手算\n"
        "    # 参考 factors/<category>/{name}.py 的 compute_jq 函数体\n"
        "    df['{name}'] = pd.Series(0.0, index=stocks)   # TODO: replace"
    ),
}


def _slugify(name: str) -> str:
    return re.sub(r"[^a-z0-9_]+", "_", name.lower()).strip("_")


def _make_unique_slug(slug: str, taken: set[str]) -> str:
    """若 slug 已存在，加 _2 / _3 直到唯一，避免多个因子静默合并。"""
    if slug not in taken:
        return slug
    i = 2
    while f"{slug}_{i}" in taken:
        i += 1
    return f"{slug}_{i}"


def _resolve_universe_code(universe: str) -> str:
    """从 '中证 800 剔除 ST 与停牌' / '中证800' 等字符串识别指数代码。

    用 normalize 后子串匹配，兼容研报里"中证 800" / "中证800" 两种写法。
    """
    if not universe:
        return "000906.XSHG"
    normalized = universe.replace(" ", "").replace("　", "")  # 半角 + 全角空格
    for key, code in _UNIVERSE_MAP.items():
        if key.replace(" ", "") in normalized:
            return code
    return "000906.XSHG"  # 缺省回退到中证 800


def _resolve_native_id(slug: str) -> Optional[str]:
    """查 factors._jq_native.NATIVE_FACTOR_MAP；不引入循环 import，惰性查找。"""
    try:
        from factors._jq_native import NATIVE_FACTOR_MAP  # noqa: WPS433
        return NATIVE_FACTOR_MAP.get(slug)
    except ImportError:
        return None


def build_strategy_code(strategy: ExtractedStrategy, hold_num: int = 20) -> str:
    """从 ExtractedStrategy 生成聚宽策略代码（不写盘）。"""
    universe_code = _resolve_universe_code(strategy.universe or "")
    benchmark = strategy.benchmark or universe_code
    schedule = _SCHEDULE_SNIPPETS.get(strategy.rebalance_freq, _SCHEDULE_SNIPPETS["monthly"])

    weights: dict[str, float] = {}
    directions: dict[str, str] = {}
    native_ids: dict[str, Optional[str]] = {}
    compute_blocks: list[str] = []
    factor_names: list[str] = []

    for f in strategy.primary_factors:
        raw_slug = _slugify(f.name) or "unnamed_factor"
        slug = _make_unique_slug(raw_slug, set(weights))
        weights[slug] = f.weight if f.weight is not None else 1.0
        directions[slug] = f.direction
        native_id = _resolve_native_id(slug)
        native_ids[slug] = native_id
        if native_id is None:
            # 非 native → 加 placeholder
            compute_blocks.append(_FACTOR_COMPUTE_TEMPLATES["non_native_placeholder"].format(name=slug))
        factor_names.append(slug)

    # 归一化权重
    total = sum(abs(w) for w in weights.values()) or 1.0
    weights = {k: round(v / total, 4) for k, v in weights.items()}

    source_line = f"研报来源：{strategy.source}" if strategy.source else ""

    # native_id_table 是给 docstring 的可读字串
    native_id_table = ", ".join(
        f"{k}={v}" if v else f"{k}=<手算>"
        for k, v in native_ids.items()
    )

    return _TEMPLATE.format(
        title=strategy.title or "Auto-generated multi-factor strategy",
        source_line=source_line,
        factor_names=", ".join(factor_names),
        native_id_table=native_id_table,
        benchmark=benchmark,
        hold_num=hold_num,
        factor_weights=repr(weights),
        factor_directions=repr(directions),
        factor_native_ids=repr(native_ids),
        universe=strategy.universe,
        universe_code=universe_code,
        schedule=schedule,
        factor_compute_blocks=("\n".join(compute_blocks) if compute_blocks else "    # 全部因子都是 jqfactor native，无需额外计算"),
    )


def write_strategy(
    strategy: ExtractedStrategy,
    output_dir: str | Path,
    hold_num: int = 20,
) -> Path:
    """生成 strategy.py + _meta.yaml 到 output_dir。"""
    out = Path(output_dir)
    out.mkdir(parents=True, exist_ok=True)

    code = build_strategy_code(strategy, hold_num=hold_num)
    code_path = out / "strategy.py"
    code_path.write_text(code, encoding="utf-8")

    meta_lines = [
        f"title: {strategy.title!r}",
        f"source: {strategy.source!r}",
        f"universe: {strategy.universe!r}",
        f"rebalance_freq: {strategy.rebalance_freq}",
        f"benchmark: {(strategy.benchmark or '')!r}",
        f"primary_factors:",
    ]
    for f in strategy.primary_factors:
        meta_lines.append(f"  - name: {f.name}")
        meta_lines.append(f"    chinese_name: {f.chinese_name!r}")
        meta_lines.append(f"    category: {f.category}")
        meta_lines.append(f"    direction: {f.direction}")
        meta_lines.append(f"    weight: {f.weight}")
    (out / "_meta.yaml").write_text("\n".join(meta_lines) + "\n", encoding="utf-8")

    return code_path
