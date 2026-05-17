# factors/ 模块使用说明 — ⚠️ 必读

> **简而言之：本模块不能整体复制到聚宽编辑器跑。**
> 它是给"本地研究 + AI agent 检索元数据 + research_importer 填模板"用的。
> 真正在聚宽云上用因子，**直接调聚宽官方** `from jqfactor import get_factor_values`。

---

## 一、聚宽自己已有因子库

⚠️ 第一原则：**聚宽自己就有 700+ 预计算因子**，每天维护。**不要重新发明轮子**。

```python
# 在聚宽云的策略代码里：
from jqfactor import get_factor_values

def handle_data(context, data):
    stocks = get_index_stocks('000906.XSHG')      # 中证 800
    factor_data = get_factor_values(
        securities=stocks,
        factors=['PE_TTM', 'ROE_TTM', 'SIZE', 'MOMENTUM', 'BTOP'],
        end_date=context.previous_date,           # 用前一交易日避免未来函数！
        count=1,
    )
    # factor_data 是 dict: {factor_id → DataFrame[date × stock]}
    pe_ttm = factor_data['PE_TTM'].iloc[-1]       # 拿最后一日横截面
    roe_ttm = factor_data['ROE_TTM'].iloc[-1]
    # ... 自己合成 / 排序 / 选股
```

**这就是聚宽策略里使用因子的标准方式**。聚宽因子库覆盖：

- **风格因子（CNE5 10 个）**：`SIZE`、`BETA`、`MOMENTUM`、`RESVOL`、`SIZENL`、`BTOP`、`LIQUIDTY`、`EARNYILD`、`GROWTH`、`LEVERAGE`
- **基础因子**：`pe_ratio`、`pb_ratio`、`ps_ratio`、`market_cap`、`turnover_rate` 等
- **质量因子**：`ROE_TTM`、`ROA_TTM`、`gross_profit_margin_ttm` 等
- **成长因子**：`inc_revenue_year_on_year`、`inc_net_profit_year_on_year` 等
- **技术 / 动量 / 风险 / 每股 / 行业 因子** ......

**完整列表**：`from jqfactor import get_all_factors; print(get_all_factors())`，或查 [聚宽官方文档](https://www.joinquant.com/help/api/help?name=factor_values)。

---

## 二、那本仓库的 `factors/` 在干嘛？

它做三件聚宽官方没做的事：

### 用途 1：给 AI agent 提供"因子元数据"

当用户问 Cursor / Claude Code "用 ROE 因子写一个选股策略"，AI 通过 SKILL.md
路由到本目录，能拿到一个 [`FactorMeta`](_base.py)：

- 文献出处（`paper_refs`）：让 AI 引用得有依据
- 已知问题（`known_issues`）：金融股 ROE 偏高 → 提醒做行业内分位
- 推荐中性化维度（`recommended_neutralization`）：让 AI 默认就做 SIZE + industry 中性化
- 聚宽对应 factor id（`jq_dependencies`）：让 AI 写出"调 `jqfactor.get_factor_values(['ROE_TTM'])`"
  的正确 API，**而不是手算 query()**

### 用途 2：本地 jqdatasdk 离线研究

不在聚宽云跑、想本地 Jupyter / VSCode 研究因子时：

```python
import factors                          # 触发 registry 加载
from factor_lab import compute_ic, grouping_backtest

entry = factors.get('roe_ttm')          # 拿 META + compute_local
# 自己 auth jqdatasdk 后跑
from jqdatasdk import auth, get_index_stocks
auth('your_user', 'your_pw')

stocks = get_index_stocks('000906.XSHG')
# 多日横截面拉取（research_importer / factor_lab 用）
factor_series = entry.compute_local('2024-06-30', stocks)
```

### 用途 3：research_importer 生成策略代码时的元数据池

[`research_importer/generator/strategy_code.py`](../research_importer/generator/strategy_code.py)
从研报抽出 `ExtractedFactor` 后，会查本 registry 找匹配项，自动填入正确的
聚宽 factor id。

---

## 三、绝对不要做的事 ❌

### ❌ 不要把整个 factors/ 目录复制到聚宽编辑器

聚宽编辑器是**单文件**环境，不支持子目录 import：

```python
# 在聚宽编辑器里这会报 ModuleNotFoundError:
from factors._base import register
from factors.value.pe_ttm_inverse import compute_jq
```

### ❌ 不要直接复制 `compute_jq` 函数加上 `from factors._base import ...`

如果你看到我们 factor 文件最底下有 `register(FactorEntry(...))` 这行，
**不要复制这行**到聚宽——它依赖本模块的 registry。

### ✅ 正确：只复制 `compute_jq` **函数体**

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

## 四、本仓库 9 个因子的「聚宽对应表」

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

## 五、Factor id 失效怎么办

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

---

## 六、为什么不直接全用聚宽官方？

我们也想，但还需要做以下额外事：

1. **元数据**：聚宽官方不给 `paper_refs` / `known_issues` / `recommended_neutralization`
2. **聚宽没有的因子**：`ret_5d`（5 日反转）、自定义事件因子等需要手算
3. **可测试性**：`factor_lab` 在本地用合成数据测试单因子分析逻辑，需要稳定的 compute_local 接口
4. **研报抽取**：`research_importer` 从研报抽到的因子名（"低价高股息" 等）不一定对应聚宽 factor id，需要 META 做语义匹配

所以本模块的角色是：**包一层 META + 兜底实现 + 名字翻译**，不重写计算。
