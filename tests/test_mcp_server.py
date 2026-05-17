"""mcp/server.py 测试 — 直接调 *_impl 函数（绕过 MCP 框架）。

这样 CI 不需要装 mcp 包也能跑测试。
"""
from __future__ import annotations

import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

import pytest

from mcp.server import (
    extract_factors_from_research_impl,
    get_factor_impl,
    lint_strategy_impl,
    list_factors_impl,
    scaffold_strategy_impl,
    search_api_impl,
)


def test_list_factors_no_filter():
    out = list_factors_impl()
    assert len(out) >= 9
    assert all("name" in f for f in out)


def test_list_factors_filter_by_category():
    out = list_factors_impl(category="value")
    assert all(f["category"] == "value" for f in out)
    assert len(out) >= 1


def test_list_factors_filter_by_keyword():
    out = list_factors_impl(keyword="PE")
    assert len(out) >= 1


def test_get_factor_returns_meta_and_source():
    out = get_factor_impl("pe_ttm_inverse")
    assert out["meta"]["name"] == "pe_ttm_inverse"
    assert out["meta"]["category"] == "value"
    assert "def compute_jq" in out["compute_jq_source"]


def test_get_factor_unknown_raises():
    with pytest.raises(KeyError):
        get_factor_impl("nope_factor")


def test_lint_strategy_passes_on_clean_code():
    code = '''
from jqdata import *

def initialize(context):
    set_benchmark("000300.XSHG")
    set_option("use_real_price", True)
    set_order_cost(OrderCost(close_tax=0.001, open_commission=0.0003,
                             close_commission=0.0003, min_commission=5), type="stock")
    set_slippage(FixedSlippage(0.002), type="stock")

def handle_data(context, data):
    pass
'''
    out = lint_strategy_impl(code)
    assert out["passed"], out


def test_lint_strategy_catches_hallucination():
    code = '''
def initialize(context):
    set_initial_cash(100000)   # 不存在的 API

def handle_data(context, data):
    place_order("000001.XSHE", 100)   # 不存在的 API
'''
    out = lint_strategy_impl(code)
    codes = {i["code"] for i in out["issues"]}
    assert "JQ001" in codes


def test_search_api_returns_results_for_existing_func():
    hits = search_api_impl("get_price", context=2)
    assert len(hits) >= 1
    assert "match" in hits[0]


def test_search_api_no_results_for_nonsense():
    hits = search_api_impl("xyzzyplugh_no_match", context=2)
    assert hits == []


def test_extract_factors_returns_prompts():
    out = extract_factors_from_research_impl("一些研报文字", source_hint="测试")
    assert "system_prompt" in out
    assert "user_prompt" in out
    assert "测试" in out["user_prompt"]


def test_scaffold_strategy_runs():
    """scaffold 子进程能跑出来。"""
    out = scaffold_strategy_impl("basic", security="000300.XSHG", hold_num=1)
    # subprocess 返回 0 即可
    assert out["returncode"] == 0
    assert "def initialize" in out["code"]
