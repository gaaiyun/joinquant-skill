# JoinQuant Skill — 端到端工作流

## 快速开始（3 分钟上手）

```
用户：帮我写一个沪深300成分股的多因子月度调仓策略
  ↓
AI：从 templates/02-multi-factor.py 出发
  ↓ 追问 2-3 个关键参数
AI：生成代码 → 内部 lint 检查 → 交付
  ↓
用户：粘贴到聚宽编辑器 → 编译运行 → 查看回测结果
```

---

## 完整工作流（7 步）

### Step 1 — 描述策略想法

用自然语言告诉 AI 你想要什么策略。越具体越好：

| 好的描述 | 差的描述 |
|---|---|
| "用中证500成分股，按 PE 和动量双因子选 20 只，月度调仓" | "帮我写个量化策略" |
| "在 6 个 ETF 之间按 20 日动量轮动，每周一调仓" | "ETF 轮动" |
| "平安银行，布林带+RSI 均值回归，日度交易" | "做个股票策略" |

### Step 2 — AI 选择模板

AI 根据描述匹配最合适的模板：

| 策略类型 | 模板 | 关键词 |
|---|---|---|
| 单股票入门 | `01-basic-single-stock.py` | 均线、单股票、入门 |
| 多因子选股 | `02-multi-factor.py` | 因子、选股、PE、市值 |
| ETF 轮动 | `03-etf-rotation.py` | ETF、轮动、资产配置 |
| 动量选股 | `04-momentum-stock.py` | 动量、趋势跟踪 |
| 均值回归 | `05-mean-reversion.py` | 布林带、RSI、超买超卖 |

### Step 3 — AI 追问关键参数

AI 会问 2-3 个问题来定制策略：

1. **标的池**：哪个指数成分？自定义列表？ETF 池？
2. **调仓频率**：日 / 周 / 月？具体时间？
3. **风险控制**：止损线？单只仓位上限？行业中性？

### Step 4 — 生成策略代码

AI 基于模板修改参数、添加逻辑，生成完整可运行代码。

**代码必须包含**（lint 会检查）：
- ✅ `set_benchmark('000300.XSHG')`
- ✅ `set_option('use_real_price', True)`
- ✅ `set_order_cost(OrderCost(...), type='stock')`
- ✅ `set_slippage(...)`
- ✅ 使用 `run_daily` / `run_weekly` / `run_monthly` 调度

### Step 5 — Lint 检查

AI 在交付前用 `strategy_lint.py` 检查代码：

```
python scripts/strategy_lint.py your_strategy.py
```

检查项：
- ❌ 不存在的 API 调用（如 `jqdata.get_stock_data()`）
- ❌ 在 `before_trading_start` 中下单
- ❌ 缺少 `use_real_price` / `set_order_cost` / `set_slippage`
- ❌ 使用已废弃的 API（如 `update_universe`）
- ⚠️ 未使用 `g.` 管理全局状态

### Step 6 — 用户运行回测

1. 打开 [聚宽](https://www.joinquant.com) → 我的策略 → 新建策略
2. 粘贴 AI 生成的代码
3. 设置回测参数：
   - 起止日期（建议至少 3 年）
   - 初始资金（默认 100 万）
   - 运行频率（日/分钟）
4. 点击"编译运行"

### Step 7 — 分析结果 & 迭代

查看回测结果后，常见迭代方向：

| 问题 | 改进方向 | 需要加载的 reference |
|---|---|---|
| 收益太低 | 调因子权重、换股票池 | `03-jqlib.md` |
| 回撤太大 | 加止损、降仓位、行业分散 | `05-portfolio-optimization.md` |
| 换手率太高 | 降调仓频率、加换手率约束 | `05-portfolio-optimization.md` |
| 税费吃掉利润 | 调整 `set_order_cost` 参数 | `01-strategy-setup.md` |
| 滑点影响大 | 用 `PriceRelatedSlippage` | `14-strategy-engine.md` |

---

## 高级场景

### 期货策略

1. 初始化时 `set_subportfolios([SubPortfolioConfig(cash=..., type='futures')])`
2. 用 `get_dominant_future('IF')` 获取主力合约
3. 下单用 `order(..., side='long')` 或 `side='short'`
4. 参考 `references/12-futures.md`

### 融资融券策略

1. 初始化时 `type='stock_margin'`
2. 用 `margincash_open` / `marginsec_open` 操作
3. 参考 `references/11-margin-trading.md`

### Tick 级策略

1. 需要会员权限
2. 用 `subscribe` / `handle_tick` 替代 `handle_data`
3. 参考 `references/10-tick-strategy.md`

### 组合优化

1. `from jqlib.optimizer import *`
2. 用 `portfolio_optimizer` 计算最优权重
3. 参考 `references/05-portfolio-optimization.md`

---

## 工具箱速查

| 需求 | 工具 | 命令 |
|---|---|---|
| 生成策略骨架 | `strategy_scaffold.py` | `python scripts/strategy_scaffold.py --type rotation --security "510300.XSHG,159915.XSHE"` |
| 检查代码质量 | `strategy_lint.py` | `python scripts/strategy_lint.py my_strategy.py` |
| 搜索 API 用法 | `api_search.py` | `python scripts/api_search.py get_price` |
| 列出因子库 | `factors` 模块 | `python -c "import factors; print([e.meta.name for e in factors.all_factors()])"` |
| 单因子 IC / 分组分析 | `factor_lab` | `python -c "from factor_lab import compute_ic"` |
| 研报 PDF → 聚宽策略 | `research_importer` CLI | `python -m research_importer pipeline report.pdf -o out/` |
| akshare 抓某股票研报清单 | `research_importer fetch` | `python -m research_importer fetch --code 600519 --limit 5` |
| 启动 MCP server（给 Claude Desktop 等用） | `jqskill_mcp` | `python -m jqskill_mcp.server` |

---

## 研报复现工作流（v2 新增）

把券商研报里的多因子策略变成可在聚宽编辑器跑通的代码，分两种入口：

### 入口 A：自己有 PDF

```
report.pdf
   │
   │  python -m research_importer extract report.pdf -o out/01_text.txt
   ▼
out/01_text.txt （去页眉页脚的正文）
   │
   │  python -m research_importer build-prompt out/01_text.txt -o out/02_prompt.json
   ▼
out/02_prompt.json （含 system_prompt + user_prompt）
   │
   │  你把 prompt 粘到 Claude / GPT，把模型回的 JSON 存为 out/03_extracted.json
   ▼
out/03_extracted.json （ExtractedStrategy 结构）
   │
   │  python -m research_importer codegen out/03_extracted.json -o out/strategy/
   ▼
out/strategy/strategy.py + _meta.yaml （可粘到聚宽 Web 编辑器）
```

或者一条龙：

```bash
python -m research_importer pipeline report.pdf -o out/ \
    --source "中信证券《选股因子系列》2024-09"
```

会写入 `01_extracted_text.txt` / `02_llm_prompt.json`，提示你调 LLM 拿 JSON，存回后重跑 `codegen` 完成。

### 入口 B：用 akshare 抓研报清单

不用 PDF，直接从公开渠道拉某股票的研报摘要（标题 / 机构 / 评级 / 目标价 / 摘要）：

```bash
pip install akshare   # 一次性
python -m research_importer fetch --code 600519 --limit 5 -o out/00_reports.txt
```

输出文件按发布日期倒序，每篇研报用 `=` 分隔线分开。挑一篇感兴趣的摘出来后，走入口 A 的 Step 2-4。

> **重要**：akshare 抓的是摘要，**不是付费 PDF 全文**。仓库本身不内置任何研报正文；版权边界详见 [`research_importer/disclaimer.md`](research_importer/disclaimer.md)。

### 完整 case 演示

[`examples/case-research-replication/`](examples/case-research-replication/) 包含一个端到端走完的样例（含 `sample_extracted.json` 与 `sample_strategy.py`），可以照着抄。

---

## 因子研究工作流（v2 新增）

在本地用 `jqdatasdk` 拉数据，跑单因子 IC / 分组回测：

```python
from jqdatasdk import auth, get_index_stocks, get_price
from factors import get as get_factor
from factor_lab import compute_ic, grouping_backtest

auth('your_jq_user', 'your_jq_pwd')

# 1) 拿股票池
stocks = get_index_stocks('000906.XSHG', '2024-06-30')   # 中证 800 历史成分

# 2) 横截面拉一个因子（注：本地需先 auth jqdatasdk）
entry = get_factor('roe_ttm')
factor_series = entry.compute_local('2024-06-30', stocks)

# 3) 构造 panel 数据 + 前向收益
# 略：你需要按日期循环拉 factor / forward returns，组成 DataFrame[date × stock]

# 4) IC 分析
report = compute_ic(factor_panel, forward_returns_panel, method='spearman')
print(f"IC mean = {report.ic_mean:.4f}")
print(f"IC IR (日频) = {report.ic_ir:.4f}")
print(f"IC IR (年化) = {report.annualized_ir():.4f}")

# 5) 五分组回测
gb = grouping_backtest(factor_panel, forward_returns_panel, n_groups=5)
print(f"多空 Sharpe = {gb.long_short_sharpe:.2f}")
print(f"单调性评分 = {gb.monotonicity_score:.2f}")
```

[`factors/USAGE.md`](factors/USAGE.md) 列出了本仓库 9 个因子与聚宽官方 factor id 的对照表，以及「本模块不能整体粘到聚宽编辑器」的边界声明。

---

## 常见陷阱清单

| 陷阱 | 后果 | 预防 |
|---|---|---|
| 没开 `use_real_price` | 回测有未来函数偏差 | lint 会报错 |
| 在 `before_trading_start` 下单 | 订单被拒绝 | lint 会报错 |
| 跨日缓存 `get_price` 返回值 | 前复权价格不一致 | 每天重新获取 |
| 手动计算买入股数 | 拆股后出错 | 用 `order_value` |
| 全局变量不用 `g.` | 跨运行状态泄露 | 统一用 `g.xxx` |
| `pip install` 第三方库 | 平台沙箱不支持 | 只用预装库 |
| 对主力合约代码下单 | 报错 | 先 `get_dominant_future` |
