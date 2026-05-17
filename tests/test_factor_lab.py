"""factor_lab/ 测试 — IC / grouping。"""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from factor_lab import compute_ic, grouping_backtest, ic_decay


def _make_synthetic_data(n_dates: int = 100, n_stocks: int = 80,
                        signal_strength: float = 0.3, seed: int = 0):
    """生成 factor + return panel，其中 return 与 factor 有指定强度的真实相关。"""
    rng = np.random.default_rng(seed)
    dates = pd.date_range("2024-01-01", periods=n_dates, freq="B")
    stocks = [f"S{i:04d}.XSHG" for i in range(n_stocks)]

    factor = pd.DataFrame(
        rng.normal(0, 1, (n_dates, n_stocks)), index=dates, columns=stocks
    )
    noise = pd.DataFrame(
        rng.normal(0, 1, (n_dates, n_stocks)), index=dates, columns=stocks
    )
    # forward returns = signal × factor + noise
    forward_returns = signal_strength * factor + noise
    return factor, forward_returns


# ---------------------------------------------------------------------------
# IC
# ---------------------------------------------------------------------------

def test_ic_positive_when_signal_exists():
    factor, ret = _make_synthetic_data(signal_strength=0.5)
    r = compute_ic(factor, ret, method="spearman")
    assert r.ic_mean > 0.2, f"应当检测出正信号，实际 IC={r.ic_mean:.3f}"
    assert r.ic_ir > 0.5
    assert r.ic_t_stat > 2


def test_ic_near_zero_when_no_signal():
    factor, ret = _make_synthetic_data(signal_strength=0.0)
    r = compute_ic(factor, ret, method="spearman")
    assert abs(r.ic_mean) < 0.05


def test_ic_supports_pearson_and_spearman():
    factor, ret = _make_synthetic_data()
    r_p = compute_ic(factor, ret, method="pearson")
    r_s = compute_ic(factor, ret, method="spearman")
    # 两种方法都应当正信号
    assert r_p.ic_mean > 0
    assert r_s.ic_mean > 0
    assert r_p.method == "pearson"
    assert r_s.method == "spearman"


def test_ic_win_rate_makes_sense():
    factor, ret = _make_synthetic_data(signal_strength=1.0)  # 极强信号
    r = compute_ic(factor, ret)
    assert r.ic_win_rate > 0.7  # 大部分日期 IC > 0


def test_ic_invalid_method_raises():
    factor, ret = _make_synthetic_data()
    with pytest.raises(ValueError):
        compute_ic(factor, ret, method="foo")  # type: ignore[arg-type]


def test_ic_handles_misaligned_panels():
    """factor 和 returns 列不完全重合时应 work（取交集）。"""
    factor, ret = _make_synthetic_data(n_stocks=50)
    # 给 ret 加上 factor 没有的列
    ret = ret.copy()
    ret["NEW_STOCK.XSHG"] = np.random.randn(len(ret))
    r = compute_ic(factor, ret)
    assert r.ic_total_n > 0


# ---------------------------------------------------------------------------
# IC decay
# ---------------------------------------------------------------------------

def test_ic_decay():
    factor, _ = _make_synthetic_data()
    # 给不同 horizon 生成不同强度的 return
    rng = np.random.default_rng(1)
    returns_by_horizon = {}
    for h, strength in [(1, 0.5), (5, 0.3), (20, 0.1)]:
        noise = pd.DataFrame(
            rng.normal(0, 1, factor.shape), index=factor.index, columns=factor.columns
        )
        returns_by_horizon[h] = strength * factor + noise

    decay = ic_decay(factor, returns_by_horizon)
    assert "ic_mean" in decay.columns
    # 信号衰减：horizon 1 的 IC 应当大于 horizon 20 的
    assert decay.loc[1, "ic_mean"] > decay.loc[20, "ic_mean"]


# ---------------------------------------------------------------------------
# Grouping
# ---------------------------------------------------------------------------

def test_grouping_monotonicity_with_strong_signal():
    factor, ret = _make_synthetic_data(signal_strength=0.5, n_dates=200)
    r = grouping_backtest(factor, ret, n_groups=5)
    # 单调性：应当 > 0.5（理想 = 1.0）
    assert r.monotonicity_score > 0.5
    # 多空 Sharpe 应当显著
    assert r.long_short_sharpe > 0.5


def test_grouping_long_short_smaller_without_signal():
    """无信号时多空 Sharpe 不应显著为正（与有信号场景对比）。"""
    factor_signal, ret_signal = _make_synthetic_data(signal_strength=0.5, n_dates=200)
    factor_noise, ret_noise = _make_synthetic_data(signal_strength=0.0, n_dates=200, seed=7)
    r_signal = grouping_backtest(factor_signal, ret_signal, n_groups=5)
    r_noise = grouping_backtest(factor_noise, ret_noise, n_groups=5)
    # 信号场景的 Sharpe 应显著高于无信号场景
    assert r_signal.long_short_sharpe > abs(r_noise.long_short_sharpe), (
        f"signal Sharpe={r_signal.long_short_sharpe:.2f} should beat "
        f"|noise Sharpe|={abs(r_noise.long_short_sharpe):.2f}"
    )
    # 无信号场景的 |Sharpe| 应当较小（理论上 ~0，给宽松阈值）
    assert abs(r_noise.long_short_sharpe) < 2.0


def test_grouping_returns_correct_shape():
    factor, ret = _make_synthetic_data()
    r = grouping_backtest(factor, ret, n_groups=5)
    assert r.group_returns.shape[1] == 5
    assert r.group_cumulative.shape == r.group_returns.shape
