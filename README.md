# JoinQuant Skill

让 AI agent（Cursor / Claude Code / Codex / OpenCode 等）能正确生成符合**聚宽（JoinQuant）平台**的量化策略代码。

项目本身不教 AI 做策略，而是给 AI 一份结构化的 API 知识库、可粘贴运行的策略模板、静态检查工具、因子库与单因子分析工具，以及一条把券商研报变成聚宽策略代码的流水线。所有产物都被组织成一个可 install 的 skill，被 Cursor / Claude Code / MCP 客户端按需检索。

## 一、它解决什么具体问题

用 Claude / Cursor 写聚宽策略时反复遇到的几个坑：

1. **模型乱编 API**：让它写 DiD 它返回 `pandas.DataFrame.diff_in_diff()`；让它写聚宽策略它返回 `jqdata.get_stock_data()`——这些函数都不存在。
2. **数据 API 与回测 API 混淆**：聚宽的 `get_price()` 在回测里和研究里行为不一样，模型常不分场景乱用。
3. **未来函数防不胜防**：回测里能跑、实盘崩盘的常见原因。
4. **复权模式搞错**：传统前复权 vs 真实价格（动态复权），细节一错全盘皆错。
5. **API 文档塞不进 prompt**：294KB 的官方文档不可能整段塞，但只塞一部分模型又用不全。

这些问题不是写更长的 prompt 能解决的，所以我们把它们封装成一个**可 install 的 skill**——按需检索、按场景路由、本地 lint。

## 二、能力地图（五大模块 + MCP 暴露层）

| 模块 | 是什么 | 怎么用 | 能粘到聚宽编辑器跑吗 |
|---|---|---|---|
| [`references/`](references/) | 把官方 294KB API 文档按主题拆成 14 份 markdown，让 AI 按场景关键词加载（progressive disclosure），不再一次塞整本。 | Cursor / Claude Code 读 [`SKILL.md`](SKILL.md) 路由表自动选；人类直接 `notepad references/02-data-getters.md` | — 知识库本身不入聚宽 |
| [`templates/`](templates/) + [`scripts/strategy_scaffold.py`](scripts/strategy_scaffold.py) | 5 个生产可用的策略骨架（基础单股 / 多因子 / ETF 轮动 / 动量 / 均值回归），每行关键 API 旁注 `# RATIONALE`。 | `python scripts/strategy_scaffold.py --type rotation --security 510300.XSHG --hold-num 5` | 是 — 直接复制 |
| [`scripts/strategy_lint.py`](scripts/strategy_lint.py) | 静态检查 25+ 条常见错误：编造 API、未来函数、缺 use_real_price / order_cost / slippage、在非交易时段下单等。`--strict` 模式开启 JQ005 白名单严格校验。 | `python scripts/strategy_lint.py my_strategy.py --strict` | — 检查工具，不入聚宽 |
| [`factors/`](factors/) | 9 个示例因子的注册表（value / momentum / quality / growth / size / volatility / reversal 七类）。每个因子带文献引用、聚宽官方 factor id 映射、推荐中性化协变量、已知陷阱。底层调聚宽官方 [`get_factor_values`](https://www.joinquant.com/help/api/help?name=factor_values)，不重写计算。 | `from factors import all_factors, get, resolve`；策略里直接用 `from jqfactor import get_factor_values` | 否（含子目录 import）。单个因子的 `compute_jq` 函数体可摘出来用，边界见 [`factors/USAGE.md`](factors/USAGE.md) |
| [`factor_lab/`](factor_lab/) | 单因子分析工具：IC / Rank-IC / 日频 IR / 衰减、五分组回测、多空 Sharpe、单调性评分。 | `from factor_lab import compute_ic, grouping_backtest`，配合本地 jqdatasdk 数据 | 否，本地研究专用 |
| [`research_importer/`](research_importer/) | 研报 PDF → 聚宽策略代码端到端流水线：PDF 抽取（3 后端 fallback）→ akshare 抓研报清单 → LLM prompt 构造 → ExtractedStrategy schema → 自动生成可粘贴的聚宽 `.py`。**流水线本身不调任何 LLM**——把 prompt 还给你，你用自己的 key 调。 | `python -m research_importer pipeline report.pdf -o out/` 或 `python -m research_importer fetch --code 600519` | 生成的策略可粘聚宽；流水线工具不入聚宽 |
| [`jqskill_mcp/`](jqskill_mcp/) | MCP server，把上述能力暴露成 `jq_*` 一组 tool 给 Claude Desktop、Cursor 等 MCP 客户端调用。工具输入用 Pydantic 校验，全部只读。 | `python -m jqskill_mcp.server`；客户端配置见 [`jqskill_mcp/server.py`](jqskill_mcp/server.py) 顶部 docstring | — 客户端服务 |

研报功能涉及版权边界，详见 [`research_importer/disclaimer.md`](research_importer/disclaimer.md)：仓库内不含任何研报正文；akshare 抓的是公开摘要而非付费 PDF；自备 PDF 自负版权责任。

## 三、三条典型工作流

完整步骤见 [`WORKFLOW.md`](WORKFLOW.md)，这里给概要。

### 工作流 A：手写或借 AI 写一个聚宽策略

```
你描述需求
   │
   ▼
Cursor / Claude Code 读 SKILL.md →
   路由到 templates/0X.py + references/0X.md → 生成代码
   │
   ▼
python scripts/strategy_lint.py my_strategy.py --strict
   │
   ▼  通过
粘贴到聚宽 Web 编辑器 → 编译 → 回测 → 调参
```

### 工作流 B：从一份研报复现多因子策略

```
report.pdf （你自己有的副本）            或   akshare 抓的研报清单
   │                                          │
   │  python -m research_importer extract     │  python -m research_importer fetch
   ▼                                          ▼     --code 600519 --limit 5
out/01_extracted_text.txt        ◀────────────┘
   │
   │  python -m research_importer build-prompt
   ▼
out/02_llm_prompt.json （system + user prompt）
   │
   │  你把 prompt 发给 Claude / GPT，把模型 JSON 输出存为 03_extracted.json
   ▼
out/03_extracted.json
   │
   │  python -m research_importer codegen
   ▼
out/strategy/strategy.py + _meta.yaml （自动跑 lint，过了就可粘聚宽）
```

一条龙：`python -m research_importer pipeline report.pdf -o out/`

完整 walkthrough：[`examples/case-research-replication/`](examples/case-research-replication/)（含一份可直接跑的 `sample_extracted.json` 和它生成的 `sample_strategy.py`）。

### 工作流 C：在本地做单因子研究

```python
from jqdatasdk import auth
from factors import get
from factor_lab import compute_ic, grouping_backtest

auth('your_jq_user', 'your_jq_pwd')

entry = get('roe_ttm')        # 拿 META + compute_local
# ... 按日期循环拉 factor 与 forward returns，组成 panel ...

ic = compute_ic(factor_panel, forward_returns)
print(ic.ic_mean, ic.ic_ir, ic.annualized_ir())

gb = grouping_backtest(factor_panel, forward_returns, n_groups=5)
print(gb.long_short_sharpe, gb.monotonicity_score)
```

详见 [`WORKFLOW.md`](WORKFLOW.md) 的「因子研究工作流」章节，本仓库 9 个因子与聚宽官方 factor id 的对照表见 [`factors/USAGE.md`](factors/USAGE.md)。

---

## 四、它和已有项目的关系

| 项目 | 解决什么 | 本仓库做什么 |
|---|---|---|
| [`JoinQuant/jqdatasdk`](https://github.com/joinquant/jqdatasdk) | 本地拉取聚宽数据 | 不重写，作为可选依赖被 `factors/*.compute_local` 引用 |
| [`stairclimber/joinquant_api`](https://github.com/stairclimber/joinquant_api) | 本地 IDE 智能提示（API 签名） | 借鉴它的函数签名结构 |
| [`marketcalls/vectorbt-backtesting-skills`](https://github.com/marketcalls/vectorbt-backtesting-skills) | VectorBT 回测 skill | 它做 VectorBT，我们专精聚宽 |
| [`brainbytes-dev/everything-claude-trading`](https://github.com/brainbytes-dev/everything-claude-trading) | 18 agents + 82 skills 通用量化系统 | 它做全栈，我们做窄而深 |
| [`microsoft/RD-Agent`](https://github.com/microsoft/RD-Agent) | 通用多 agent factor-model co-optimization | 它针对 qlib 平台，我们针对聚宽 + 给 AI 的 Skill 形态 |

本仓库聚焦聚宽平台的 API 准确性，目标是让 AI 生成的代码不用改就能粘到聚宽编辑器跑通；研报抽取与因子分析是这条主线上的两个延伸场景。

---

## 五、快速试用

### 1. 安装

```powershell
cd D:\projects                              # 选你喜欢的目录，避免名字带空格
git clone https://github.com/gaaiyun/joinquant-skill.git
cd joinquant-skill

# 注册为 Cursor / Claude Code 的 skill（junction 不占额外空间）
cmd /c mklink /J "$env:USERPROFILE\.cursor\skills\joinquant-skill" "$PWD"
cmd /c mklink /J "$env:USERPROFILE\.claude\skills\joinquant-skill" "$PWD"

# 装开发 / 测试依赖（核心 lint / scaffold 是纯标准库，不需要装）
pip install -r requirements-dev.txt

# 可选：装 akshare 才能用 fetch 命令
pip install akshare
```

详细 Windows / macOS / Linux 安装步骤见 [`INSTALL_CN.md`](INSTALL_CN.md)。

### 2. 在 Cursor / Claude Code 里用

直接在对话里说：

> 用 joinquant-skill 帮我写一个基于 RSI 的均值回归策略，标的 000300.XSHG 成分股，月度调仓

Cursor / Claude Code 读 `SKILL.md` → 路由到 `templates/05-mean-reversion.py` + `references/02-data-getters.md` → 生成可粘贴的代码 → 你本地跑 `python scripts/strategy_lint.py` 验证 → 粘到聚宽 Web 编辑器。

### 3. 命令行直接用

```powershell
# 看 14 个 reference 索引
notepad SKILL.md

# 命令行生成策略骨架
python scripts/strategy_scaffold.py --type rotation --security 510300.XSHG --hold-num 5

# 跑 lint 检查
python scripts/strategy_lint.py my_strategy.py --strict

# 搜索 API 用法
python scripts/api_search.py get_price

# 研报抽取流水线（详见 WORKFLOW.md）
python -m research_importer pipeline /path/to/report.pdf -o out/
python -m research_importer fetch --code 600519 --limit 5
```

### 4. 启动 MCP server 给其他 MCP 客户端用

```powershell
pip install "mcp[cli]"
python -m jqskill_mcp.server   # stdio 协议，被 Claude Desktop 等托管
```

Claude Desktop 的 `claude_desktop_config.json` 配置：

```json
{
  "mcpServers": {
    "joinquant-skill": {
      "command": "python",
      "args": ["-m", "jqskill_mcp.server"],
      "cwd": "D:\\projects\\joinquant-skill"
    }
  }
}
```

启动后客户端可以看到一组 `jq_*` 工具（列因子、查因子元数据、lint 策略代码、生成骨架、搜 API、构造研报抽取 prompt 等），完整签名见 [`jqskill_mcp/server.py`](jqskill_mcp/server.py)。

---

## 六、项目结构

```
joinquant-skill/
├── README.md                       项目入口（你现在在看）
├── SKILL.md                        Cursor / Claude Code skill 入口（含 YAML frontmatter）
├── WORKFLOW.md                     三条工作流总览：策略开发 / 研报复现 / 因子研究
├── INSTALL_CN.md                   Windows 中文安装指南
│
├── api文档/api.txt                 官方完整 API 文档原始备份（294KB）
├── references/                     14 个按类别拆分的 AI 友好知识库
├── templates/                      5 个生产可用策略模板
│
├── scripts/
│   ├── strategy_lint.py            静态 lint（25+ 条检查项 + JQ005 strict 模式）
│   ├── strategy_scaffold.py        命令行生成策略骨架
│   └── api_search.py               按关键词搜 api.txt
│
├── factors/                        因子注册表（9 个示例 × 7 类）
│   ├── _base.py / _helpers.py      FactorMeta + winsorize/standardize/neutralize
│   ├── _jq_native.py               聚宽官方 get_factor_values 包装层
│   ├── USAGE.md                    必读：本目录与聚宽编辑器的边界声明
│   └── value / momentum / quality / ...   按类组织的因子文件
│
├── factor_lab/                     单因子分析（IC / 分组回测 / 多空 Sharpe）
│   └── single_factor/
│       ├── ic.py                   compute_ic + ICReport.annualized_ir
│       └── grouping.py             grouping_backtest + monotonicity
│
├── research_importer/              研报 → 聚宽策略 端到端流水线
│   ├── __main__.py                 CLI：extract / fetch / build-prompt / codegen / pipeline
│   ├── extractor/
│   │   ├── pdf.py                  PDF 抽取（pypdfium2/pdfplumber/PyPDF2 三后端 fallback）
│   │   └── akshare_loader.py       用 akshare 抓某股票研报清单 + 摘要
│   ├── parser/
│   │   ├── schema.py               ExtractedStrategy / ExtractedFactor dataclass
│   │   └── prompts.py              LLM 三阶段抽取 prompt 模板
│   ├── generator/
│   │   └── strategy_code.py        ExtractedStrategy → 聚宽 .py（含真用 get_factor_values）
│   └── disclaimer.md               版权边界声明
│
├── jqskill_mcp/                    MCP server
│   └── server.py                   一组 jq_* tool（Pydantic 输入校验 + readOnlyHint）
│
├── examples/
│   ├── case-mean-reversion/        RSI 均值回归
│   ├── case-etf-rotation/          ETF 月度轮动
│   ├── case-research-replication/  研报 → 聚宽策略 端到端 walkthrough
│   └── bad-strategy-for-lint-test.py 给 lint 自测用的反例集合
│
├── tests/                          pytest 测试套件
└── .github/workflows/ci.yml        CI：pytest + dogfood lint templates / examples
```

---

## 七、核心约定

**不重新发明聚宽。** 不重写 jqdatasdk，不实现回测引擎，不下载付费研报正文。本仓库只做让 AI 准确生成聚宽代码这一件主线工作；研报抽取与因子分析是这条主线的两个相邻延伸。需要本地数据请用 [`jqdatasdk`](https://github.com/joinquant/jqdatasdk)，需要本地 IDE 智能提示请用 [`stairclimber/joinquant_api`](https://github.com/stairclimber/joinquant_api)。

**优先调聚宽官方因子库。** `factors/` 下的因子默认调聚宽 [`jqfactor.get_factor_values`](https://www.joinquant.com/help/api/help?name=factor_values) 拿预计算值，不手算 `query().filter()`。只有当聚宽确实没有现成因子时（如 5 日反转）才走 `get_price` 手算。

**中文优先。** 所有 references 中文为主，函数签名保留英文。注释里的 `# RATIONALE` 用中文解释「为什么这么写」。

**准确性 > 完整性。** 如果某个 API 在不同场景下行为有微妙差异（比如 `get_price` 在回测和研究环境的差异），references 必须明确写出来；宁可遗漏，不可错误。

**研报复现要尊重版权。** 仓库不内置任何券商研报正文；akshare 只拉公开摘要不抓付费 PDF；用户上传 PDF 需自负版权责任，对外发表复现结果时请用自己的话改写并注明出处。详见 [`research_importer/disclaimer.md`](research_importer/disclaimer.md)。

---

## 八、相关文档

- [`WORKFLOW.md`](WORKFLOW.md) — 三条工作流的完整步骤与命令
- [`SKILL.md`](SKILL.md) — Cursor / Claude Code 用的 skill 入口
- [`INSTALL_CN.md`](INSTALL_CN.md) — Windows 安装指南
- [`factors/USAGE.md`](factors/USAGE.md) — factors 模块与聚宽编辑器的边界声明
- [`research_importer/disclaimer.md`](research_importer/disclaimer.md) — 研报功能版权声明
- [`examples/case-research-replication/`](examples/case-research-replication/) — 研报复现端到端 walkthrough

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
