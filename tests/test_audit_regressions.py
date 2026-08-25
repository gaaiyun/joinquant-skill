"""审计报告里建议的回归测试集。

来源：
- `.review_workspace/audit_jq_api_and_math.md`
- `.review_workspace/audit_tests_and_engineering.md`

每条测试都直接对应 audit 报告里的一个 finding，文件命名为
`test_audit_regressions.py` 以方便日后维护时回溯。
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))


# ---------------------------------------------------------------------------
# Agent A finding #1：log_market_cap 名字与聚宽 SIZE 实际语义不符 → META 修正
# ---------------------------------------------------------------------------


def test_log_market_cap_meta_warns_about_size_being_standardized():
    """log_market_cap 的 description / known_issues 必须明确说聚宽 SIZE 已标准化。"""
    import factors
    entry = factors.get("log_market_cap")
    text = entry.meta.description + " ".join(entry.meta.known_issues)
    # 必须含「z-score」「标准化」或「standardized」等关键词
    assert any(kw in text for kw in ("z-score", "标准化", "standardized")), (
        f"log_market_cap META 应当声明聚宽 SIZE 是标准化值，实际：{text!r}"
    )


# ---------------------------------------------------------------------------
# Agent A finding #2：ret_5d 样本不足时返回全 NaN（不是空 Series）
# ---------------------------------------------------------------------------


def test_ret_5d_returns_nan_series_when_data_short():
    """ret_5d 在 close_panel < 6 行时应返回与 universe 对齐的全 NaN Series。"""
    import pandas as pd
    from factors.reversal.ret_5d import _ret_5d_from_close_panel

    universe = ["000001.XSHE", "600000.XSHG"]
    # 给一个只有 3 行的空 panel，触发 < 6 的分支
    short_panel = pd.DataFrame(
        index=pd.date_range("2024-01-01", periods=3, freq="B"),
        columns=universe,
        data=1.0,
    )
    result = _ret_5d_from_close_panel(short_panel, universe)
    assert isinstance(result, pd.Series)
    assert list(result.index) == universe
    assert result.isna().all(), "应当全部为 NaN（让上游能感知缺失）"


def test_ret_5d_normal_path_computes_correct_returns():
    import pandas as pd
    from factors.reversal.ret_5d import _ret_5d_from_close_panel

    universe = ["A", "B"]
    panel = pd.DataFrame(
        index=pd.date_range("2024-01-01", periods=6, freq="B"),
        columns=universe,
        data=[[100, 50], [101, 51], [102, 52], [103, 53], [104, 54], [110, 60]],
    )
    result = _ret_5d_from_close_panel(panel, universe)
    # 5 日累计 = (110 - 100) / 100 = 0.10
    assert result["A"] == pytest.approx(0.10)
    assert result["B"] == pytest.approx(0.20)


# ---------------------------------------------------------------------------
# Agent A finding #3：ic_ir 是日频 IR，新增 annualized_ir 辅助
# ---------------------------------------------------------------------------


def test_ic_report_exposes_annualized_ir():
    """ICReport 应当提供年化 IR 转换，避免 caller 误把日 IR 当年化值。"""
    from factor_lab import compute_ic
    import numpy as np
    import pandas as pd

    rng = np.random.default_rng(0)
    factor = pd.DataFrame(rng.normal(0, 1, (100, 30)),
                          index=pd.date_range("2024-01-01", periods=100, freq="B"),
                          columns=[f"S{i}" for i in range(30)])
    returns = factor * 0.5 + pd.DataFrame(
        rng.normal(0, 1, factor.shape), index=factor.index, columns=factor.columns
    )
    r = compute_ic(factor, returns, forward_periods=1)
    # to_dict 必须包含 ic_ir_annualized
    d = r.to_dict()
    assert "ic_ir_annualized" in d
    # 持有 1 期 → 年化系数 = sqrt(252) ≈ 15.87
    if r.ic_ir and not (r.ic_ir != r.ic_ir):    # 不是 NaN
        ratio = r.annualized_ir() / r.ic_ir
        assert abs(ratio - (252 ** 0.5)) < 1e-6


# ---------------------------------------------------------------------------
# Agent B P1.2：ExtractedStrategy.from_dict 容错（忽略未知 key + 默认填充）
# ---------------------------------------------------------------------------


def test_from_dict_ignores_unknown_keys():
    """LLM 输出常带额外 key（reasoning / metadata），不应导致 TypeError。"""
    from research_importer.parser.schema import ExtractedStrategy
    payload = {
        "title": "x",
        "source": "y",
        "rebalance_freq": "monthly",
        "universe": "中证 800",
        "primary_factors": [],
        # 故意混入 LLM 可能多出的字段
        "reasoning_steps": ["a", "b"],
        "model_used": "claude-sonnet-4",
        "extracted_metadata": {"any": "thing"},
    }
    s = ExtractedStrategy.from_dict(payload)
    assert s.title == "x"
    assert s.source == "y"


def test_from_dict_fills_missing_required_with_defaults():
    """缺必填字段时应填默认而不是 TypeError。"""
    from research_importer.parser.schema import ExtractedStrategy
    s = ExtractedStrategy.from_dict({"primary_factors": []})
    # 必填字段全部走默认
    assert s.title == ""
    assert s.source == ""
    assert s.universe == ""
    assert s.rebalance_freq == "monthly"


def test_from_dict_filters_unknown_factor_fields():
    """primary_factors 里某项含未知字段时也应安全 skip 那个字段。"""
    from research_importer.parser.schema import ExtractedStrategy
    payload = {
        "title": "t", "source": "s", "rebalance_freq": "monthly", "universe": "u",
        "primary_factors": [{
            "name": "roe_ttm", "chinese_name": "x", "category": "quality",
            "definition": "y", "direction": "ascending",
            "llm_confidence_internal": 0.9,    # 多余字段
        }],
    }
    s = ExtractedStrategy.from_dict(payload)
    assert len(s.primary_factors) == 1
    assert s.primary_factors[0].name == "roe_ttm"


# ---------------------------------------------------------------------------
# Agent B P1.3：_make_unique_slug 防 slug 冲突静默丢因子
# ---------------------------------------------------------------------------


def test_build_strategy_code_handles_slug_collisions():
    """两个不可 slug 化的因子名都会落到 'unnamed_factor'，必须自动加序号区分。"""
    from research_importer.parser.schema import ExtractedFactor, ExtractedStrategy
    from research_importer.generator import build_strategy_code

    s = ExtractedStrategy(
        title="x", source="y", rebalance_freq="monthly", universe="中证 800",
        primary_factors=[
            ExtractedFactor(name="!!!", chinese_name="a", category="momentum",
                            definition="x", direction="ascending"),
            ExtractedFactor(name="???", chinese_name="b", category="value",
                            definition="y", direction="ascending"),
            ExtractedFactor(name="🚀", chinese_name="c", category="quality",
                            definition="z", direction="ascending"),
        ],
    )
    code = build_strategy_code(s, allow_placeholders=True)
    # 三个因子都应当出现，第一个 unnamed_factor，后续加 _2 / _3
    assert "'unnamed_factor'" in code
    assert "'unnamed_factor_2'" in code
    assert "'unnamed_factor_3'" in code


# ---------------------------------------------------------------------------
# Agent B P2.1：_resolve_universe_code 应识别有空格 / 无空格两种写法
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("universe,expected", [
    ("中证 800", "000906.XSHG"),
    ("中证 800 剔除 ST 与停牌", "000906.XSHG"),
    ("中证800", "000906.XSHG"),                  # 无空格也要识别
    ("沪深 300", "000300.XSHG"),
    ("沪深300", "000300.XSHG"),
    ("中证 1000", "000852.XSHG"),
    ("中证1000", "000852.XSHG"),
    ("中证 500", "000905.XSHG"),
    ("", "000906.XSHG"),                          # 空 → 默认中证 800
    ("未知股票池", "000906.XSHG"),                # 未知 → 默认
])
def test_resolve_universe_code(universe, expected):
    from research_importer.generator.strategy_code import _resolve_universe_code
    assert _resolve_universe_code(universe) == expected


# ---------------------------------------------------------------------------
# Agent B P2：fetch_via_jqfactor 缺依赖时应抛带提示的 ImportError
# ---------------------------------------------------------------------------


def test_fetch_via_jqfactor_raises_when_both_missing(monkeypatch):
    """jqfactor + jqdatasdk 都没装时，应抛 ImportError 且消息含安装提示。"""
    import sys
    monkeypatch.setitem(sys.modules, "jqfactor", None)
    monkeypatch.setitem(sys.modules, "jqdatasdk", None)
    import factors

    with pytest.raises(ImportError, match=r"jqfactor|jqdatasdk"):
        factors.fetch_via_jqfactor(["000001.XSHE"], ["EP"], "2024-01-01")


# ---------------------------------------------------------------------------
# Agent B P2：MCP server build_server 在 mcp 已装时必须能成功构造
# ---------------------------------------------------------------------------


def test_build_server_works_when_mcp_installed():
    """若 mcp[cli] 已安装，build_server() 必须能构造 FastMCP 实例。"""
    try:
        from mcp.server.fastmcp import FastMCP  # noqa: F401
    except ImportError:
        pytest.skip("mcp[cli] 未安装")

    from jqskill_mcp.server import build_server, SERVER_NAME
    app = build_server()
    assert app is not None
    assert app.name == SERVER_NAME

    # 应当注册了至少 6 个 tool
    import asyncio
    tools = asyncio.run(app.list_tools())
    assert len(tools) >= 6
    names = {t.name for t in tools}
    # 所有工具都用 jq_ 前缀
    assert all(n.startswith("jq_") for n in names), f"工具名缺前缀：{names}"
