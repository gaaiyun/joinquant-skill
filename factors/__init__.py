"""
factors — Barra 风格 A 股因子库。

**重要边界（v2.1 修正）**：本模块**不**为聚宽编辑器单文件粘贴而设计 ——
聚宽编辑器不支持 `from factors._base import ...` 这种子目录 import。

正确使用方式见 [USAGE.md](USAGE.md)，三种模式：

1. **本地研究**：`jqdatasdk` + 我们的 compute_local
2. **聚宽云策略**：复制单个 `compute_jq` 函数体（不复制 `from factors._base ...`），
   或者直接用 `from jqfactor import get_factor_values` 一行调
3. **AI agent 检索**：通过 SKILL.md 路由到本模块的 META 元数据
"""
from __future__ import annotations

# 暴露 registry API
from factors._base import (  # noqa: F401
    Category,
    Direction,
    FactorEntry,
    FactorMeta,
    all_factors,
    by_category,
    get,
    register,
    reset_registry,
    search,
)

# 暴露聚宽官方因子包装层
from factors._jq_native import (  # noqa: F401
    NATIVE_FACTOR_MAP,
    NativeFactorCall,
    fetch_via_jqfactor,
    list_supported,
    resolve,
    verify_factor_ids_locally,
)

# 自动 import 所有 factor 文件以触发 register() 调用
# v1：手动列；v2 可以改成 pkgutil.walk_packages 自动扫描
from factors.value import pe_ttm_inverse, book_to_market  # noqa: F401, E402
from factors.momentum import ret_12m_skip_1m  # noqa: F401, E402
from factors.quality import roe_ttm, gross_profit_margin  # noqa: F401, E402
from factors.growth import revenue_growth_yoy  # noqa: F401, E402
from factors.size import log_market_cap  # noqa: F401, E402
from factors.volatility import vol_60d  # noqa: F401, E402
from factors.reversal import ret_5d  # noqa: F401, E402
