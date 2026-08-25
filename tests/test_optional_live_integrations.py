"""可选 live integration tests。

默认跳过，避免普通 CI 依赖 akshare 网络、jqdatasdk 安装或聚宽账号。
需要真实外部验证时显式设置环境变量：

- JQSKILL_ENABLE_AKSHARE_LIVE=1
- JQSKILL_ENABLE_JQDATA_LIVE=1
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

import pytest

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))


def _enabled(name: str) -> bool:
    return os.environ.get(name, "").strip().lower() in {"1", "true", "yes", "on"}


@pytest.mark.skipif(
    not _enabled("JQSKILL_ENABLE_AKSHARE_LIVE"),
    reason="set JQSKILL_ENABLE_AKSHARE_LIVE=1 to run akshare live fetch",
)
def test_akshare_live_fetch_returns_report_shape():
    """真实调用 akshare 个股研报接口，验证外部字段形状仍可解析。"""
    from research_importer.extractor.akshare_loader import (
        AkshareNotInstalled,
        fetch_stock_reports,
    )

    try:
        reports = fetch_stock_reports("600519", limit=1)
    except AkshareNotInstalled as exc:
        pytest.skip(str(exc))

    assert reports, "akshare live fetch returned no reports for 600519"
    report = reports[0]
    assert report.stock_code or report.stock_name
    assert report.title
    assert report.publish_date


@pytest.mark.skipif(
    not _enabled("JQSKILL_ENABLE_JQDATA_LIVE"),
    reason="set JQSKILL_ENABLE_JQDATA_LIVE=1 after jqdatasdk auth to verify factor ids",
)
def test_jqdatasdk_live_native_factor_ids_are_available():
    """真实调用 jqdatasdk.get_all_factors，验证 native factor id 未失效。"""
    from factors import NATIVE_FACTOR_MAP, verify_factor_ids_locally

    factor_ids = sorted({fid for fid in NATIVE_FACTOR_MAP.values() if fid})
    try:
        result = verify_factor_ids_locally(factor_ids)
    except ImportError as exc:
        pytest.skip(str(exc))

    missing = [fid for fid, ok in result.items() if not ok]
    assert not missing, f"native factor ids missing from jqdatasdk: {missing}"
