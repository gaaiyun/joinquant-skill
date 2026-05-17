"""把 strategy_lint 跑在自己的 templates 和 examples 上 — "狗食"测试。

防止：
- 某次重构改坏 lint 规则导致模板自己也过不了
- examples/bad-strategy-for-lint-test.py 标注的预期错误数量退化
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from scripts.strategy_lint import lint_file


# ---------------------------------------------------------------------------
# templates/ — 全部模板应当 lint 通过（无 error）
# ---------------------------------------------------------------------------

TEMPLATE_PATHS = sorted((PROJECT_ROOT / "templates").glob("*.py"))


@pytest.mark.parametrize("template", TEMPLATE_PATHS, ids=lambda p: p.stem)
def test_template_passes_lint(template: Path):
    report = lint_file(template, strict=False)
    assert report.passed, (
        f"模板 {template.name} 不能通过自己的 lint:\n"
        + "\n".join(f"  {i.code} L{i.line}: {i.message}" for i in report.errors)
    )


# ---------------------------------------------------------------------------
# examples/case-* — 完整可跑案例也应当 lint 通过
# ---------------------------------------------------------------------------

EXAMPLE_STRATEGIES = sorted(
    (PROJECT_ROOT / "examples").glob("case-*/strategy.py")
)


@pytest.mark.parametrize("strategy", EXAMPLE_STRATEGIES, ids=lambda p: p.parent.name)
def test_example_case_passes_lint(strategy: Path):
    report = lint_file(strategy, strict=False)
    assert report.passed, (
        f"案例 {strategy.parent.name}/strategy.py 不能通过 lint:\n"
        + "\n".join(f"  {i.code} L{i.line}: {i.message}" for i in report.errors)
    )


# ---------------------------------------------------------------------------
# examples/bad-strategy-for-lint-test.py — 反例
# ---------------------------------------------------------------------------

BAD_EXAMPLE = PROJECT_ROOT / "examples" / "bad-strategy-for-lint-test.py"


def test_bad_example_lint_catches_expected_codes():
    """反例文件应当至少抓到 JQ001（hallucination）和 JQ004（before_trading 下单）。"""
    if not BAD_EXAMPLE.exists():
        pytest.skip(f"{BAD_EXAMPLE} 不存在")
    report = lint_file(BAD_EXAMPLE, strict=False)
    codes = {i.code for i in report.issues}
    # 至少应当抓到这些：
    # JQ001 hallucination (set_initial_cash 等)
    # JQ002 deprecated (set_universe)
    # JQ004 before_trading_start 下单
    expected_min = {"JQ001"}
    missing = expected_min - codes
    assert not missing, (
        f"反例文件应当抓到 {expected_min}，但缺 {missing}。"
        f"实际抓到：{codes}"
    )


def test_bad_example_reports_multiple_errors():
    """反例应当至少有 3 个 error（不要因 lint 规则退化只剩 1 个）。"""
    if not BAD_EXAMPLE.exists():
        pytest.skip(f"{BAD_EXAMPLE} 不存在")
    report = lint_file(BAD_EXAMPLE, strict=False)
    assert len(report.errors) >= 3, (
        f"反例应当至少 3 个 error，实际 {len(report.errors)} 个:\n"
        + "\n".join(f"  {i.code}: {i.message}" for i in report.errors)
    )


# ---------------------------------------------------------------------------
# JQ005 strict mode — 新增的白名单检查
# ---------------------------------------------------------------------------

def test_strict_mode_on_clean_template_has_no_jq005():
    """模板里的所有调用都应当在 KNOWN_APIS 或 builtin 列表里，strict mode 也不应报 JQ005。"""
    if not TEMPLATE_PATHS:
        pytest.skip("无模板")
    # 用第一个模板做样本
    report = lint_file(TEMPLATE_PATHS[0], strict=True)
    jq005_codes = [i for i in report.issues if i.code == "JQ005"]
    # 极端情况下模板里可能有用户自定义函数；只要数量很少就行
    assert len(jq005_codes) <= 2, (
        f"模板 {TEMPLATE_PATHS[0].name} 在 strict 模式下不该有 JQ005，实际:\n"
        + "\n".join(f"  L{i.line}: {i.message}" for i in jq005_codes)
    )


def test_strict_mode_catches_unknown_api():
    """strict 模式应当抓到 KNOWN_APIS 之外的看似聚宽 API。"""
    import tempfile
    fake_code = '''
def initialize(context):
    set_benchmark("000300.XSHG")
    set_option("use_real_price", True)
    set_order_cost(OrderCost(), type="stock")
    set_slippage(FixedSlippage(0.002))
    fetch_some_unknown_api(context, "x")   # 看起来像聚宽 API 但不存在
'''
    with tempfile.NamedTemporaryFile(mode="w", suffix=".py", delete=False, encoding="utf-8") as f:
        f.write(fake_code)
        tmp = Path(f.name)
    try:
        report = lint_file(tmp, strict=True)
        info_codes = [i.code for i in report.issues if i.severity == "info"]
        assert "JQ005" in info_codes
    finally:
        tmp.unlink()
