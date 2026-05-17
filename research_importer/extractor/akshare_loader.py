"""
研报采集层 — 用 akshare 从东方财富等公开渠道拉券商研报。

为什么用 akshare
================
akshare 是免费开源（MIT 协议）的 A 股数据库，包装了东方财富、新浪、同花顺
等公开渠道的非授权数据。它的 ``stock_research_report_em`` 接口能直接给到
个股研报列表，避免我们自己爬反爬虫规则。

合规边界
========
- akshare 抓到的是**公开摘要 + 标题 + 评级 + 目标价**等元数据，**不包含
  研报正文 PDF**。
- 研报正文 PDF 一般需要券商客户后台访问；本工具不主动下载付费 PDF。
- 用户可以：
  1. 用本工具拉 ``akshare.stock_research_report_em`` 拿到研报清单 + 摘要；
  2. 自己从券商客户端下到 PDF 副本；
  3. 把 PDF 副本路径喂给 ``extract_text`` 完成正文抽取。

依赖
====
``pip install akshare`` （可选依赖，未装时所有 akshare 函数会抛
``AkshareNotInstalled``）。
"""
from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import List, Optional


log = logging.getLogger(__name__)


class AkshareNotInstalled(ImportError):
    """akshare 未安装。"""


def _check_akshare():
    try:
        import akshare  # noqa: F401
    except ImportError as exc:
        raise AkshareNotInstalled(
            "需要 akshare 才能用研报抓取功能。\n"
            "Suggested fix: pip install akshare"
        ) from exc


@dataclass(frozen=True)
class ResearchReportSummary:
    """单条研报元数据（来自 akshare）。"""

    stock_code: str
    stock_name: str
    title: str
    org: str          # 发布机构（券商）
    author: str
    rating: str       # 投资评级（买入 / 增持 / 中性 / 减持 / 卖出 / 无）
    target_price: Optional[float]
    publish_date: str
    summary: str      # 摘要（akshare 给的简短摘要，不是研报正文）
    source_url: Optional[str] = None

    def to_dict(self) -> dict:
        return {
            "stock_code": self.stock_code,
            "stock_name": self.stock_name,
            "title": self.title,
            "org": self.org,
            "author": self.author,
            "rating": self.rating,
            "target_price": self.target_price,
            "publish_date": self.publish_date,
            "summary": self.summary,
            "source_url": self.source_url,
        }


# 东方财富 stock_research_report_em 接口的字段映射
# （字段名以 akshare 实际返回为准；版本升级时若失败，请 print 一行看实际列名）
_FIELD_ALIASES = {
    "stock_code": ("股票代码", "代码"),
    "stock_name": ("股票简称", "简称", "股票名称"),
    "title": ("报告名称", "标题"),
    "org": ("机构", "发布机构"),
    "author": ("分析师", "作者"),
    "rating": ("最新评级", "评级"),
    "target_price": ("目标价", "目标价格"),
    "publish_date": ("日期", "发布日期"),
    "summary": ("内容", "摘要", "报告摘要"),
    "source_url": ("报告链接", "链接", "url"),
}


def _pick(row, aliases) -> Optional[str]:
    for k in aliases:
        if k in row.index:
            v = row[k]
            if v is None:
                return None
            if isinstance(v, float):
                # NaN
                import math
                if math.isnan(v):
                    return None
                return v
            return str(v).strip()
    return None


def _row_to_summary(row) -> ResearchReportSummary:
    """把 akshare DataFrame 的一行转为 ResearchReportSummary。"""
    raw_price = _pick(row, _FIELD_ALIASES["target_price"])
    target_price = None
    if raw_price not in (None, "", "-", "—"):
        try:
            target_price = float(str(raw_price).replace(",", ""))
        except (TypeError, ValueError):
            target_price = None
    return ResearchReportSummary(
        stock_code=str(_pick(row, _FIELD_ALIASES["stock_code"]) or ""),
        stock_name=str(_pick(row, _FIELD_ALIASES["stock_name"]) or ""),
        title=str(_pick(row, _FIELD_ALIASES["title"]) or ""),
        org=str(_pick(row, _FIELD_ALIASES["org"]) or ""),
        author=str(_pick(row, _FIELD_ALIASES["author"]) or ""),
        rating=str(_pick(row, _FIELD_ALIASES["rating"]) or ""),
        target_price=target_price,
        publish_date=str(_pick(row, _FIELD_ALIASES["publish_date"]) or ""),
        summary=str(_pick(row, _FIELD_ALIASES["summary"]) or ""),
        source_url=_pick(row, _FIELD_ALIASES["source_url"]),
    )


def fetch_stock_reports(
    stock_code: str,
    limit: int = 20,
) -> List[ResearchReportSummary]:
    """
    抓某只股票最近的研报列表（按发布日期倒序）。

    底层调用 ``akshare.stock_research_report_em``。

    Parameters
    ----------
    stock_code : 股票代码，**不带交易所后缀**（如 ``"000001"`` 而非 ``"000001.XSHE"``）。
        akshare 的 _em 接口用东方财富口径，纯数字 6 位代码。
    limit : 最多返回多少条。

    Returns
    -------
    list[ResearchReportSummary]

    Raises
    ------
    AkshareNotInstalled
        没装 akshare 包时。
    RuntimeError
        akshare 返回了非预期的结构（通常是接口升级）。
    """
    _check_akshare()
    import akshare as ak

    # akshare 接口约定见 https://akshare.akfamily.xyz/data/stock/stock.html
    try:
        df = ak.stock_research_report_em(symbol=stock_code)
    except Exception as exc:
        raise RuntimeError(
            f"akshare.stock_research_report_em(symbol={stock_code!r}) 调用失败：{exc}.\n"
            "Suggested fix: 检查股票代码是否正确（6 位数字，不带后缀）"
            "或 akshare 版本是否过旧 (pip install -U akshare)"
        ) from exc

    if df is None or len(df) == 0:
        return []

    # 按"日期"列倒序（如果字段名变了，akshare 通常自带排序）
    out: List[ResearchReportSummary] = []
    for _, row in df.head(limit).iterrows():
        try:
            out.append(_row_to_summary(row))
        except Exception as e:
            log.warning("跳过一行解析失败的研报：%s", e)
    return out


def summary_to_extractable_text(summary: ResearchReportSummary) -> str:
    """
    把 ``ResearchReportSummary`` 转成可喂给 LLM 抽取的文本片段。

    akshare 拿到的不是研报正文，只是元数据 + 摘要，但摘要里通常含核心
    投资逻辑与目标价，足够 LLM 抽出 ``ExtractedStrategy`` 的骨架。
    """
    lines = [
        f"【研报标题】{summary.title}",
        f"【发布机构】{summary.org}",
        f"【分析师】{summary.author}",
        f"【发布日期】{summary.publish_date}",
        f"【股票】{summary.stock_name} ({summary.stock_code})",
        f"【投资评级】{summary.rating}",
    ]
    if summary.target_price is not None:
        lines.append(f"【目标价】{summary.target_price}")
    lines.append("")
    lines.append("【摘要】")
    lines.append(summary.summary or "(akshare 未返回正文摘要)")
    if summary.source_url:
        lines.append("")
        lines.append(f"【原文链接】{summary.source_url}")
    return "\n".join(lines)
