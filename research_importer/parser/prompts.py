"""
research_importer/parser/prompts.py — 给 LLM 的抽取 prompt 模板。

设计原则
--------
1. **三阶段**（参考 arxiv 2409.06289 Automate Strategy Finding with LLM in Quant
   Investment）：抽取 → 归类 → 自评
2. **结构化输出强约束**：要求 LLM 返回严格 JSON，匹配 schema.ExtractedStrategy
3. **示例驱动**：每个 prompt 都带 1 个完整 few-shot 例子（高质量样本）
4. **审计追溯**：要求每条 factor / constraint 都带原文片段引用

调用方式
--------
本模块只生成 prompt 字符串，**不直接调任何 LLM API**——具体走 OpenAI / Anthropic /
DeepSeek / 通义都由调用方决定。MCP server 里会有适配器。
"""
from __future__ import annotations

import json
from typing import Optional


SYSTEM_PROMPT_EXTRACT = """你是一个量化研报解析专家。任务：从一份券商金工 / 行业研报的文本中抽取
量化策略的结构化描述，输出 JSON。

抽取目标
--------
1. **策略概要**：标题、来源、universe（股票池）、调仓频率、基准、手续费 / 滑点
2. **主要因子（primary_factors）**：研报核心选股因子
3. **次要因子 / 过滤条件（secondary_factors）**：辅助筛选
4. **风险约束（risk_constraints）**：单股权重上限、行业暴露上限、跟踪误差等

每个因子必须包含：
- name (snake_case 英文，全局唯一)
- chinese_name
- category (value/momentum/quality/growth/volatility/size/reversal/liquidity/sentiment/alternative)
- definition (自然语言，≤ 200 字)
- formula (数学公式，若研报给出)
- direction (ascending = 越大越买；descending = 越小越买)
- paper_excerpts (从原文摘抄 1-3 句作证)
- jq_dependencies_guess (推测聚宽 API 依赖，如 ['valuation.pe_ratio']；不确定填 [])

输出格式
--------
严格 JSON，可被 `json.loads` 解析；不要在 JSON 之外添加任何文字（不要 ```json``` 包裹）。

confidence
----------
最后给出 confidence (0~1)：你认为本次抽取的可靠度。
"""


FEWSHOT_EXAMPLE = {
    "title": "基于盈利质量与动量的多因子选股模型",
    "source": "示例证券《选股因子系列》2024-06",
    "rebalance_freq": "monthly",
    "universe": "中证 800 剔除 ST 与停牌",
    "primary_factors": [
        {
            "name": "roe_ttm",
            "chinese_name": "TTM ROE",
            "category": "quality",
            "definition": "TTM 归母净利润 / 平均净资产；衡量股东资金运用效率，质量代理变量",
            "formula": "ROE_TTM = NetIncome_TTM / AvgEquity",
            "weight": 0.4,
            "direction": "ascending",
            "paper_excerpts": ["盈利质量上，我们采用 ROE_TTM 作为核心因子"],
            "jq_dependencies_guess": ["indicator.roe", "balance.total_owner_equities"],
        },
        {
            "name": "ret_12m_skip_1m",
            "chinese_name": "12 月动量剔近 1 月",
            "category": "momentum",
            "definition": "过去 252 个交易日到 21 个交易日前的累计收益率",
            "formula": "(P_{-21} / P_{-252}) - 1",
            "weight": 0.3,
            "direction": "ascending",
            "paper_excerpts": ["动量端使用 12-1 形式的累计收益"],
            "jq_dependencies_guess": ["get_price"],
        },
    ],
    "secondary_factors": [],
    "benchmark": "000906.XSHG",
    "fee_rate": 0.0003,
    "slippage": 0.002,
    "risk_constraints": [
        "单股权重 ≤ 3%",
        "行业暴露偏离基准 ≤ 1σ",
        "组合换手率 ≤ 50% / 月",
    ],
    "paper_excerpts": [
        "我们以中证 800 为基础股票池，每月末调仓",
        "组合内单股权重不超过 3%，行业偏离限制在 1 倍标准差内",
    ],
    "confidence": 0.85,
}


def build_extract_prompt(text: str, source_hint: Optional[str] = None) -> tuple[str, str]:
    """
    生成系统 prompt + user prompt。

    Parameters
    ----------
    text : 研报全文（已去掉页眉页脚的 cleaned 版本，传入前请适当截断到 ≤ 60k tokens）
    source_hint : 调用方知道的来源（"中信证券 xxx 2024-09"），帮 LLM 校准

    Returns
    -------
    (system_prompt, user_prompt)
    """
    fewshot_str = json.dumps(FEWSHOT_EXAMPLE, ensure_ascii=False, indent=2)
    user = (
        "以下是一份券商金工研报的正文文本。请按 system message 的要求抽取并返回 JSON。\n\n"
        + (f"来源提示：{source_hint}\n\n" if source_hint else "")
        + "===== 示例输出（仅作格式参考）=====\n"
        + fewshot_str
        + "\n===== 示例结束 =====\n\n"
        + "===== 研报正文（开始）=====\n"
        + text
        + "\n===== 研报正文（结束）=====\n\n"
        + "请输出 JSON。"
    )
    return SYSTEM_PROMPT_EXTRACT, user


SYSTEM_PROMPT_REVIEW = """你是量化策略 reviewer。给你一份从研报里抽出的 ExtractedStrategy JSON，
评估并指出：

1. **factor 命名问题**：是否符合 snake_case、是否过于通用（"momentum_factor" 太泛，应叫
   "ret_12m_skip_1m"）
2. **category 分类问题**：是否正确（"换手率" 是 liquidity 不是 momentum）
3. **direction 错误**：ascending vs descending 是否反了（"PE 越低越好" → direction 应是
   ascending 因为 E/P 越大越好；如果 factor 直接用 PE 则是 descending）
4. **jq_dependencies_guess 是否合理**：对照聚宽 valuation / income / balance / indicator
   表的字段
5. **遗漏的因子或约束**：研报里有提到但 JSON 里漏了

输出格式：严格 JSON，包含 `issues: [{factor_name, severity, message, suggested_fix}]`。"""


def build_review_prompt(extracted_json: str) -> tuple[str, str]:
    return SYSTEM_PROMPT_REVIEW, (
        "请 review 以下 ExtractedStrategy 抽取结果：\n\n"
        + extracted_json
        + "\n\n输出 issues JSON。"
    )
