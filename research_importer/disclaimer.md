# 研报导入功能 — 合规声明

本模块（`research_importer`）提供「**把券商研报 PDF 或公开文本转成聚宽策略代码**」
的工程化能力。**本仓库内不内置任何券商研报**。

## 用户责任

使用本模块前请**自行确认**：

1. **PDF 来源合法**：研报 PDF 是用户**自己合法获取**的副本（券商客户后台、
   付费数据库、公开渠道等）。本工具不会主动抓取版权内容。
2. **复现用途合规**：抽取的策略仅供**研究、自用回测**。如果你打算
   - 在公开博客 / 论文里发表「我复现了 XX 券商 XX 研报」，**必须**：
     - 用自己的话改写策略描述，不直接搬运研报原文
     - 在文末明确注明研报出处（券商 + 标题 + 日期）
     - 不展示 PDF 完整内容截图
   - 商用（产品 / 服务 / 收费课程），请先获得研报方书面授权
3. **数据来源**：如果通过 [`akshare`](https://akshare.akfamily.xyz) 等公开
   接口拉取研报正文，请遵守 akshare 与数据源的使用条款。

## 我们做什么 / 不做什么

| 做 | 不做 |
|---|---|
| 从用户提供的 PDF 文本抽取结构化策略描述 | 主动爬取付费研报数据库 |
| 把 LLM 抽取结果存入用户本地 SQLite | 把研报正文 / 抽取结果上传到云端 |
| 生成聚宽策略代码骨架供用户在自己账户回测 | 把因子签名暴露给第三方 |
| 在 README / commit 里**只**写"复现了某券商的多因子框架"等抽象描述 | 在代码 / 文档里贴研报原文片段 |

## 推荐工作流

```
1. 用户自己持有 PDF（自己拉的）
   ↓
2. CLI: python -m research_importer extract <local.pdf> --out tmp.json
   ↓
3. 人工 review tmp.json（修正 LLM 抽错的 direction / category）
   ↓
4. CLI: python -m research_importer codegen tmp.json --out strategies/my_replication/
   ↓
5. python scripts/strategy_lint.py strategies/my_replication/strategy.py
   ↓
6. 复制策略代码到聚宽 web 编辑器跑回测
```

整个流程**不联网**（除了 LLM 调用本身）；研报 PDF 在用户本地处理，不会
上传。

## 联系

如果你认为本仓库的某个 example / strategies / factors 文件触碰到了你的版权
（你是研报作者或券商方），请提 issue，我会立刻删除。
