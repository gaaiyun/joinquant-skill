"""research_importer.extractor.akshare_loader 测试。

不真打 akshare 网络；用 monkeypatch 注入假 akshare 模块，验证
- 缺 akshare 时抛 AkshareNotInstalled（带安装提示）
- 字段映射兼容多个候选列名
- summary_to_extractable_text 输出包含核心字段
"""
from __future__ import annotations

import sys
import types
from pathlib import Path

import pandas as pd
import pytest

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from research_importer.extractor.akshare_loader import (
    AkshareNotInstalled,
    ResearchReportSummary,
    fetch_stock_reports,
    summary_to_extractable_text,
)


# ---------------------------------------------------------------------------
# ResearchReportSummary 基础
# ---------------------------------------------------------------------------


def _make_summary(**overrides) -> ResearchReportSummary:
    defaults = dict(
        stock_code="600519",
        stock_name="贵州茅台",
        title="维持买入评级",
        org="测试证券",
        author="测试分析师",
        rating="买入",
        target_price=2000.0,
        publish_date="2024-09-01",
        summary="公司2024H1业绩稳健，看好长期增长。",
        source_url="https://example.com/report/123",
    )
    defaults.update(overrides)
    return ResearchReportSummary(**defaults)


def test_summary_to_dict_roundtrip():
    s = _make_summary()
    d = s.to_dict()
    assert d["stock_code"] == "600519"
    assert d["target_price"] == 2000.0
    assert d["rating"] == "买入"


def test_summary_to_extractable_text_includes_key_fields():
    s = _make_summary()
    text = summary_to_extractable_text(s)
    assert "贵州茅台" in text
    assert "600519" in text
    assert "维持买入评级" in text
    assert "测试证券" in text
    assert "2000" in text       # 目标价
    assert "买入" in text       # 评级
    assert "https://example.com/report/123" in text


def test_summary_to_extractable_text_handles_missing_optional_fields():
    s = _make_summary(target_price=None, source_url=None)
    text = summary_to_extractable_text(s)
    # 没目标价就不应出现"目标价"行
    assert "目标价" not in text
    assert "https://" not in text


# ---------------------------------------------------------------------------
# fetch_stock_reports：缺 akshare 时抛 AkshareNotInstalled
# ---------------------------------------------------------------------------


def test_fetch_stock_reports_raises_when_akshare_missing(monkeypatch):
    # 强制 sys.modules['akshare'] = None 让 import 失败
    monkeypatch.setitem(sys.modules, "akshare", None)
    with pytest.raises(AkshareNotInstalled, match="akshare"):
        fetch_stock_reports("600519", limit=1)


# ---------------------------------------------------------------------------
# fetch_stock_reports：用假 akshare 注入返回 DataFrame，验证字段映射
# ---------------------------------------------------------------------------


def _make_fake_akshare(df: pd.DataFrame) -> types.ModuleType:
    fake = types.ModuleType("akshare")
    fake.stock_research_report_em = lambda symbol: df
    return fake


def test_fetch_stock_reports_maps_chinese_columns(monkeypatch):
    """中文列名（akshare 实际格式）应能被字段别名解析。"""
    df = pd.DataFrame([
        {
            "股票代码": "600519",
            "股票简称": "贵州茅台",
            "报告名称": "盈利持续超预期",
            "机构": "测试证券",
            "分析师": "测试分析师",
            "最新评级": "买入",
            "目标价": 2000.0,
            "日期": "2024-09-01",
            "内容": "公司2024H1业绩稳健。",
            "报告链接": "https://example.com/r/1",
        },
        {
            "股票代码": "600519",
            "股票简称": "贵州茅台",
            "报告名称": "下半年展望",
            "机构": "另一证券",
            "分析师": "另一分析师",
            "最新评级": "增持",
            "目标价": "1950",
            "日期": "2024-09-15",
            "内容": "中秋旺季可期。",
            "报告链接": None,
        },
    ])
    monkeypatch.setitem(sys.modules, "akshare", _make_fake_akshare(df))

    reports = fetch_stock_reports("600519", limit=10)
    assert len(reports) == 2
    assert reports[0].stock_name == "贵州茅台"
    assert reports[0].title == "盈利持续超预期"
    assert reports[0].target_price == 2000.0
    assert reports[1].target_price == 1950.0     # 字符串数字也能解析
    assert reports[1].source_url is None          # None / NaN 兼容


def test_fetch_stock_reports_handles_dash_price(monkeypatch):
    """目标价是 '-' 或 '—' 时应当落到 None 而非崩溃。"""
    df = pd.DataFrame([{
        "股票代码": "600519", "股票简称": "贵州茅台", "报告名称": "x",
        "机构": "y", "分析师": "z", "最新评级": "无", "目标价": "-",
        "日期": "2024-09-01", "内容": "..", "报告链接": "https://x",
    }])
    monkeypatch.setitem(sys.modules, "akshare", _make_fake_akshare(df))
    reports = fetch_stock_reports("600519", limit=1)
    assert reports[0].target_price is None


def test_fetch_stock_reports_empty_df_returns_empty(monkeypatch):
    df = pd.DataFrame([])
    monkeypatch.setitem(sys.modules, "akshare", _make_fake_akshare(df))
    reports = fetch_stock_reports("000000", limit=10)
    assert reports == []


def test_fetch_stock_reports_respects_limit(monkeypatch):
    df = pd.DataFrame([
        {"股票代码": "600519", "股票简称": "x", "报告名称": f"R{i}",
         "机构": "y", "分析师": "z", "最新评级": "买入",
         "目标价": 100.0, "日期": "2024-09-01", "内容": "..", "报告链接": "u"}
        for i in range(20)
    ])
    monkeypatch.setitem(sys.modules, "akshare", _make_fake_akshare(df))
    reports = fetch_stock_reports("600519", limit=5)
    assert len(reports) == 5


def test_fetch_stock_reports_wraps_akshare_exception(monkeypatch):
    """akshare 内部抛异常时应包成 RuntimeError 带 actionable hint。"""
    fake = types.ModuleType("akshare")
    def _boom(symbol):
        raise ValueError("接口升级了")
    fake.stock_research_report_em = _boom
    monkeypatch.setitem(sys.modules, "akshare", fake)

    with pytest.raises(RuntimeError, match=r"接口升级|akshare"):
        fetch_stock_reports("600519", limit=1)
