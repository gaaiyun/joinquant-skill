# JoinQuant Skill

让 AI agent（Cursor / Claude Code / Codex / OpenCode 等）能正确生成符合**聚宽（JoinQuant）平台**的量化策略代码。

它不是教 AI 做策略，而是给 AI 一份结构化的 API 知识库、可粘贴运行的策略模板和静态检查工具，让生成结果能直接复制进聚宽 Web 编辑器跑通。v2 又在此之上补齐了因子注册表、单因子分析工具、研报抽取流水线和 MCP server。

## v2 新增模块

| 模块 | 用途 | 与聚宽编辑器的关系 |
|---|---|---|
| [`factors/`](factors/) | 因子注册表与元数据库。包含 9 个示例因子，覆盖 value / momentum / quality / growth / size / volatility / reversal 七类，每个因子都附原始文献引用、聚宽 factor id 映射、推荐中性化协变量、已知陷阱。底层调用聚宽官方 [`get_factor_values`](https://www.joinquant.com/help/api/help?name=factor_values) 而不是手算字段。 | 不能整体粘贴到聚宽编辑器（含子目录 import），但单个因子的 `compute_jq` 函数体可以摘出来直接用。详细边界见 [`factors/USAGE.md`](factors/USAGE.md)。 |
| [`factor_lab/`](factor_lab/) | 单因子分析工具：IC、Rank-IC、信息比率（日频）、IC 衰减、五分组回测、多空 Sharpe、单调性评分。 | 仅用于本地研究，配合 jqdatasdk 拉到本地的数据。 |
| [`research_importer/`](research_importer/) | 研报 PDF 抽取流水线：PDF 文本抽取 → LLM 抽取 prompt（system + user）→ ExtractedStrategy schema → 聚宽策略代码生成。流水线本身不调用任何 LLM，prompt 与 schema 都交给上层应用调度。 | 生成结果就是可粘贴的聚宽策略文件；流水线本身只是开发期工具。 |
| [`jqskill_mcp/`](jqskill_mcp/) | MCP server，把上述能力暴露成 7 个 tool 给 Claude Desktop、Cursor 等 MCP 客户端调用。所有工具都标注为 `readOnlyHint=True`，用 Pydantic 校验输入。包名特意叫 `jqskill_mcp` 而不是 `mcp`，避免与 [官方 `mcp` 包](https://pypi.org/project/mcp/) 冲突。 | 不适用——这是 IDE/agent 端的服务。 |
| [`scripts/strategy_lint.py`](scripts/strategy_lint.py) v2 升级 | 新增 JQ005 白名单严格模式（`--strict`），把 hallucination 黑名单从 9 条扩到 25 条，文档对照真实实现。 | 跑在本地的 Python 静态检查工具，不入聚宽云。 |

研报抽取功能涉及版权边界，详见 [`research_importer/disclaimer.md`](research_importer/disclaimer.md)：仓库内不含任何研报正文，用户需自备合法获取的 PDF 副本。

---

## 这个项目要解决什么

我用 Claude / Cursor 写聚宽策略时遇到几个反复出现的问题：

1. **模型乱编 API**：让它写 DiD 它给我 `pandas.DataFrame.diff_in_diff()`，让它写聚宽策略它给我 `jqdata.get_stock_data()`——这些都不存在。模型从训练数据里"猜"了一个看着像的名字。
2. **混淆数据 API 和回测 API**：聚宽的 `get_price()` 在回测里和研究里行为不一样，模型往往不分场景就乱用。
3. **未来函数防不胜防**：模型生成的代码经常违反"不能用未来数据"的规则，回测能跑通，实盘崩盘。
4. **复权模式搞错**：传统前复权 vs 真实价格（动态复权），细节一错全盘皆错。
5. **每次都要把 API 文档塞进 prompt**：294KB 的官方文档不可能全塞，但只塞一部分模型又用不全。

这个项目是把这些问题封装成一个 **可直接 install 的 skill**。

---

## 它和已有项目的关系

| 项目 | 解决什么 | 我们做什么 |
|---|---|---|
| [`JoinQuant/jqdatasdk`](https://github.com/joinquant/jqdatasdk)（1.2K stars，官方） | 本地拉取聚宽数据 | reference，但不在我们项目里 |
| [`stairclimber/joinquant_api`](https://github.com/stairclimber/joinquant_api)（14 stars） | 本地 IDE 智能提示（API 签名） | 借鉴它的函数签名结构 |
| [`openclaw-skills-joinquant-strategy`](https://lobehub.com/zh-TW/skills/openclaw-skills-joinquant-strategy) | OpenClaw 平台 skill | 类似定位，但我们做 Cursor + Claude Code 双 IDE |
| [`marketcalls/vectorbt-backtesting-skills`](https://github.com/marketcalls/vectorbt-backtesting-skills)（100 stars） | VectorBT 回测 skill | 它做 VectorBT，我们做聚宽 |
| [`brainbytes-dev/everything-claude-trading`](https://github.com/brainbytes-dev/everything-claude-trading) | 18 agents + 82 skills 量化系统 | 它通用全栈，我们专精聚宽 |

**核心差异**：我们专注**单一平台的 API 准确性**——让 AI 生成的代码不需要改就能粘到聚宽编辑器跑通。

---

## 三大能力

### 1. AI 友好的 API 知识库（progressive disclosure）

把官方 294KB 的 API 文档拆成 14 个 reference 文件，按需加载：

```
references/
├── 01-strategy-setup.md        # 策略设置（initialize / set_benchmark / set_option ...）
├── 02-data-getters.md          # 数据获取（get_price / attribute_history / history ...）
├── 03-jqlib.md                 # jqlib（alpha101 / alpha191 / technical_analysis ...）
├── 04-data-processing.md       # 数据处理函数
├── 05-portfolio-optimization.md # 组合优化
├── 06-trading.md               # 交易（order / order_value / order_target ...）
├── 07-objects.md               # 对象（Order / Position / Portfolio / OrderCost ...）
├── 08-misc-functions.md        # 其他
├── 09-multi-portfolio.md       # 多投资组合
├── 10-tick-strategy.md         # Tick 级策略专用
├── 11-margin-trading.md        # 融资融券（margincash_open / marginsec_open ...）
├── 12-futures.md               # 期货专用
├── 13-attribution-analysis.md  # 归因分析（Brinson / 因子分析）
└── 14-strategy-engine.md       # 策略引擎机制（订单处理 / 撮合 / 复权 / 滑点 / 税费 / 风险指标）
```

`SKILL.md` 是入口，根据用户的需求路由到对应的 reference 文件。

### 2. 策略模板库

5 个最常见的策略骨架，覆盖 80% 的实证策略类型：

```
templates/
├── 01-basic-single-stock.py    # 单股票均线策略（入门）
├── 02-multi-factor.py          # 多因子选股 + 月度调仓
├── 03-etf-rotation.py          # ETF 轮动（动量排序）
├── 04-momentum-stock.py        # 股票动量（横截面 + 时序）
└── 05-mean-reversion.py        # 均值回归（布林带 / RSI）
```

每个模板都：
- 直接可粘贴到聚宽编辑器跑通
- 头部注释说明回测参数建议
- 关键 API 调用旁边都有 `# RATIONALE` 注释解释为什么这么写

### 3. Lint 工具

防止 AI 编出不存在的 API 或写出未来函数：

```bash
python scripts/strategy_lint.py my_strategy.py
```

检查项：
- ✅ 所有函数调用都在聚宽 API 列表里
- ✅ `get_price` 是否传了 `count` 参数（避免未来函数的常见来源）
- ✅ 是否调用了 `set_option('use_real_price', True)`（强烈推荐开启）
- ✅ `OrderCost` 设置是否合理（手续费 / 印花税 / 最低收费）
- ✅ 滑点是否设置（`set_slippage`）
- ✅ 是否在 `before_trading_start` / `after_trading_end` 中下单（违法）
- ✅ 是否使用了已废弃的 API（如旧的 `update_universe`）

---

## 快速试用

### 在 Cursor / Claude Code 里直接用

```powershell
# 方法 1：先 clone，再 junction（推荐 — 编辑哪边都同步）
cd D:\projects                              # 选你喜欢的目录（避免名字带空格）
git clone https://github.com/gaaiyun/joinquant-skill.git
cd joinquant-skill
cmd /c mklink /J "$env:USERPROFILE\.cursor\skills\joinquant-skill" "$PWD"
cmd /c mklink /J "$env:USERPROFILE\.claude\skills\joinquant-skill" "$PWD"

# 方法 2：直接 clone 进 skills 目录
cd "$env:USERPROFILE\.claude\skills"
git clone https://github.com/gaaiyun/joinquant-skill.git
```

然后在 Cursor 对话里说：

> 用 joinquant-skill 帮我写一个基于 RSI 的均值回归策略，标的 000300.XSHG 成分股，月度调仓

Cursor 会自动读 SKILL.md → 路由到 `templates/05-mean-reversion.py` 和 `references/02-data-getters.md` → 生成可直接粘贴的代码。

### 不用 IDE，直接看文档

```powershell
# 看 SKILL.md 入口
notepad SKILL.md

# 看某个具体类别的 API
notepad references/02-data-getters.md

# 跑 lint 检查现有策略
python scripts/strategy_lint.py my_strategy.py
```

---

## 项目结构

```
joinquant-skill/
├── README.md                    项目入口（你现在在看）
├── SKILL.md                     Cursor / Claude Code skill 入口（带 frontmatter）
├── WORKFLOW.md                  策略开发完整工作流（编写 → lint → 粘贴 → 回测 → 模拟 → 实盘）
├── INSTALL_CN.md                Windows 中文安装指南
├── api文档/
│   └── api.txt                  完整官方 API 文档（294KB，原始备份）
├── references/                  14 个按类别拆分的 API 知识库
├── templates/                   5 个策略骨架模板
├── scripts/
│   ├── strategy_lint.py         lint 工具
│   ├── strategy_scaffold.py     根据描述生成策略骨架
│   └── api_search.py            按关键词搜索 API（fallback for unsupported queries）
├── examples/
│   ├── case-mean-reversion/         完整案例：RSI 均值回归
│   ├── case-etf-rotation/           完整案例：ETF 月度轮动
│   └── bad-strategy-for-lint-test.py "反例集合"（专门给 lint 自测用）
├── factors/                         (v2 新增) Barra 风格 7 大类因子库
├── factor_lab/                      (v2 新增) 单因子 IC / 分组 / 衰减分析
├── research_importer/               (v2 新增) 研报 PDF → 聚宽策略代码
├── jqskill_mcp/                     (v2 新增) MCP server（让任何 MCP 客户端调用本 skill）
└── tests/                           pytest 测试套件
```

---

## 核心约定

### 不重新发明聚宽

我们 **不重写** jqdatasdk，**不实现** 回测引擎。我们只做**让 AI 准确生成聚宽代码**这一件事。

如果你想本地拉数据，用 [`jqdatasdk`](https://github.com/joinquant/jqdatasdk)。  
如果你想 IDE 智能提示，用 [`stairclimber/joinquant_api`](https://github.com/stairclimber/joinquant_api)。  
我们的产物是 SKILL.md + 知识库 + 模板 + lint，是 **agent 用** 的，不是 **人用** 的代码库。

### 中文优先

所有 references 中文为主，函数签名英文。注释 RATIONALE 用中文解释为什么这么写。

### 准确性 > 完整性

如果某个 API 在不同场景下行为有微妙差异（比如 `get_price` 在回测和研究环境的差异），references 必须明确写出来。**宁可遗漏，不可错误**。

---

## License

MIT。详见 [LICENSE](./LICENSE)。

---

## Credits

- **官方 API 文档**：[聚宽 API 文档](https://www.joinquant.com/help/api/help)（已包含在 `api文档/api.txt`）
- **jqdatasdk**：[JoinQuant/jqdatasdk](https://github.com/joinquant/jqdatasdk)（聚宽官方数据 SDK）
- **本地 API 签名启发**：[stairclimber/joinquant_api](https://github.com/stairclimber/joinquant_api)
- **量化 trading skills 生态**：[brainbytes-dev/everything-claude-trading](https://github.com/brainbytes-dev/everything-claude-trading) / [marketcalls/vectorbt-backtesting-skills](https://github.com/marketcalls/vectorbt-backtesting-skills) / [tradermonty/claude-trading-skills](https://github.com/tradermonty/claude-trading-skills)
- **设计哲学**：受 [obra/superpowers](https://github.com/obra/superpowers) 的 progressive disclosure 启发
