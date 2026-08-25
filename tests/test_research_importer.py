"""research_importer/ 测试 — schema / prompts / generator。"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from research_importer.parser.schema import ExtractedFactor, ExtractedStrategy
from research_importer.parser.prompts import build_extract_prompt, build_review_prompt
from research_importer.generator.strategy_code import build_strategy_code, write_strategy
from research_importer.extractor.pdf import clean_text


# ---------------------------------------------------------------------------
# Schema
# ---------------------------------------------------------------------------

def _sample_strategy() -> ExtractedStrategy:
    return ExtractedStrategy(
        title="测试多因子",
        source="测试券商 2024-06",
        rebalance_freq="monthly",
        universe="中证 800",
        primary_factors=[
            ExtractedFactor(
                name="roe_ttm", chinese_name="TTM ROE", category="quality",
                definition="净利润 / 净资产", direction="ascending", weight=0.5,
                paper_excerpts=["质量端使用 ROE"],
            ),
            ExtractedFactor(
                name="ret_12m_skip_1m", chinese_name="12 月动量", category="momentum",
                definition="过去 12 月剔近 1 月累计收益", direction="ascending", weight=0.5,
            ),
        ],
        benchmark="000906.XSHG",
        risk_constraints=["单股 ≤ 5%"],
    )


def test_schema_json_roundtrip():
    s = _sample_strategy()
    payload = s.to_json()
    parsed = ExtractedStrategy.from_json(payload)
    assert parsed.title == s.title
    assert len(parsed.primary_factors) == 2
    assert parsed.primary_factors[0].name == "roe_ttm"
    assert parsed.primary_factors[0].category == "quality"


def test_schema_from_dict_partial():
    """允许部分字段缺失。"""
    d = {
        "title": "x", "source": "y", "rebalance_freq": "monthly",
        "universe": "中证 800", "primary_factors": [],
    }
    s = ExtractedStrategy.from_dict(d)
    assert s.title == "x"
    assert s.primary_factors == []
    assert s.secondary_factors == []


# ---------------------------------------------------------------------------
# Prompts
# ---------------------------------------------------------------------------

def test_extract_prompt_contains_text():
    sys_p, user_p = build_extract_prompt("研报正文 XXX", source_hint="某证券 2024")
    assert "研报正文 XXX" in user_p
    assert "某证券 2024" in user_p
    assert "primary_factors" in sys_p  # schema 字段在 system prompt 里被提到


def test_extract_prompt_includes_fewshot():
    _, user_p = build_extract_prompt("text")
    # few-shot 例子里出现的标志性字段
    assert "ret_12m_skip_1m" in user_p
    assert "roe_ttm" in user_p


def test_review_prompt_takes_json():
    s = _sample_strategy()
    sys_p, user_p = build_review_prompt(s.to_json())
    assert s.title in user_p
    assert "issues" in sys_p.lower()


# ---------------------------------------------------------------------------
# Generator
# ---------------------------------------------------------------------------

def test_build_strategy_code_compiles():
    """生成的代码至少 Python 语法 OK（ast.parse 不报错）。"""
    import ast
    s = _sample_strategy()
    code = build_strategy_code(s, hold_num=20)
    ast.parse(code)   # 不抛 SyntaxError
    assert "def initialize" in code
    assert "def rebalance" in code
    assert "roe_ttm" in code
    assert "ret_12m_skip_1m" in code


def test_build_strategy_code_passes_lint():
    """生成的代码应通过我们自己的 strategy_lint（除了 placeholder 类的 JQ005）。"""
    import tempfile
    from scripts.strategy_lint import lint_file

    s = _sample_strategy()
    code = build_strategy_code(s)
    with tempfile.NamedTemporaryFile(mode="w", suffix=".py", delete=False, encoding="utf-8") as f:
        f.write(code)
        tmp = Path(f.name)
    try:
        report = lint_file(tmp, strict=False)
        # 不要求 0 warning（缺 use_real_price 不会触发因为我们生成了 set_option('use_real_price', True)）
        # 但绝对不能有 error
        assert report.passed, [i.code + ":" + i.message for i in report.errors]
    finally:
        tmp.unlink()


def test_build_strategy_code_sets_use_real_price():
    s = _sample_strategy()
    code = build_strategy_code(s)
    assert "set_option('use_real_price', True)" in code


def test_build_strategy_code_uses_target_value_rebalancing():
    """生成策略必须对所有目标持仓做目标市值再平衡。"""
    s = _sample_strategy()
    code = build_strategy_code(s)
    assert "order_target_value(s, target_value)" in code
    assert "order_value(s, cash_per_stock)" not in code


def test_schedule_snippets_use_documented_joinquant_time_format():
    """调度时间应使用项目文档/模板里的 HH:MM 或语义时间格式。"""
    for freq in ("daily", "weekly", "monthly", "quarterly", "ad_hoc"):
        s = _sample_strategy()
        s.rebalance_freq = freq
        code = build_strategy_code(s)
        assert "time='09:31'" in code
        assert "time='0930'" not in code


def test_build_strategy_code_uses_manual_ret_5d_without_zero_placeholder():
    """已知非 native 因子 ret_5d 应生成真实手算逻辑，不能静默全 0。"""
    s = ExtractedStrategy(
        title="短反测试",
        source="ut",
        rebalance_freq="weekly",
        universe="中证 800",
        primary_factors=[
            ExtractedFactor(
                name="ret_5d",
                chinese_name="5 日收益",
                category="reversal",
                definition="过去 5 个交易日累计收益",
                direction="descending",
                weight=1.0,
            ),
        ],
    )
    code = build_strategy_code(s)
    assert "get_price(" in code
    assert "count=6" in code
    assert "df['ret_5d'] = pd.Series(0.0" not in code
    assert "TODO: replace" not in code


def test_build_strategy_code_rejects_unknown_non_native_factor():
    """未知手算因子默认失败，避免输出看似可用但全 0 的策略。"""
    s = ExtractedStrategy(
        title="未知因子",
        source="ut",
        rebalance_freq="monthly",
        universe="中证 800",
        primary_factors=[
            ExtractedFactor(
                name="custom_alpha_999",
                chinese_name="未知 alpha",
                category="alternative",
                definition="没有实现的因子",
                direction="ascending",
                weight=1.0,
            ),
        ],
    )
    with pytest.raises(ValueError, match="custom_alpha_999"):
        build_strategy_code(s)


def test_generated_strategy_mock_runtime_rebalances_target_values(monkeypatch):
    """codegen -> fake JoinQuant runtime：确认卖出非目标并按目标市值调仓。"""
    import sys
    import types
    from types import SimpleNamespace

    import pandas as pd

    orders: list[tuple[str, str, float]] = []
    scheduled: list[tuple[str, str, str]] = []

    jqdata = types.ModuleType("jqdata")
    jqdata.g = SimpleNamespace()
    jqdata.log = SimpleNamespace(warn=lambda *args, **kwargs: None)
    jqdata.OrderCost = lambda **kwargs: ("OrderCost", kwargs)
    jqdata.FixedSlippage = lambda value: ("FixedSlippage", value)
    jqdata.set_benchmark = lambda benchmark: None
    jqdata.set_option = lambda *args, **kwargs: None
    jqdata.set_order_cost = lambda *args, **kwargs: None
    jqdata.set_slippage = lambda *args, **kwargs: None
    jqdata.run_monthly = lambda func, monthday, time: scheduled.append(("monthly", func.__name__, time))
    jqdata.run_weekly = lambda func, weekday, time: scheduled.append(("weekly", func.__name__, time))
    jqdata.run_daily = lambda func, time: scheduled.append(("daily", func.__name__, time))
    jqdata.get_index_stocks = lambda code: ["000001.XSHE", "000002.XSHE", "000003.XSHE"]
    jqdata.get_current_data = lambda: {
        s: SimpleNamespace(is_st=False, paused=False)
        for s in ["000001.XSHE", "000002.XSHE", "000003.XSHE"]
    }
    jqdata.order_target = lambda security, amount: orders.append(("order_target", security, amount))
    jqdata.order_target_value = (
        lambda security, value: orders.append(("order_target_value", security, value))
    )
    jqdata.__all__ = [
        "g", "log", "OrderCost", "FixedSlippage", "set_benchmark", "set_option",
        "set_order_cost", "set_slippage", "run_monthly", "run_weekly", "run_daily",
        "get_index_stocks", "get_current_data", "order_target", "order_target_value",
    ]

    jqfactor = types.ModuleType("jqfactor")
    jqfactor.get_factor_values = lambda securities, factors, end_date, count: {
        "ROE_TTM": pd.DataFrame(
            [[3.0, 2.0, 1.0]],
            columns=["000001.XSHE", "000002.XSHE", "000003.XSHE"],
        )
    }

    monkeypatch.setitem(sys.modules, "jqdata", jqdata)
    monkeypatch.setitem(sys.modules, "jqfactor", jqfactor)

    strategy = ExtractedStrategy(
        title="mock runtime",
        source="ut",
        rebalance_freq="monthly",
        universe="中证 800",
        primary_factors=[
            ExtractedFactor(
                name="roe_ttm",
                chinese_name="ROE",
                category="quality",
                definition="x",
                direction="ascending",
                weight=1.0,
            ),
        ],
    )
    code = build_strategy_code(strategy, hold_num=2)
    namespace: dict[str, object] = {}
    exec(code, namespace)

    context = SimpleNamespace(
        previous_date="2024-12-31",
        portfolio=SimpleNamespace(
            positions={"000001.XSHE": object(), "000003.XSHE": object()},
            total_value=100000.0,
            available_cash=50000.0,
        ),
    )
    namespace["initialize"](context)
    namespace["rebalance"](context)

    assert ("monthly", "rebalance", "09:31") in scheduled
    assert ("order_target", "000003.XSHE", 0) in orders
    assert ("order_target_value", "000001.XSHE", 50000.0) in orders
    assert ("order_target_value", "000002.XSHE", 50000.0) in orders


def test_write_strategy_creates_files(tmp_path: Path):
    s = _sample_strategy()
    out = write_strategy(s, tmp_path / "test_strat")
    assert out.exists()
    assert out.name == "strategy.py"
    assert (tmp_path / "test_strat" / "_meta.yaml").exists()
    meta = (tmp_path / "test_strat" / "_meta.yaml").read_text(encoding="utf-8")
    assert "roe_ttm" in meta


# ---------------------------------------------------------------------------
# Extractor (clean_text only — PDF extraction needs real PDF or libs)
# ---------------------------------------------------------------------------

def test_clean_text_strips_pagination():
    raw = "正文行 1\n第 1 页 共 30 页\n正文行 2\n第 2 页 共 30 页\n正文行 3"
    out = clean_text(raw)
    assert "第 1 页" not in out
    assert "正文行 1" in out
    assert "正文行 3" in out


def test_clean_text_collapses_blank_lines():
    raw = "a\n\n\n\n\nb"
    out = clean_text(raw)
    assert "\n\n\n" not in out
