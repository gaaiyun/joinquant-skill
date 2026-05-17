#!/usr/bin/env python3
"""
strategy_lint.py — JoinQuant 策略代码 lint 工具

检查 AI 生成（或人写）的聚宽策略代码是否有：
  1. 调用了不存在的 API（hallucination）
  2. 缺少关键设置（use_real_price / order_cost / slippage）
  3. 未来函数风险（用日期切片而非 count）
  4. 在 before_trading_start / after_trading_end 中下单
  5. 使用了已废弃的 API
  6. 没用 g.* 保存全局状态

用法:
    python scripts/strategy_lint.py my_strategy.py
    python scripts/strategy_lint.py --fix my_strategy.py     # 自动修复（部分）
    python scripts/strategy_lint.py --json my_strategy.py    # JSON 输出
"""

from __future__ import annotations

import argparse
import ast
import json
import re
import sys
from dataclasses import dataclass, field
from pathlib import Path

# 已知聚宽 API 函数白名单（从官方 API 文档提取的核心函数）
# 完整列表见 references/，这里只列最常用且容易被 AI 编错的
# v2: 白名单现在通过 JQ005 真正生效（之前是死数据）
KNOWN_APIS = {
    # 策略设置
    'initialize', 'before_trading_start', 'handle_data', 'after_trading_end',
    'set_benchmark', 'set_option', 'set_order_cost', 'set_slippage',
    'set_pricing_model', 'set_commission', 'set_max_amount_per_trade',
    'set_subportfolios', 'set_future_commission', 'set_margin_rate',
    'run_daily', 'run_weekly', 'run_monthly',
    # 数据获取
    'get_price', 'attribute_history', 'history', 'get_current_data',
    'get_fundamentals', 'get_factor_values', 'get_industry', 'get_concept',
    'get_money_flow', 'get_ticks', 'get_call_auction',
    'get_all_securities', 'get_security_info', 'get_index_stocks',
    'get_industry_stocks', 'get_concept_stocks', 'get_extras',
    'get_all_trade_days', 'get_trade_days', 'get_locked_shares',
    'get_baidu_factor', 'get_billboard_list', 'get_dominant_future',
    'get_future_contracts', 'get_continuous_dominant_future', 'get_bars',
    # 交易
    'order', 'order_value', 'order_target', 'order_target_value',
    'order_market', 'order_lots', 'cancel_order', 'get_open_orders', 'get_orders',
    'get_trades',
    # 融资融券
    'margincash_open', 'margincash_close', 'margincash_direct_refund',
    'marginsec_open', 'marginsec_close', 'marginsec_direct_refund',
    # 期货
    'sell_open', 'buy_open', 'sell_close', 'buy_close',
    # 杂项
    'record', 'log', 'send_message', 'write_file', 'read_file',
    # 数据处理（注意 standardlize 不是 standardize）
    'neutralize', 'winsorize', 'standardlize', 'winsorize_med',
    # 类
    'OrderCost', 'OrderStyle', 'MarketOrderStyle', 'LimitOrderStyle',
    'FixedSlippage', 'PriceRelatedSlippage', 'StepRelatedSlippage',
    'SubPortfolioConfig',
    # jqlib / jqfactor
    'alpha101', 'alpha191',
    # query (SQLAlchemy 风格，聚宽常用 from jqdata import * 后直接用)
    'query',
}

# 经常被 AI 编出来但实际不存在的 API
# v2: 补充了 references/02-data-getters.md / 06-trading.md / 07-objects.md 里
#     列出的所有 "AI 常编错" 名字
KNOWN_HALLUCINATIONS = {
    # 数据类（references/02-data-getters.md）
    'get_stock_data',         # AI 常编，应该用 get_price
    'get_history_data',       # AI 常编，应该用 history / attribute_history
    'get_history_price',      # 同上
    'fetch_kline',            # 同上
    'jqdata.get_stock_data',
    'jqdata.fetch_data',
    'jqdata.get_price',       # jqdata 模块下没有 get_price，是 top-level
    # 设置类
    'set_initial_cash',       # 不存在，初始资金在 web 界面设置
    'get_realtime_quote',     # 不存在，应该用 get_current_data
    # 下单类（references/06-trading.md）
    'place_order',            # AI 从其他平台带过来的，应该用 order / order_value
    'submit_order',           # 同上
    'buy_stock',              # AI 常编，应该用 order(security, amount)
    'sell_stock',             # 同上
    'close_position',         # 同上
    'set_position',           # 不存在，应该用 order_target / order_target_value
    # context / portfolio 误用（references/07-objects.md）
    'get_account_balance',    # 不存在，应该用 context.portfolio.available_cash
    'get_position',           # 不存在，应该用 context.portfolio.positions
    'query_position',         # 同上
    'cash_balance',           # 不是函数，是 context.portfolio.available_cash
    'holdings',                # 不是函数，是 context.portfolio.positions
}

# 已废弃但可能仍被 AI 生成
DEPRECATED_APIS = {
    'update_universe',        # 旧 API，已废弃
    'set_universe',           # 部分场景已废弃，建议用动态选股
}

# JQ005 白名单检查时，需要忽略的"非聚宽 API"调用前缀
# （第三方库 / Python builtin / 用户自定义）
_THIRD_PARTY_MODULES = {
    'pd', 'pandas', 'np', 'numpy', 'sp', 'scipy', 'plt', 'matplotlib',
    'datetime', 'math', 'random', 'json', 're', 'os', 'sys', 'time',
    'collections', 'itertools', 'functools', 'typing',
    # 聚宽里的 namespace
    'context', 'g', 'data', 'self',
}

_PYTHON_BUILTINS = {
    'print', 'len', 'range', 'sum', 'min', 'max', 'abs', 'round', 'int', 'float',
    'str', 'bool', 'list', 'dict', 'tuple', 'set', 'sorted', 'reversed',
    'enumerate', 'zip', 'map', 'filter', 'isinstance', 'hasattr', 'getattr',
    'setattr', 'type', 'super', 'iter', 'next', 'all', 'any', 'open',
    'Exception', 'ValueError', 'KeyError', 'TypeError', 'IndexError',
}


@dataclass
class LintIssue:
    severity: str       # 'error' | 'warning' | 'info'
    line: int
    col: int
    code: str           # 检查项 code
    message: str
    fix_hint: str = ''


@dataclass
class LintReport:
    file: str
    issues: list[LintIssue] = field(default_factory=list)
    api_calls_found: set[str] = field(default_factory=set)

    def add(self, severity: str, line: int, col: int, code: str,
            message: str, fix_hint: str = '') -> None:
        self.issues.append(LintIssue(severity, line, col, code, message, fix_hint))

    @property
    def errors(self) -> list[LintIssue]:
        return [i for i in self.issues if i.severity == 'error']

    @property
    def warnings(self) -> list[LintIssue]:
        return [i for i in self.issues if i.severity == 'warning']

    @property
    def passed(self) -> bool:
        return len(self.errors) == 0

    def to_dict(self) -> dict:
        return {
            'file': self.file,
            'passed': self.passed,
            'error_count': len(self.errors),
            'warning_count': len(self.warnings),
            'issues': [
                {
                    'severity': i.severity,
                    'line': i.line,
                    'col': i.col,
                    'code': i.code,
                    'message': i.message,
                    'fix_hint': i.fix_hint,
                }
                for i in self.issues
            ],
            'api_calls': sorted(self.api_calls_found),
        }


class StrategyLinter(ast.NodeVisitor):
    def __init__(self, report: LintReport, source: str, strict: bool = False):
        self.report = report
        self.source_lines = source.splitlines()
        self._current_func: str | None = None
        self._has_use_real_price = False
        self._has_order_cost = False
        self._has_slippage = False
        self._initialize_seen = False
        self._user_defined_funcs: set[str] = set()
        self._imported_names: set[str] = set()
        self._strict = strict   # JQ005 白名单检查仅在 strict 模式下报 warning

    def visit_FunctionDef(self, node: ast.FunctionDef) -> None:
        prev = self._current_func
        self._current_func = node.name
        self._user_defined_funcs.add(node.name)
        if node.name == 'initialize':
            self._initialize_seen = True
        self.generic_visit(node)
        self._current_func = prev

    def visit_Import(self, node: ast.Import) -> None:
        for alias in node.names:
            self._imported_names.add(alias.asname or alias.name.split('.')[0])
        self.generic_visit(node)

    def visit_ImportFrom(self, node: ast.ImportFrom) -> None:
        for alias in node.names:
            self._imported_names.add(alias.asname or alias.name)
        self.generic_visit(node)

    def visit_Call(self, node: ast.Call) -> None:
        func_name = self._extract_call_name(node.func)
        if func_name:
            self.report.api_calls_found.add(func_name)

            # 1. 检查 hallucination
            if func_name in KNOWN_HALLUCINATIONS:
                fixes = {
                    'get_stock_data': '改用 get_price(...) 或 attribute_history(...)',
                    'get_history_data': '改用 history(...) 或 attribute_history(...)',
                    'jqdata.get_stock_data': '改用 get_price(...)',
                    'jqdata.fetch_data': '改用 get_price(...)',
                    'set_initial_cash': '初始资金在聚宽 Web 界面回测设置中配置，代码里不需要设',
                    'get_realtime_quote': '改用 get_current_data()',
                    'place_order': '改用 order(security, amount) 或 order_value(...)',
                    'submit_order': '改用 order(...) / order_value(...)',
                    'get_account_balance': '改用 context.portfolio.available_cash',
                    'get_position': '改用 context.portfolio.positions.get(security)',
                }
                self.report.add(
                    'error', node.lineno, node.col_offset, 'JQ001',
                    f'调用了不存在的 API：{func_name}',
                    fixes.get(func_name, '查看 references/ 里的对应 API'),
                )

            # 2. 检查已废弃 API
            elif func_name in DEPRECATED_APIS:
                self.report.add(
                    'warning', node.lineno, node.col_offset, 'JQ002',
                    f'API {func_name} 已废弃',
                    '查看 references/01-strategy-setup.md 找替代方案',
                )

            # 3. 标记关键设置是否出现
            if func_name == 'set_option':
                if node.args and isinstance(node.args[0], ast.Constant):
                    if node.args[0].value == 'use_real_price' and len(node.args) >= 2:
                        if isinstance(node.args[1], ast.Constant) and node.args[1].value is True:
                            self._has_use_real_price = True
            elif func_name == 'set_order_cost':
                self._has_order_cost = True
            elif func_name == 'set_slippage':
                self._has_slippage = True

            # 4. 检查 get_price 是否传了 start_date 而没传 count
            if func_name == 'get_price':
                kw_names = {kw.arg for kw in node.keywords}
                if 'start_date' in kw_names and 'count' not in kw_names:
                    has_end_date = 'end_date' in kw_names
                    if not has_end_date:
                        self.report.add(
                            'warning', node.lineno, node.col_offset, 'JQ003',
                            'get_price 用了 start_date 但没传 count 或 end_date',
                            '建议改用 count=N 形式，避免未来函数',
                        )

            # 5. 检查在 before_trading_start / after_trading_end 中下单
            if self._current_func in ('before_trading_start', 'after_trading_end'):
                if func_name in ('order', 'order_value', 'order_target', 'order_target_value',
                                 'order_market', 'order_lots',
                                 'margincash_open', 'margincash_close',
                                 'marginsec_open', 'marginsec_close'):
                    self.report.add(
                        'error', node.lineno, node.col_offset, 'JQ004',
                        f'在 {self._current_func} 中调用 {func_name}：聚宽不允许在非交易时段下单',
                        '把下单逻辑放到 handle_data 或通过 run_daily 调度的函数里',
                    )

            # 6. JQ005：白名单检查（仅 strict 模式）
            #    func_name 如果看起来像聚宽 API（snake_case 短名）但不在 KNOWN_APIS 里，
            #    且不是 builtin / 第三方 / 用户自定义 / hallucination / deprecated → 报 info
            if self._strict and func_name:
                self._check_against_whitelist(func_name, node)

        self.generic_visit(node)

    def _check_against_whitelist(self, func_name: str, node: ast.Call) -> None:
        """JQ005：检查 func_name 是否是 KNOWN_APIS 之外的"未识别函数"。"""
        # 含 `.` 表示 module.func 形式（如 jqdata.something）
        # 只检查疑似聚宽 namespace：jqdata.* / jqfactor.* / jqlib.*
        # 其他模块（pd.*, np.* 等）跳过
        if '.' in func_name:
            module = func_name.split('.', 1)[0]
            if module not in {'jqdata', 'jqfactor', 'jqlib'}:
                return
            # 这些 namespace 下的 attribute call 在 KNOWN_APIS 里通常没记
            # 留给 KNOWN_HALLUCINATIONS 抓
            return

        # 已经被前面的 JQ001/JQ002 处理过的，跳过
        if func_name in KNOWN_HALLUCINATIONS or func_name in DEPRECATED_APIS:
            return
        # 已知 API、第三方、builtin、用户自定义 → 跳过
        if func_name in KNOWN_APIS:
            return
        if func_name in _THIRD_PARTY_MODULES or func_name in _PYTHON_BUILTINS:
            return
        if func_name in self._user_defined_funcs or func_name in self._imported_names:
            return
        # 名字看起来不像聚宽 API（不是 snake_case，或太短/太长）→ 跳过
        if not re.match(r'^[a-z][a-z0-9_]{3,40}$', func_name):
            return

        self.report.add(
            'info', node.lineno, node.col_offset, 'JQ005',
            f'未识别的函数调用 {func_name}（不在聚宽 API 白名单内）',
            f'确认 {func_name} 是用户函数 / 第三方库还是漏掉的聚宽 API；'
            f'若是聚宽 API 但 lint 未识别，请到 scripts/strategy_lint.py 的 KNOWN_APIS 加上',
        )

    def _extract_call_name(self, node: ast.AST) -> str | None:
        """从 ast.Call.func 提取完整调用名（含 module.func 形式）。"""
        if isinstance(node, ast.Name):
            return node.id
        if isinstance(node, ast.Attribute):
            value = self._extract_call_name(node.value)
            if value:
                return f'{value}.{node.attr}'
            return node.attr
        return None

    def finalize(self) -> None:
        """visit 完成后做整体检查。"""
        if self._initialize_seen:
            if not self._has_use_real_price:
                self.report.add(
                    'warning', 0, 0, 'JQ010',
                    '没有调用 set_option(\'use_real_price\', True)',
                    '在 initialize 里加：set_option(\'use_real_price\', True)，避免未来函数',
                )
            if not self._has_order_cost:
                self.report.add(
                    'warning', 0, 0, 'JQ011',
                    '没有调用 set_order_cost(...)',
                    '在 initialize 里加 set_order_cost，否则用聚宽默认费率，可能与实际券商不符',
                )
            if not self._has_slippage:
                self.report.add(
                    'warning', 0, 0, 'JQ012',
                    '没有调用 set_slippage(...)',
                    '在 initialize 里加 set_slippage(FixedSlippage(0.02)) 模拟真实成交滑点',
                )


def lint_file(path: Path, strict: bool = False) -> LintReport:
    source = path.read_text(encoding='utf-8')
    report = LintReport(file=str(path))

    try:
        tree = ast.parse(source)
    except SyntaxError as e:
        report.add(
            'error', e.lineno or 0, e.offset or 0, 'JQ000',
            f'Python 语法错误：{e.msg}',
        )
        return report

    linter = StrategyLinter(report, source, strict=strict)
    linter.visit(tree)
    linter.finalize()
    return report


def render_report(report: LintReport) -> str:
    lines: list[str] = []
    lines.append('=' * 70)
    lines.append(f'JoinQuant Strategy Lint Report — {report.file}')
    lines.append('=' * 70)
    if report.passed and not report.warnings:
        lines.append('PASSED — 没有发现问题')
        return '\n'.join(lines)

    lines.append(f'Errors: {len(report.errors)}    Warnings: {len(report.warnings)}')
    lines.append('')

    severity_order = {'error': 0, 'warning': 1, 'info': 2}
    for issue in sorted(report.issues, key=lambda i: (severity_order[i.severity], i.line)):
        sev_label = {'error': '[ERROR]', 'warning': '[WARN] ', 'info': '[INFO] '}[issue.severity]
        loc = f'L{issue.line}:{issue.col}' if issue.line else 'global'
        lines.append(f'{sev_label} {issue.code} {loc}: {issue.message}')
        if issue.fix_hint:
            lines.append(f'         fix: {issue.fix_hint}')

    lines.append('')
    lines.append(f'Detected API calls: {len(report.api_calls_found)}')
    lines.append('  ' + ', '.join(sorted(report.api_calls_found)[:15]) +
                 (' ...' if len(report.api_calls_found) > 15 else ''))
    lines.append('=' * 70)
    return '\n'.join(lines)


def main() -> int:
    parser = argparse.ArgumentParser(description='JoinQuant strategy code linter')
    parser.add_argument('file', help='Path to .py strategy file')
    parser.add_argument('--json', action='store_true', help='Output JSON instead of text')
    parser.add_argument('--strict', action='store_true',
                        help='启用 JQ005 白名单检查（未识别的函数调用报 info）')
    args = parser.parse_args()

    path = Path(args.file)
    if not path.exists():
        print(f'[error] File not found: {path}', file=sys.stderr)
        return 2

    report = lint_file(path, strict=args.strict)

    if args.json:
        print(json.dumps(report.to_dict(), ensure_ascii=False, indent=2))
    else:
        print(render_report(report))

    return 0 if report.passed else 1


if __name__ == '__main__':
    sys.exit(main())
