# Case：研报复现端到端 walkthrough

> 演示用 ``research_importer`` 把一份券商研报变成可在聚宽编辑器跑通的策略
> 代码。本目录里有完整工件，可以照着抄。

本 case 同时演示**两条入口**：

A. **自备 PDF**：你已经有了研报 PDF 副本（券商客户端下载的）。
B. **akshare 抓清单**：用 ``akshare`` 拉某股票最近的研报摘要（无需 PDF）。

---

## 入口 A：自备 PDF

### Step 1 — 抽文本

```bash
python -m research_importer extract /path/to/citic_factor_2024.pdf \
    -o out/01_extracted_text.txt
```

输出：原始正文清洗后的 ``.txt``（页眉页脚已去除，三后端自动 fallback：
``pypdfium2`` → ``pdfplumber`` → ``PyPDF2``，任一可用即可）。

### Step 2 — 构造 LLM prompt

```bash
python -m research_importer build-prompt out/01_extracted_text.txt \
    --source "中信证券《选股因子系列》2024-09" \
    -o out/02_llm_prompt.json
```

输出 ``02_llm_prompt.json`` 含 ``system_prompt`` 与 ``user_prompt`` 两个字段。
prompt 设计参考了
[arxiv 2409.06289 Automate Strategy Finding with LLM in Quant Investment](https://arxiv.org/abs/2409.06289)
的三阶段框架（抽取 → 归类 → 自评），并带一个完整 few-shot 示例。

### Step 3 — 调你自己的 LLM

打开 ``02_llm_prompt.json``：

- 复制 ``system_prompt`` 粘到 Claude / GPT 的 system 输入框；
- 复制 ``user_prompt`` 粘到 user 输入框；
- 模型会返回一段严格 JSON。

把那段 JSON 存为 ``out/03_extracted.json``（参考本目录的 ``sample_extracted.json``）。

> 本工具不直接调 LLM——你的 API key 自己掌握，cost 自己控制。

### Step 4 — 生成策略代码

```bash
python -m research_importer codegen out/03_extracted.json \
    -o out/strategy/ \
    --hold-num 30
```

会得到：

```
out/strategy/
├── strategy.py        # 可直接粘进聚宽 Web 编辑器
└── _meta.yaml         # 研报来源 / 因子清单 / 调仓频率 等元数据
```

自动跑完 ``strategy_lint``，若 lint 不过会以 exit 4 返回。

### Step 5 — 粘到聚宽 Web 编辑器

```
打开 https://www.joinquant.com
策略 → 新建策略 → 把 out/strategy/strategy.py 全文粘进去
设回测区间 / 初始资金 → 编译运行
```

### 一条龙 pipeline

上面 4 步合一：

```bash
python -m research_importer pipeline /path/to/citic_factor_2024.pdf \
    -o out/ \
    --source "中信证券《选股因子系列》2024-09"
```

会一次性写完 ``01_extracted_text.txt`` / ``02_llm_prompt.json``，提示你去调 LLM。
拿到 JSON 后存为 ``out/03_extracted.json``，重跑 ``codegen`` 即可。

---

## 入口 B：用 akshare 抓研报清单

适合"我对 600519（贵州茅台）最近的研报观点感兴趣，想批量做"。akshare 拿
到的是**研报标题 + 摘要 + 评级 + 目标价**等元数据，**不是 PDF 全文**——
但摘要里通常已包含核心投资逻辑与因子，足够 LLM 抽出 ``ExtractedStrategy``。

### Step 1 — 抓清单

需要先 ``pip install akshare``。然后：

```bash
python -m research_importer fetch --code 600519 --limit 5 \
    -o out/00_akshare_reports.txt
```

输出的 ``00_akshare_reports.txt`` 是 5 篇研报的文本拼接，每篇用 ``=`` 分隔
线分开，含标题 / 机构 / 分析师 / 评级 / 目标价 / 摘要。

也可以输出 JSON 做二次处理：

```bash
python -m research_importer fetch --code 600519 --limit 5 \
    --format json -o out/00_akshare_reports.json
```

### Step 2-4 — 同入口 A

```bash
# 任选一篇感兴趣的研报，把它的文本块单独存到 selected.txt
python -m research_importer build-prompt selected.txt \
    --source "某券商《xxx》2024-12" \
    -o out/02_llm_prompt.json

# 调 LLM 拿 JSON，存到 out/03_extracted.json

python -m research_importer codegen out/03_extracted.json -o out/strategy/
```

---

## 合规边界

- 本仓库**不内置**任何券商研报正文；
- ``research_importer.extractor.akshare_loader`` 只调 ``akshare`` 公开接口，
  返回的是东方财富等公开摘要，**不会绕过付费墙下载 PDF**；
- 若你打算**对外发表**「我复现了 XX 券商 XX 研报的策略」，请：
  - 用自己的话改写策略描述，不直接搬运研报原文；
  - 注明研报出处（券商 + 标题 + 日期）；
  - 不展示 PDF 完整截图。

详细见 [research_importer/disclaimer.md](../../research_importer/disclaimer.md)。

---

## 本目录文件

| 文件 | 用途 |
|---|---|
| ``README.md`` | 本说明 |
| ``sample_extracted.json`` | 一份示例的 LLM 抽取结果，可直接喂给 ``codegen`` 试 |
| ``sample_strategy.py`` | 用 sample_extracted.json 跑 codegen 后的产物（已 lint 通过） |
