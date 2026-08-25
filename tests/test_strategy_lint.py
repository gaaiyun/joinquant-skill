"""Tests for scripts/strategy_lint.py."""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from scripts.strategy_lint import lint_file, KNOWN_HALLUCINATIONS


def test_lint_passes_clean_template(tmp_path: Path) -> None:
    """Real production template should pass lint."""
    template = PROJECT_ROOT / 'templates' / '01-basic-single-stock.py'
    assert template.exists(), 'template missing'
    report = lint_file(template)
    assert report.passed, f'Template should pass lint, got errors: {report.errors}'
    assert len(report.errors) == 0


def test_lint_catches_hallucinated_api(tmp_path: Path) -> None:
    """Calls to known-hallucinated APIs should be flagged as errors."""
    bad = tmp_path / 'bad.py'
    bad.write_text('''
import jqdata

def initialize(context):
    set_initial_cash(100000)
    set_benchmark('000300.XSHG')

def market_open(context):
    df = get_stock_data('000001.XSHE', days=20)
    cash = get_account_balance()
    place_order('000001.XSHE', 100)
''', encoding='utf-8')

    report = lint_file(bad)
    assert not report.passed
    error_codes = {i.code for i in report.errors}
    assert 'JQ001' in error_codes  # 至少抓到 hallucination
    error_messages = ' '.join(i.message for i in report.errors)
    assert 'set_initial_cash' in error_messages
    assert 'get_stock_data' in error_messages
    assert 'place_order' in error_messages


def test_lint_catches_order_in_before_trading_start(tmp_path: Path) -> None:
    """JQ004: 在 before_trading_start 中下单应该被抓到。"""
    bad = tmp_path / 'bad.py'
    bad.write_text('''
def initialize(context):
    set_benchmark('000300.XSHG')

def before_trading_start(context):
    order('000001.XSHE', 1000)
''', encoding='utf-8')
    report = lint_file(bad)
    error_codes = {i.code for i in report.errors}
    assert 'JQ004' in error_codes


def test_lint_warns_missing_use_real_price(tmp_path: Path) -> None:
    """JQ010: 没有 use_real_price 应该是 warning。"""
    bad = tmp_path / 'incomplete.py'
    bad.write_text('''
def initialize(context):
    set_benchmark('000300.XSHG')
    set_order_cost(OrderCost(open_tax=0, close_tax=0.001,
                              open_commission=0.0003, close_commission=0.0003,
                              close_today_commission=0, min_commission=5),
                   type='stock')
    set_slippage(FixedSlippage(0.02))
''', encoding='utf-8')
    report = lint_file(bad)
    warning_codes = {i.code for i in report.warnings}
    assert 'JQ010' in warning_codes


def test_lint_warns_missing_order_cost(tmp_path: Path) -> None:
    """JQ011: 没有 set_order_cost 应该是 warning。"""
    bad = tmp_path / 'incomplete.py'
    bad.write_text('''
def initialize(context):
    set_benchmark('000300.XSHG')
    set_option('use_real_price', True)
    set_slippage(FixedSlippage(0.02))
''', encoding='utf-8')
    report = lint_file(bad)
    warning_codes = {i.code for i in report.warnings}
    assert 'JQ011' in warning_codes


def test_lint_warns_hardcoded_future_get_price_dates(tmp_path: Path) -> None:
    """JQ003: get_price 里硬编码未来日期应被标成未来函数风险。"""
    bad = tmp_path / 'future_date.py'
    bad.write_text('''
def initialize(context):
    set_benchmark('000300.XSHG')
    set_option('use_real_price', True)
    set_order_cost(OrderCost(open_tax=0, close_tax=0.001,
                              open_commission=0.0003, close_commission=0.0003,
                              close_today_commission=0, min_commission=5),
                   type='stock')
    set_slippage(FixedSlippage(0.02))

def market_open(context):
    get_price('000001.XSHE', start_date='2099-01-01', end_date='2099-12-31')
''', encoding='utf-8')
    report = lint_file(bad)
    warnings = [(i.code, i.message) for i in report.warnings]
    assert any(code == 'JQ003' and '2099' in message for code, message in warnings)


def test_lint_warns_hardcoded_historical_get_price_dates(tmp_path: Path) -> None:
    """历史回测中，早于电脑当天的固定日期也可能位于回测时点之后。"""
    bad = tmp_path / 'historical_fixed_date.py'
    bad.write_text('''
def initialize(context):
    set_benchmark('000300.XSHG')
    set_option('use_real_price', True)
    set_order_cost(OrderCost(open_tax=0, close_tax=0.001,
                              open_commission=0.0003, close_commission=0.0003,
                              close_today_commission=0, min_commission=5),
                   type='stock')
    set_slippage(FixedSlippage(0.02))

def market_open(context):
    get_price('000001.XSHE', end_date='2020-12-31', count=20)
''', encoding='utf-8')
    report = lint_file(bad)
    warnings = [(i.code, i.message) for i in report.warnings]
    assert any(code == 'JQ003' and '2020-12-31' in message for code, message in warnings)


def test_lint_warns_module_level_strategy_state(tmp_path: Path) -> None:
    """JQ006: 策略状态应放到 g.*，不要用模块级变量。"""
    bad = tmp_path / 'global_state.py'
    bad.write_text('''
HOLDINGS = []
threshold = 0.8
MAX_HOLD = 10

def initialize(context):
    set_benchmark('000300.XSHG')
    set_option('use_real_price', True)
    set_order_cost(OrderCost(open_tax=0, close_tax=0.001,
                              open_commission=0.0003, close_commission=0.0003,
                              close_today_commission=0, min_commission=5),
                   type='stock')
    set_slippage(FixedSlippage(0.02))
''', encoding='utf-8')
    report = lint_file(bad)
    jq006 = [i for i in report.warnings if i.code == 'JQ006']
    assert len(jq006) == 2
    assert 'HOLDINGS' in ' '.join(i.message for i in jq006)
    assert 'threshold' in ' '.join(i.message for i in jq006)
    assert 'MAX_HOLD' not in ' '.join(i.message for i in jq006)


def test_lint_detects_deprecated_api(tmp_path: Path) -> None:
    """JQ002: update_universe 已废弃。"""
    bad = tmp_path / 'deprecated.py'
    bad.write_text('''
def initialize(context):
    set_benchmark('000300.XSHG')

def market_open(context):
    update_universe(['000001.XSHE'])
''', encoding='utf-8')
    report = lint_file(bad)
    warning_codes = {i.code for i in report.warnings}
    assert 'JQ002' in warning_codes


def test_lint_handles_syntax_error(tmp_path: Path) -> None:
    """语法错误应该报告但不崩溃。"""
    bad = tmp_path / 'broken.py'
    bad.write_text('def initialize(context):\n    set_benchmark(\n', encoding='utf-8')
    report = lint_file(bad)
    assert not report.passed
    assert any(i.code == 'JQ000' for i in report.errors)


@pytest.mark.parametrize('hallu,fix_keyword', [
    ('get_stock_data', 'get_price'),
    ('get_history_data', 'history'),
    ('get_realtime_quote', 'get_current_data'),
    ('get_account_balance', 'available_cash'),
    ('place_order', 'order'),
])
def test_lint_fix_hint_for_hallucinations(tmp_path: Path, hallu: str, fix_keyword: str) -> None:
    """Fix hint should suggest the correct API."""
    bad = tmp_path / 'h.py'
    bad.write_text(f'def m(context):\n    {hallu}()\n', encoding='utf-8')
    report = lint_file(bad)
    assert any(fix_keyword in i.fix_hint for i in report.errors), \
        f'No fix hint with {fix_keyword} found for {hallu}'


def test_known_hallucinations_set_is_complete() -> None:
    """At least these well-known hallucinations should be in the blacklist."""
    must_have = {
        'get_stock_data', 'get_history_data', 'get_realtime_quote',
        'get_account_balance', 'place_order', 'submit_order', 'set_initial_cash',
    }
    missing = must_have - KNOWN_HALLUCINATIONS
    assert not missing, f'Missing in blacklist: {missing}'
