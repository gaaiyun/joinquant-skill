# factors/ 模块使用说明

本目录里的代码**不能**整体复制到聚宽编辑器跑。它服务三个场景：

- 给 Cursor / Claude Code 等 AI 助手提供「因子元数据」做检索；
- 给 `factor_lab` 在本地 jqdatasdk 数据上做单因子分析提供 `compute_local` 接口；
- 给 `research_importer` 把研报抽出的因子名翻译成聚宽 factor id。

如果你只想在聚宽编辑器里用因子，直接 `from jqfactor import get_factor_values`。

---

## 一、聚宽自己已有因子库

聚宽自带 700+ 预计算因子，每天维护。在策略里直接调用即可：

```python
from jqfactor import get_factor_values

def handle_data(context, data):
    stocks = get_index_stocks('000906.XSHG')      # 中证 800
    factor_data = get_factor_values(
        securities=stocks,
        factors=['PE_TTM', 'ROE_TTM', 'SIZE', 'MOMENTUM', 'BTOP'],
        end_date=context.previous_date,           # 用前一交易日避免未来函数
        count=1,
    )
    # factor_data 是 dict: {factor_id → DataFrame[date × stock]}
    pe_ttm = factor_data['PE_TTM'].iloc[-1]       # 取最后一日横截面
    roe_ttm = factor_data['ROE_TTM'].iloc[-1]
    # ... 自己合成 / 排序 / 选股
```

聚宽因子库覆盖：

- 风格因子（CNE5 10 个）：`SIZE`、`BETA`、`MOMENTUM`、`RESVOL`、`SIZENL`、`BTOP`、`LIQUIDTY`、`EARNYILD`、`GROWTH`、`LEVERAGE`
- 基础因子：`pe_ratio`、`pb_ratio`、`ps_ratio`、`market_cap`、`turnover_rate` 等
- 质量因子：`ROE_TTM`、`ROA_TTM`、`gross_profit_margin_ttm` 等
- 成长因子：`inc_revenue_year_on_year`、`inc_net_profit_year_on_year` 等
- 技术 / 动量 / 风险 / 每股 / 行业 因子 ......

完整列表：`from jqfactor import get_all_factors; print(get_all_factors())`，或查 [聚宽官方文档](https://www.joinquant.com/help/api/help?name=factor_values)。

---

## 二、本仓库 `factors/` 的角色

聚宽官方因子库不提供以下三类信息，本模块补齐：

**因子元数据**

Cursor / Claude Code 通过 SKILL.md 路由进来时，能拿到每个因子的 [`FactorMeta`](_base.py)：

- `paper_refs`：文献出处，供 AI 引用
- `known_issues`：已知陷阱（如「金融股 ROE 偏高，建议行业内分位」）
- `recommended_neutralization`：推荐的中性化协变量
- `jq_dependencies`：聚宽对应的 factor id，AI 据此生成 `get_factor_values` 调用

**本地离线研究**

```python
import factors
from factor_lab import compute_ic, grouping_backtest
from jqdatasdk import auth, get_index_stocks

auth('your_user', 'your_pw')

stocks = get_index_stocks('000906.XSHG')
entry = factors.get('roe_ttm')
factor_series = entry.compute_local('2024-06-30', stocks)
```

`compute_local` 是本仓库提供的接口，配合 jqdatasdk 拉到本地的数据使用，不要求聚宽云环境。

**research_importer 的因子名翻译**

[`research_importer/generator/strategy_code.py`](../research_importer/generator/strategy_code.py) 从研报抽出 `ExtractedFactor` 后会查本 registry，把中文因子名映射到正确的聚宽 factor id。

---

## 三、不能这样用

聚宽编辑器是单文件环境，不支持子目录 import。下面两段在聚宽里都会直接报 `ModuleNotFoundError`：

```python
from factors._base import register
from factors.value.pe_ttm_inverse import compute_jq
```

每个 factor 文件最底下的 `register(FactorEntry(...))` 行依赖本仓库的 registry，**不要**把它一起复制到聚宽。

## 四、正确用法：只复制 `compute_jq` 函数体

例如，把 [factors/value/pe_ttm_inverse.py](value/pe_ttm_inverse.py) 的内容用在聚宽里：

```python
# 在聚宽编辑器里：
from jqdata import *
from jqfactor import get_factor_values

def initialize(context):
    set_benchmark('000906.XSHG')
    set_option('use_real_price', True)
    set_order_cost(OrderCost(close_tax=0.001, open_commission=0.0003,
                              close_commission=0.0003, min_commission=5), type='stock')
    set_slippage(FixedSlippage(0.002), type='stock')
    g.hold_num = 30

def my_ep_factor(context, universe):
    """从 factors/value/pe_ttm_inverse.py 的 compute_jq 函数体改写：
       直接调聚宽官方 EP 因子。"""
    data = get_factor_values(
        securities=universe,
        factors=['EP'],
        end_date=context.previous_date,
        count=1,
    )
    return data['EP'].iloc[-1]

def handle_data(context, data):
    stocks = get_index_stocks('000906.XSHG')
    ep = my_ep_factor(context, stocks)
    top = ep.dropna().sort_values(ascending=False).head(g.hold_num).index.tolist()
    # ... 调仓
```

---

## 五、本仓库 9 个因子的聚宽对应表

| 本仓库因子 | 聚宽 factor id | 转换 |
|---|---|---|
| `pe_ttm_inverse` | `EP` | 直接用（聚宽自带 1/PE_TTM） |
| `book_to_market` | `BTOP` | 直接用（CNE5 风格） |
| `ret_12m_skip_1m` | `MOMENTUM` | 直接用（CNE5 12-1 累计） |
| `roe_ttm` | `ROE_TTM` | 直接用 |
| `gross_profit_margin` | `gross_profit_margin_ttm` | 直接用 |
| `revenue_growth_yoy` | `inc_revenue_year_on_year` | 直接用 |
| `log_market_cap` | `SIZE` | 直接用（CNE5 ln(总市值)） |
| `vol_60d` | `Variance60` | 取 sqrt + 年化 ×√252 |
| `ret_5d` | （无官方对应） | 手算 `get_price(count=6)` |

→ `factors._jq_native.NATIVE_FACTOR_MAP` 是这张表的代码版。

---

## 六、Factor id 失效怎么办

聚宽偶尔会改 factor id 名（罕见但发生）。如果发现某个 id 调用报错：

```python
# 本地（必须先 auth jqdatasdk）：
from factors._jq_native import verify_factor_ids_locally
print(verify_factor_ids_locally(['PE_TTM', 'ROE_TTM', 'SIZE']))
# {'PE_TTM': True, 'ROE_TTM': True, 'SIZE': True}

# 或直接查官方：
from jqdatasdk import get_all_factors
print(get_all_factors())              # 当前全部有效 factor id
```

找到正确 id 后，请 PR 修正 [`_jq_native.py:NATIVE_FACTOR_MAP`](_jq_native.py)
和对应 factor 文件。

