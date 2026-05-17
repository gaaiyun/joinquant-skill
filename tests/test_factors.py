"""factors/ 测试 — registry + 元数据完整性。"""
from __future__ import annotations

import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

import factors


def test_registry_has_factors():
    assert len(factors.all_factors()) >= 9


def test_all_factors_have_complete_meta():
    """每个因子必须 META 字段齐全。"""
    for entry in factors.all_factors():
        m = entry.meta
        assert m.name, f"{m} 缺 name"
        assert m.chinese_name, f"{m.name} 缺 chinese_name"
        assert m.category, f"{m.name} 缺 category"
        assert m.description, f"{m.name} 缺 description"
        assert m.paper_refs, f"{m.name} 缺 paper_refs"
        assert m.direction in ("ascending", "descending"), f"{m.name} 方向不合法"


def test_factor_names_are_unique():
    names = [e.meta.name for e in factors.all_factors()]
    assert len(names) == len(set(names)), f"重名: {names}"


def test_by_category_returns_only_matching():
    for cat in ("value", "momentum", "quality", "growth", "size", "volatility", "reversal"):
        results = factors.by_category(cat)
        for entry in results:
            assert entry.meta.category == cat


def test_search_finds_value_factors():
    """search('价值') 至少能找到 value 类的因子。"""
    results = factors.search("PE")
    assert len(results) >= 1


def test_get_factor_by_name():
    entry = factors.get("pe_ttm_inverse")
    assert entry.meta.category == "value"


def test_get_unknown_factor_raises():
    import pytest
    with pytest.raises(KeyError):
        factors.get("nonexistent_factor_xyz")


def test_all_factors_have_compute_jq():
    """每个因子都应当提供 compute_jq（即使是简化版）。"""
    for entry in factors.all_factors():
        assert entry.compute_jq is not None, f"{entry.meta.name} 缺 compute_jq"
        assert callable(entry.compute_jq)


# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------

def test_winsorize_clips_extremes():
    import numpy as np
    import pandas as pd
    from factors._helpers import winsorize

    s = pd.Series(list(range(100)) + [10_000, -10_000])
    out = winsorize(s, lower=0.025, upper=0.975)
    assert out.max() < 200
    assert out.min() > -200


def test_standardize_zero_mean_unit_std():
    import numpy as np
    import pandas as pd
    from factors._helpers import standardize

    s = pd.Series(np.random.randn(1000))
    out = standardize(s)
    assert abs(out.mean()) < 0.01
    assert abs(out.std(ddof=1) - 1.0) < 0.01


def test_neutralize_removes_covariate_correlation():
    import numpy as np
    import pandas as pd
    from factors._helpers import neutralize

    np.random.seed(0)
    n = 1000
    mcap = pd.Series(np.random.randn(n), name="mcap")
    # 因子与市值高度相关
    factor = 0.7 * mcap + 0.3 * pd.Series(np.random.randn(n))
    residual = neutralize(factor, by=mcap.to_frame())
    corr = residual.corr(mcap)
    assert abs(corr) < 0.05, f"中性化后相关性 {corr:.3f} 应当接近 0"


def test_rank_normalize_in_range():
    import pandas as pd
    from factors._helpers import rank_normalize

    s = pd.Series(range(100))
    out = rank_normalize(s)
    assert out.min() >= -1.0
    assert out.max() <= 1.0
