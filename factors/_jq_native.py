"""
factors/_jq_native.py — 聚宽官方因子库 `jqfactor.get_factor_values` 的包装层。

为什么有这个文件
================

聚宽自己就有因子库（700+ 预计算因子，每日维护）。我们的 `factors/` 模块
**优先用聚宽官方因子**，仅在聚宽没有时才手算。理由：

1. **数据正确性**：官方因子经过聚宽数据团队验证，比手写 `query() + indicator.*`
   稳健（对照单位 / 单季 vs TTM / 复权 等坑全踩过）
2. **维护成本**：聚宽自动每日刷新；我们手算每改一次都要回测验证
3. **跨用户兼容**：所有聚宽用户都能直接调，避免「在我机器跑得通在你机器跑不通」

聚宽因子的官方分类（10 大类）
============================

参见 https://www.joinquant.com/help/api/help?name=factor_values

| 分类 | 例子 |
|---|---|
| 风格因子 (Barra CNE5) | `SIZE` / `BETA` / `MOMENTUM` / `RESVOL` / `SIZENL` / `BTOP` / `LIQUIDTY` / `EARNYILD` / `GROWTH` / `LEVERAGE` |
| 基础因子 | `pe_ratio` / `pb_ratio` / `ps_ratio` / `pcf_ratio` / `market_cap` / `circulating_market_cap` |
| 质量因子 | `ROE_TTM` / `ROA_TTM` / `roic_ttm` / `gross_profit_margin_ttm` / `net_profit_margin_ttm` |
| 成长因子 | `inc_revenue_year_on_year` / `inc_net_profit_year_on_year` / `inc_operation_profit_year_on_year` |
| 动量因子 | `momentum_20d` / `momentum_60d` / `momentum_120d` |
| 技术因子 | `MA5` / `MA10` / `MA20` / `RSI` / `MACD` / `BIAS` |
| 情绪因子 | `turnover_rate` / `VOL5` / `VOL10` / `VOL20` |
| 风险因子 | `Variance20` / `Variance60` / `Variance120` |
| 每股因子 | `EPS` / `BPS` / `OPS_TTM` |
| 行业因子 | `industry_code`（行业编码，配合中性化用） |

⚠️ 上面是**部分常用因子**，**不是完整列表**。完整列表请：

- 聚宽云：`from jqfactor import get_all_factors; get_all_factors()`
- 本地：`from jqdatasdk import get_all_factors; get_all_factors()`
- 官方文档：https://www.joinquant.com/help/api/help?name=factor_values

如果本文件列的因子 ID 在你环境下不存在，说明聚宽改了 ID（罕见但发生）—— 请先跑
`get_all_factors()` 找正确名字，再 PR 修正这里的 mapping。

聚宽云调用 vs 本地调用
======================

```python
# === 聚宽云（策略代码里）===
from jqfactor import get_factor_values
data = get_factor_values(
    securities=stocks,
    factors=['PE_TTM', 'ROE_TTM', 'SIZE'],
    end_date=context.previous_date,    # 用 previous_date 避免未来函数
    count=1,                            # 只要最近 1 期
)
# data 是 dict: {factor_name: pd.DataFrame[date × stock]}
pe_ttm = data['PE_TTM'].iloc[-1]       # 横截面 Series[stock → value]

# === 本地（jqdatasdk + 已 auth）===
from jqdatasdk import auth, get_factor_values, get_index_stocks
auth('jq_username', 'jq_password')
stocks = get_index_stocks('000906.XSHG')
data = get_factor_values(stocks, ['PE_TTM'], end_date='2024-12-31', count=1)
```
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable, Optional


# ---------------------------------------------------------------------------
# 我们 factors/ 里的 factor.meta.name → 聚宽官方 factor id 的映射
# ---------------------------------------------------------------------------

NATIVE_FACTOR_MAP: dict[str, str] = {
    # value
    "pe_ttm_inverse": "EP",                # 聚宽自带 EP = 1/PE_TTM
    "book_to_market": "BTOP",              # CNE5 风格因子之一
    # momentum
    "ret_12m_skip_1m": "MOMENTUM",         # CNE5 MOMENTUM 是经典 12-1 形式，聚宽自己算
    # quality
    "roe_ttm": "ROE_TTM",
    "gross_profit_margin": "gross_profit_margin_ttm",
    # growth
    "revenue_growth_yoy": "inc_revenue_year_on_year",
    # size
    "log_market_cap": "SIZE",              # CNE5 SIZE = ln(总市值)
    # volatility（聚宽自己也有 RESVOL，但我们手算 60d realized vol 更直接）
    "vol_60d": "Variance60",               # 注：Variance60 是方差，要 sqrt 才是波动率
    # reversal（聚宽没现成 5d return 反转因子，保留手算）
    "ret_5d": None,                        # None = 没有官方对应
}


@dataclass(frozen=True)
class NativeFactorCall:
    """如何用 jqfactor.get_factor_values 拿一个因子。"""

    factor_id: str
    transform: Optional[str] = None   # 'invert' / 'sqrt' / None
    note: str = ""

    def docstring(self) -> str:
        lines = [f"调用 `get_factor_values(stocks, ['{self.factor_id}'], end_date=date, count=1)`"]
        if self.transform == "invert":
            lines.append("然后取倒数（1/x），因为聚宽给的是 PE/PB 等正比的字段。")
        elif self.transform == "sqrt":
            lines.append("然后开方，因为聚宽给的是 Variance 而非 Std。")
        if self.note:
            lines.append(self.note)
        return " ".join(lines)


def resolve(factor_name: str) -> Optional[NativeFactorCall]:
    """
    给一个我们 factors/ 里的因子名，返回对应的聚宽官方调用。

    Returns
    -------
    None 表示聚宽官方没有对应版本，需要本仓库手算（compute_jq 走 fallback 路径）。
    """
    native_id = NATIVE_FACTOR_MAP.get(factor_name)
    if native_id is None:
        return None
    transform: Optional[str] = None
    note = ""
    if factor_name == "vol_60d":
        transform = "sqrt"
        note = "Variance60 是方差，年化波动率 = sqrt(Variance60 * 252)。"
    if factor_name == "pe_ttm_inverse":
        # 聚宽自带 EP 因子，直接用，不需要反转
        note = "聚宽自带 EP = 净利润TTM / 市值，方向已经是越大越好。"
    return NativeFactorCall(factor_id=native_id, transform=transform, note=note)


def list_supported() -> list[tuple[str, str]]:
    """列出本仓库哪些因子有聚宽官方对应。"""
    return [
        (name, native_id) for name, native_id in NATIVE_FACTOR_MAP.items()
        if native_id is not None
    ]


# ---------------------------------------------------------------------------
# 聚宽云 / 本地的 unified call helper
# 给真正想跑的人用；本仓库不内置 LLM key 也不内置聚宽账号
# ---------------------------------------------------------------------------

def fetch_via_jqfactor(securities: list[str], factor_ids: Iterable[str],
                      end_date, count: int = 1):
    """
    统一入口：在聚宽云或本地 jqdatasdk 上拉因子。

    优先用 `jqfactor`（聚宽云上 strategy 里能直接 import）；
    失败再用 `jqdatasdk`（本地）。

    Returns
    -------
    dict[factor_id → pd.DataFrame]
    """
    factor_ids = list(factor_ids)
    end_date_str = str(end_date)[:10] if not isinstance(end_date, str) else end_date

    # 1. 试聚宽云的 jqfactor
    try:
        import jqfactor       # type: ignore
        return jqfactor.get_factor_values(
            securities=securities, factors=factor_ids,
            end_date=end_date_str, count=count,
        )
    except ImportError:
        pass

    # 2. 试本地 jqdatasdk（需要已 auth）
    try:
        import jqdatasdk      # type: ignore
        return jqdatasdk.get_factor_values(
            securities=securities, factors=factor_ids,
            end_date=end_date_str, count=count,
        )
    except ImportError as e:
        raise ImportError(
            "需要 jqfactor（聚宽云）或 jqdatasdk（本地，需 auth）才能调 get_factor_values。"
            "本地环境：pip install jqdatasdk; from jqdatasdk import auth; auth('user','pw')"
        ) from e


def verify_factor_ids_locally(factor_ids: Iterable[str]) -> dict[str, bool]:
    """
    给一组 factor id，逐个去 jqdatasdk 查它是否还在官方因子列表里。

    本函数仅在本地（已装 jqdatasdk + 已 auth）能跑。用于 v2 → v3 之间因子库
    可能改名的回归检查。

    Returns
    -------
    dict[factor_id → bool]
    """
    try:
        import jqdatasdk     # type: ignore
        all_df = jqdatasdk.get_all_factors()
    except ImportError as e:
        raise ImportError("需先装 jqdatasdk 并 auth") from e

    valid = set(all_df["factor"].astype(str).tolist()) if "factor" in all_df.columns else set()
    return {fid: fid in valid for fid in factor_ids}
