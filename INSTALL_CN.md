# 中文安装与使用指南

> Windows + PowerShell 用户。macOS / Linux 用户把 PowerShell 命令换成 bash 即可。

## 1. 项目位置

把仓库 clone 到你喜欢的目录（**避免目录名带空格**，否则部分命令会失败）：

```powershell
# 例：放到 D:\projects
cd D:\projects
git clone https://github.com/gaaiyun/joinquant-skill.git
```

之后所有命令里 `$PROJECT_DIR` 即指这个 `D:\projects\joinquant-skill`。

## 2. Python 环境

需要 Python 3.10+（lint 工具用 AST，依赖较新版本）。

```powershell
python --version  # 应该 >= 3.10
```

我们的脚本不依赖任何 pip 包（lint / scaffold / api_search 全部用 Python 标准库）。

如果你想跑测试：
```powershell
pip install pytest
```

## 3. 注册到 Cursor / Claude Code

### 方式 1：junction 链接（推荐）

先 `cd` 到你 clone 的目录，然后用 `$PWD` 引用绝对路径（**不要把路径硬编码**）：

```powershell
cd D:\projects\joinquant-skill          # 你 clone 的路径
cmd /c mklink /J "$env:USERPROFILE\.cursor\skills\joinquant-skill" "$PWD"
cmd /c mklink /J "$env:USERPROFILE\.claude\skills\joinquant-skill" "$PWD"
```

junction 不占空间，编辑主目录两边自动同步。

### 方式 2：git clone 到 IDE skills 目录

```powershell
cd "C:\Users\$env:USERNAME\.claude\skills"
git clone https://github.com/gaaiyun/joinquant-skill.git
```

## 4. 在 Cursor / Claude Code 里使用

直接在对话里说：

```
用 joinquant-skill 写一个 ETF 轮动策略，标的池 5 个主流宽基指数 ETF，月度调仓
```

```
用 joinquant-skill 帮我审一下我下面这段聚宽代码，找问题
[paste code]
```

```
聚宽里 get_call_auction 怎么用
```

Cursor / Claude Code 会自动读 SKILL.md 路由到对应的 references 和模板。

## 5. 命令行直接用

### 列出可用模板

```powershell
cd D:\projects\joinquant-skill           # 替换成你 clone 的路径
python scripts\strategy_scaffold.py --list
```

### 生成一个策略

```powershell
# 默认参数
python scripts\strategy_scaffold.py --type basic --output my_strategy.py

# 自定义参数
python scripts\strategy_scaffold.py --type rotation --security 510500.XSHG --hold-num 5 --output etf_strategy.py

# 直接打印不写文件
python scripts\strategy_scaffold.py --type momentum
```

### 检查现有策略代码

```powershell
python scripts\strategy_lint.py my_strategy.py

# JSON 输出（机器可读）
python scripts\strategy_lint.py my_strategy.py --json
```

会输出：
- ❌ Errors：调用了不存在的 API、在禁止时段下单等
- ⚠️ Warnings：缺关键设置、用了已废弃 API
- 检测到的所有 API 调用列表

### 在 API 文档里搜函数

```powershell
python scripts\api_search.py get_price          # 搜函数名
python scripts\api_search.py 平行趋势           # 搜中文
python scripts\api_search.py --regex "set_\w+"  # 正则
python scripts\api_search.py --context 10 fq    # 更多上下文
```

## 6. 跑测试

```powershell
pip install pytest
python -m pytest tests -v
```

应该看到 13 个测试（v2 加了因子库 / factor_lab / research_importer / MCP server 后会更多）全部 PASS。

## 7. 完整流程示例：从想法到上线

```powershell
# 步骤 1：根据想法生成骨架
python scripts\strategy_scaffold.py --type rotation `
  --security 000300.XSHG `
  --hold-num 3 `
  --output my_etf_strategy.py

# 步骤 2：编辑参数（标的池、调仓频率等）
notepad my_etf_strategy.py

# 步骤 3：lint 检查
python scripts\strategy_lint.py my_etf_strategy.py

# 步骤 4：lint 通过后，复制全部代码
Get-Content my_etf_strategy.py | Set-Clipboard

# 步骤 5：粘贴到聚宽在线编辑器（https://www.joinquant.com）
# - 点「策略」→「新建策略」
# - 把代码粘进去
# - 设置回测时间 + 初始资金
# - 点「编译运行」

# 步骤 6：根据回测结果调整参数，重复 2-5
```

## 8. 故障排查

### `python scripts\strategy_lint.py` 报错 `SyntaxError`

是你的策略代码本身有语法错误。lint 会标出 JQ000，按提示修。

### `OSError: [WinError 1314]` 创建 junction 失败

需要管理员权限或开发者模式。两种解决：

```powershell
# 方案 1：以管理员身份打开 PowerShell 重试

# 方案 2：开启 Windows 开发者模式（不需要管理员）
# 设置 → 隐私和安全性 → 开发者选项 → 开启
```

### Cursor 看不到 skill

确认 junction 已建：
```powershell
ls "C:\Users\$env:USERNAME\.cursor\skills\joinquant-skill"
```

应该列出主项目内容。如果是空，重做 junction。

### 生成的代码粘到聚宽报错

- 检查 lint 输出，先解决所有 errors
- 检查回测开始时间是否合理（太早可能数据不全）
- 检查初始资金是否够买你的标的（A 股一手 100 股，10 元股票一手 1000 元）

### 删除 junction（不影响主项目）

```powershell
cmd /c rmdir "C:\Users\$env:USERNAME\.cursor\skills\joinquant-skill"
cmd /c rmdir "C:\Users\$env:USERNAME\.claude\skills\joinquant-skill"
```

## 9. 进一步学习

- [`SKILL.md`](./SKILL.md) — Cursor / Claude Code skill 完整说明
- [`README.md`](./README.md) — 项目介绍 + 与同类项目对比
- [`references/`](./references/) — 14 个 API 类别详解（progressive disclosure）
- [`templates/`](./templates/) — 5 个生产可用策略模板
- [`api文档/api.txt`](./api文档/api.txt) — 聚宽官方完整 API 文档原始备份

外部资源：
- [聚宽官网](https://www.joinquant.com)
- [聚宽 API 文档](https://www.joinquant.com/help/api/help)
- [聚宽社区](https://www.joinquant.com/community/list)
- [`JoinQuant/jqdatasdk`](https://github.com/joinquant/jqdatasdk) — 本地拉数据 SDK
