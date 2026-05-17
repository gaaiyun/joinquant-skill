"""
jqskill_mcp/server.py — joinquant-skill 的 MCP server。

包名说明
========
本目录名为 ``jqskill_mcp``，与官方 ``mcp`` 包名错开。如果取名为 ``mcp/``，
Python 会把 ``from mcp.server.fastmcp import FastMCP`` 优先解析到本目录，
导致 ``ModuleNotFoundError: No module named 'mcp.server.fastmcp'``。

服务定位
========
把 joinquant-skill 的核心能力暴露为 7 个 MCP tool，让 Claude Desktop、
Cursor、自家 chatbot 等任意 MCP 客户端通过 stdio 协议调用：

- ``jq_list_factors``                  列出已注册因子，按 category / keyword 过滤
- ``jq_get_factor``                    单个因子的完整 META + compute_jq 源代码
- ``jq_resolve_factor_id``             把本仓库因子名翻译为聚宽官方 factor id
- ``jq_lint_strategy``                 对一段聚宽策略代码跑静态 lint
- ``jq_scaffold_strategy``             按模板生成策略骨架
- ``jq_search_api``                    在 ``api文档/api.txt`` 里搜函数/关键词
- ``jq_build_research_extract_prompt`` 把研报文本变为可发给 LLM 的抽取 prompt

启动方式
========
.. code-block:: bash

    pip install "mcp[cli]"
    python -m jqskill_mcp.server

Claude Desktop ``claude_desktop_config.json`` 配置示例：

.. code-block:: json

    {
      "mcpServers": {
        "joinquant-skill": {
          "command": "python",
          "args": ["-m", "jqskill_mcp.server"],
          "cwd": "<你 clone 的 joinquant-skill 路径>"
        }
      }
    }

设计原则
========
- 每个 tool 都有 Pydantic input model，类型与约束在 schema 层强制；
- 每个 tool 都标注 ``readOnlyHint / idempotentHint`` 等 annotation，方便客户端
  做权限或缓存决策；
- 所有 tool 都是只读的（不会修改用户文件 / 仓库 / 远程服务），运行安全；
- 错误通过 ``_format_error`` 统一格式，附带可操作的修复建议；
- 工具内部走同一组 ``*_impl`` 同步函数，测试不依赖 mcp 包也能直接调；
- 工具命名统一使用 ``jq_`` 前缀，避免与同一客户端下其他 MCP server 冲突。
"""
from __future__ import annotations

import inspect
import json
import logging
import os
import subprocess
import sys
import tempfile
from enum import Enum
from pathlib import Path
from typing import Any, List, Optional

from pydantic import BaseModel, ConfigDict, Field, field_validator


# ---------------------------------------------------------------------------
# 项目根目录加入 sys.path，便于 import factors / scripts / research_importer
# ---------------------------------------------------------------------------

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

SERVER_NAME = "joinquant_skill_mcp"
SERVER_VERSION = "0.2.0"

log = logging.getLogger(SERVER_NAME)


# ---------------------------------------------------------------------------
# 通用工具
# ---------------------------------------------------------------------------


class ResponseFormat(str, Enum):
    """输出格式选项。"""

    JSON = "json"
    MARKDOWN = "markdown"


def _format_error(exc: Exception, hint: str = "") -> str:
    """把异常格式化为带修复建议的可读字符串，避免向 LLM 暴露原始堆栈。"""
    base = f"[{type(exc).__name__}] {exc}".strip()
    return f"Error: {base}\nSuggested fix: {hint}" if hint else f"Error: {base}"


def _mcp_available() -> bool:
    try:
        import mcp  # noqa: F401
        return True
    except ImportError:
        return False


# ---------------------------------------------------------------------------
# 1. jq_list_factors
# ---------------------------------------------------------------------------


class ListFactorsInput(BaseModel):
    """``jq_list_factors`` 输入参数。"""

    model_config = ConfigDict(str_strip_whitespace=True, extra="forbid")

    category: Optional[str] = Field(
        default=None,
        description=(
            "按因子类别过滤。可选值："
            "value / momentum / quality / growth / volatility / size / "
            "reversal / liquidity / sentiment / alternative。"
            "缺省返回全部类别。"
        ),
        examples=["value", "momentum"],
    )
    keyword: Optional[str] = Field(
        default=None,
        description=(
            "在因子名、中文名、描述、文献引用中做模糊匹配（大小写不敏感）。"
        ),
        examples=["PE", "动量", "ROE"],
        max_length=80,
    )
    limit: int = Field(
        default=50,
        ge=1,
        le=200,
        description="返回的因子条数上限（分页用）。",
    )
    offset: int = Field(
        default=0,
        ge=0,
        description="跳过前 N 条结果（分页用）。",
    )


def list_factors_impl(
    category: Optional[str] = None,
    keyword: Optional[str] = None,
    limit: int = 50,
    offset: int = 0,
) -> dict:
    """返回因子注册表片段。给 *_impl 用，便于不装 mcp 也能测。"""
    import factors

    entries = factors.all_factors()
    if category:
        entries = [e for e in entries if e.meta.category == category]
    if keyword:
        kw = keyword.lower()
        entries = [
            e
            for e in entries
            if kw in e.meta.name.lower()
            or kw in e.meta.chinese_name.lower()
            or kw in e.meta.description.lower()
            or any(kw in p.lower() for p in e.meta.paper_refs)
        ]

    total = len(entries)
    page = entries[offset : offset + limit]
    items = [
        {
            "name": e.meta.name,
            "chinese_name": e.meta.chinese_name,
            "category": e.meta.category,
            "direction": e.meta.direction,
            "description": e.meta.description,
            "paper_refs": list(e.meta.paper_refs),
            "jq_dependencies": list(e.meta.jq_dependencies),
        }
        for e in page
    ]
    has_more = total > offset + len(items)
    return {
        "total": total,
        "count": len(items),
        "offset": offset,
        "limit": limit,
        "has_more": has_more,
        "next_offset": offset + len(items) if has_more else None,
        "items": items,
    }


# ---------------------------------------------------------------------------
# 2. jq_get_factor
# ---------------------------------------------------------------------------


class GetFactorInput(BaseModel):
    """``jq_get_factor`` 输入参数。"""

    model_config = ConfigDict(str_strip_whitespace=True, extra="forbid")

    name: str = Field(
        ...,
        description="因子注册名（registry key），全局唯一。",
        examples=["pe_ttm_inverse", "ret_12m_skip_1m", "roe_ttm"],
        min_length=1,
        max_length=80,
    )


def get_factor_impl(name: str) -> dict:
    """返回单个因子的 META + compute_jq 源码。"""
    import factors

    entry = factors.get(name)
    source = ""
    if entry.compute_jq is not None:
        try:
            source = inspect.getsource(entry.compute_jq)
        except (OSError, TypeError):
            source = ""
    return {
        "meta": {
            "name": entry.meta.name,
            "chinese_name": entry.meta.chinese_name,
            "category": entry.meta.category,
            "description": entry.meta.description,
            "direction": entry.meta.direction,
            "paper_refs": list(entry.meta.paper_refs),
            "jq_dependencies": list(entry.meta.jq_dependencies),
            "recommended_neutralization": list(entry.meta.recommended_neutralization),
            "universe_hint": entry.meta.universe_hint,
            "known_issues": list(entry.meta.known_issues),
        },
        "compute_jq_source": source,
        "module": entry.module,
    }


# ---------------------------------------------------------------------------
# 3. jq_resolve_factor_id
# ---------------------------------------------------------------------------


class ResolveFactorIdInput(BaseModel):
    """``jq_resolve_factor_id`` 输入参数。"""

    model_config = ConfigDict(str_strip_whitespace=True, extra="forbid")

    name: str = Field(
        ...,
        description="本仓库注册的因子名（与 jq_get_factor 的 name 一致）。",
        examples=["pe_ttm_inverse", "ret_5d"],
        min_length=1,
        max_length=80,
    )


def resolve_factor_id_impl(name: str) -> dict:
    """查询某个本地因子对应的聚宽官方 factor id。"""
    import factors

    call = factors.resolve(name)
    if call is None:
        return {
            "name": name,
            "has_native": False,
            "factor_id": None,
            "transform": None,
            "note": (
                "聚宽官方因子库无现成对应；请用 jq_get_factor 看本仓库的"
                " compute_jq 手算实现。"
            ),
        }
    return {
        "name": name,
        "has_native": True,
        "factor_id": call.factor_id,
        "transform": call.transform,
        "note": call.note,
        "usage_snippet": (
            f"from jqfactor import get_factor_values\n"
            f"data = get_factor_values(stocks, ['{call.factor_id}'], "
            f"end_date=context.previous_date, count=1)\n"
            f"series = data['{call.factor_id}'].iloc[-1]"
        ),
    }


# ---------------------------------------------------------------------------
# 4. jq_lint_strategy
# ---------------------------------------------------------------------------


class LintStrategyInput(BaseModel):
    """``jq_lint_strategy`` 输入参数。"""

    model_config = ConfigDict(extra="forbid")

    code: str = Field(
        ...,
        description="聚宽策略 Python 源代码（含 initialize / handle_data 等函数）。",
        min_length=1,
        max_length=200_000,
    )
    strict: bool = Field(
        default=False,
        description=(
            "是否启用 JQ005 白名单检查 — strict 模式下，看似聚宽 API 但不在"
            " KNOWN_APIS 中的函数调用会被标为 info。"
        ),
    )

    @field_validator("code")
    @classmethod
    def _strip_bom(cls, v: str) -> str:
        return v.lstrip("﻿")


def lint_strategy_impl(code: str, strict: bool = False) -> dict:
    """对一段聚宽策略代码跑 lint，返回 LintReport.to_dict()。"""
    from scripts.strategy_lint import lint_file

    tmp = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".py", delete=False, encoding="utf-8"
        ) as f:
            f.write(code)
            tmp = Path(f.name)
        report = lint_file(tmp, strict=strict)
        return report.to_dict()
    finally:
        if tmp is not None:
            try:
                tmp.unlink()
            except OSError:
                pass


# ---------------------------------------------------------------------------
# 5. jq_scaffold_strategy
# ---------------------------------------------------------------------------


class ScaffoldType(str, Enum):
    """支持的策略骨架类型，与 scripts/strategy_scaffold.py --type 对齐。"""

    BASIC = "basic"
    MULTI_FACTOR = "multi-factor"
    ROTATION = "rotation"
    MOMENTUM = "momentum"
    MEAN_REVERSION = "mean-reversion"


class ScaffoldStrategyInput(BaseModel):
    """``jq_scaffold_strategy`` 输入参数。"""

    model_config = ConfigDict(str_strip_whitespace=True, extra="forbid")

    type: ScaffoldType = Field(
        ...,
        description=(
            "策略骨架类型。basic = 单标的简单策略；multi-factor = 多因子选股；"
            "rotation = ETF 轮动；momentum = 动量；mean-reversion = 均值回归。"
        ),
    )
    security: Optional[str] = Field(
        default=None,
        description="主标的代码（如 000300.XSHG）；仅 basic / momentum / mean-reversion 用得到。",
        examples=["000300.XSHG", "510500.XSHG"],
        max_length=20,
    )
    hold_num: Optional[int] = Field(
        default=None,
        ge=1,
        le=100,
        description="持仓数量上限；multi-factor / rotation 才用。",
    )


def scaffold_strategy_impl(
    type: str,
    security: Optional[str] = None,
    hold_num: Optional[int] = None,
) -> dict:
    """通过 subprocess 调 scripts/strategy_scaffold.py 生成骨架。"""
    args = ["--type", type]
    if security:
        args += ["--security", security]
    if hold_num is not None:
        args += ["--hold-num", str(hold_num)]

    env = {**os.environ, "PYTHONIOENCODING": "utf-8"}
    proc = subprocess.run(
        [sys.executable, str(PROJECT_ROOT / "scripts" / "strategy_scaffold.py"), *args],
        capture_output=True,
        text=True,
        timeout=30,
        encoding="utf-8",
        errors="replace",
        env=env,
    )
    return {
        "code": proc.stdout or "",
        "stderr": proc.stderr or "",
        "returncode": proc.returncode,
    }


# ---------------------------------------------------------------------------
# 6. jq_search_api
# ---------------------------------------------------------------------------


class SearchApiInput(BaseModel):
    """``jq_search_api`` 输入参数。"""

    model_config = ConfigDict(str_strip_whitespace=True, extra="forbid")

    query: str = Field(
        ...,
        description="要在聚宽 API 文档里搜索的关键词或函数名。",
        examples=["get_price", "set_order_cost", "复权"],
        min_length=1,
        max_length=120,
    )
    context: int = Field(
        default=3,
        ge=0,
        le=20,
        description="每条命中前后保留的上下文行数。",
    )
    limit: int = Field(
        default=30,
        ge=1,
        le=200,
        description="返回的命中条数上限。",
    )


def search_api_impl(query: str, context: int = 3, limit: int = 30) -> List[dict]:
    """在 ``api文档/api.txt`` 里逐行匹配关键词，返回命中片段。"""
    api_txt = PROJECT_ROOT / "api文档" / "api.txt"
    if not api_txt.exists():
        return []
    lines = api_txt.read_text(encoding="utf-8").splitlines()
    q_lower = query.lower()
    hits: List[dict] = []
    for i, line in enumerate(lines):
        if q_lower in line.lower():
            start = max(0, i - context)
            end = min(len(lines), i + context + 1)
            hits.append(
                {
                    "line_number": i + 1,
                    "match": line,
                    "context": lines[start:end],
                }
            )
            if len(hits) >= limit:
                break
    return hits


# ---------------------------------------------------------------------------
# 7. jq_build_research_extract_prompt
# ---------------------------------------------------------------------------


class BuildResearchExtractPromptInput(BaseModel):
    """``jq_build_research_extract_prompt`` 输入参数。"""

    model_config = ConfigDict(extra="forbid")

    text: str = Field(
        ...,
        description="研报正文（已抽取后的纯文本）。建议先在客户端做截断。",
        min_length=20,
        max_length=200_000,
    )
    source_hint: Optional[str] = Field(
        default=None,
        description="研报来源提示（券商 + 标题 + 日期），帮助 LLM 校准。",
        examples=["中信证券《选股因子系列》2024-09"],
        max_length=200,
    )


def extract_factors_from_research_impl(
    text: str, source_hint: Optional[str] = None
) -> dict:
    """构造可直接发给 LLM 的研报抽取 prompt。本工具不直接调 LLM。"""
    from research_importer.parser.prompts import build_extract_prompt

    system, user = build_extract_prompt(text, source_hint=source_hint)
    return {
        "system_prompt": system,
        "user_prompt": user,
        "expected_schema": "research_importer.parser.schema.ExtractedStrategy",
        "next_step": (
            "把 system_prompt + user_prompt 发给 Claude / GPT / DeepSeek，"
            "拿到 JSON 后用 ExtractedStrategy.from_json 反序列化，再用 "
            "research_importer.generator.write_strategy 生成代码。"
        ),
    }


# ---------------------------------------------------------------------------
# FastMCP 注册
# ---------------------------------------------------------------------------


def _readonly_annotations(title: str) -> dict:
    """所有本服务工具都是只读，统一注释模板。"""
    return {
        "title": title,
        "readOnlyHint": True,
        "destructiveHint": False,
        "idempotentHint": True,
        "openWorldHint": False,
    }


def build_server():
    """构造 FastMCP 实例并注册全部 tool。

    Raises:
        ImportError: 未安装 mcp 包。
    """
    if not _mcp_available():
        raise ImportError(
            "未安装 mcp 包，无法启动 server。\n"
            "Suggested fix: pip install \"mcp[cli]\""
        )

    from mcp.server.fastmcp import FastMCP

    app = FastMCP(SERVER_NAME)

    # ---- jq_list_factors ----
    @app.tool(
        name="jq_list_factors",
        annotations=_readonly_annotations("List JoinQuant factors"),
    )
    async def jq_list_factors(params: ListFactorsInput) -> str:
        """列出 joinquant-skill 注册的因子，支持类别 / 关键词过滤 + 分页。

        本工具只读，不会改任何文件。

        Args:
            params (ListFactorsInput): 见 schema。

        Returns:
            str: JSON 字符串，包含 total / count / offset / limit / has_more /
                next_offset / items[]。
                items[] 每项含 name / chinese_name / category / direction /
                description / paper_refs / jq_dependencies。

        Examples:
            - "列出所有价值因子" → category="value"
            - "搜动量相关" → keyword="momentum"
        """
        try:
            payload = list_factors_impl(
                category=params.category,
                keyword=params.keyword,
                limit=params.limit,
                offset=params.offset,
            )
            return json.dumps(payload, ensure_ascii=False, indent=2)
        except Exception as exc:  # noqa: BLE001
            return _format_error(
                exc,
                hint="确认 category 在合法枚举内；keyword 不超过 80 字。",
            )

    # ---- jq_get_factor ----
    @app.tool(
        name="jq_get_factor",
        annotations=_readonly_annotations("Get factor metadata + source"),
    )
    async def jq_get_factor(params: GetFactorInput) -> str:
        """返回单个因子的完整 META + compute_jq 源代码。

        Args:
            params (GetFactorInput): 含 name（因子注册名）。

        Returns:
            str: JSON 字符串，键包括 meta（含 paper_refs / known_issues 等）、
                compute_jq_source（可直接复制到聚宽编辑器的函数源码）、module。

        Errors:
            - 未注册的 name → 返回 "Error: ... Suggested fix: 用 jq_list_factors 找正确名字。"
        """
        try:
            return json.dumps(
                get_factor_impl(params.name), ensure_ascii=False, indent=2
            )
        except KeyError as exc:
            return _format_error(
                exc,
                hint="用 jq_list_factors 列出可用的因子名再重试。",
            )
        except Exception as exc:  # noqa: BLE001
            return _format_error(exc)

    # ---- jq_resolve_factor_id ----
    @app.tool(
        name="jq_resolve_factor_id",
        annotations=_readonly_annotations("Resolve to JoinQuant native factor id"),
    )
    async def jq_resolve_factor_id(params: ResolveFactorIdInput) -> str:
        """把本仓库因子名翻译为聚宽官方 ``get_factor_values`` 用的 factor id。

        Args:
            params (ResolveFactorIdInput): 含 name。

        Returns:
            str: JSON 字符串，含 has_native / factor_id / transform / note /
                usage_snippet（可粘贴的最小调用示例）。

        Examples:
            - name="pe_ttm_inverse" → factor_id="EP"
            - name="ret_5d" → has_native=False（聚宽无对应，需手算）
        """
        try:
            return json.dumps(
                resolve_factor_id_impl(params.name),
                ensure_ascii=False,
                indent=2,
            )
        except Exception as exc:  # noqa: BLE001
            return _format_error(
                exc,
                hint="先用 jq_list_factors 拿到合法的 name 再调本工具。",
            )

    # ---- jq_lint_strategy ----
    @app.tool(
        name="jq_lint_strategy",
        annotations=_readonly_annotations("Lint JoinQuant strategy code"),
    )
    async def jq_lint_strategy(params: LintStrategyInput) -> str:
        """对一段聚宽策略代码跑静态 lint。

        检测项见 ``scripts/strategy_lint.py``：

        - JQ001 hallucinated API（25+ 条黑名单）
        - JQ002 已废弃 API
        - JQ003 ``get_price`` 未来函数风险
        - JQ004 在 before/after_trading 时段下单
        - JQ005 strict 模式下未识别的"看似聚宽 API"调用
        - JQ010 / JQ011 / JQ012 缺关键 set_* 调用

        Args:
            params (LintStrategyInput): 含 code、strict。

        Returns:
            str: JSON 字符串，含 passed / error_count / warning_count /
                issues[]（severity / line / col / code / message / fix_hint）/
                api_calls。
        """
        try:
            return json.dumps(
                lint_strategy_impl(params.code, strict=params.strict),
                ensure_ascii=False,
                indent=2,
            )
        except Exception as exc:  # noqa: BLE001
            return _format_error(
                exc,
                hint="确认 code 是合法 Python 源代码字符串（不要 base64）。",
            )

    # ---- jq_scaffold_strategy ----
    @app.tool(
        name="jq_scaffold_strategy",
        annotations=_readonly_annotations("Generate JoinQuant strategy skeleton"),
    )
    async def jq_scaffold_strategy(params: ScaffoldStrategyInput) -> str:
        """按 templates/01-05 的模板生成一份聚宽策略骨架。

        Args:
            params (ScaffoldStrategyInput): 含 type / security / hold_num。

        Returns:
            str: JSON 字符串，含 code（生成的源代码字符串）、stderr、returncode。
                returncode != 0 时应当读 stderr 找原因。
        """
        try:
            return json.dumps(
                scaffold_strategy_impl(
                    type=params.type.value,
                    security=params.security,
                    hold_num=params.hold_num,
                ),
                ensure_ascii=False,
                indent=2,
            )
        except subprocess.TimeoutExpired as exc:
            return _format_error(
                exc, hint="模板生成 30s 内未完成，可能是 IO 卡死；重试一次。"
            )
        except Exception as exc:  # noqa: BLE001
            return _format_error(
                exc,
                hint="type 必须在 basic / multi-factor / rotation / momentum / mean-reversion 中。",
            )

    # ---- jq_search_api ----
    @app.tool(
        name="jq_search_api",
        annotations=_readonly_annotations("Search JoinQuant API docs"),
    )
    async def jq_search_api(params: SearchApiInput) -> str:
        """在 ``api文档/api.txt`` 里搜函数名或关键词，返回带上下文的命中片段。

        Args:
            params (SearchApiInput): 含 query / context / limit。

        Returns:
            str: JSON 字符串，含 hits[]（line_number / match / context[]）。
                未命中时返回空数组。
        """
        try:
            hits = search_api_impl(
                query=params.query,
                context=params.context,
                limit=params.limit,
            )
            return json.dumps({"hits": hits, "count": len(hits)}, ensure_ascii=False, indent=2)
        except Exception as exc:  # noqa: BLE001
            return _format_error(exc)

    # ---- jq_build_research_extract_prompt ----
    @app.tool(
        name="jq_build_research_extract_prompt",
        annotations=_readonly_annotations("Build LLM prompt for research extract"),
    )
    async def jq_build_research_extract_prompt(
        params: BuildResearchExtractPromptInput,
    ) -> str:
        """把研报正文构造为可直接发给 LLM 的 system+user prompt。

        本工具不调任何 LLM —— 把 prompt 返回给调用方，让客户端用自己的 API key
        调 Claude / GPT / DeepSeek。这样：

        1. 服务不持有调用方密钥；
        2. cost 由调用方控制；
        3. 客户端可以挑模型 / 自定义重试 / 自定义后处理。

        Args:
            params (BuildResearchExtractPromptInput): 含 text、source_hint。

        Returns:
            str: JSON 字符串，含 system_prompt / user_prompt /
                expected_schema / next_step。
        """
        try:
            return json.dumps(
                extract_factors_from_research_impl(
                    text=params.text, source_hint=params.source_hint
                ),
                ensure_ascii=False,
                indent=2,
            )
        except Exception as exc:  # noqa: BLE001
            return _format_error(
                exc,
                hint="text 不能为空，长度建议 < 200K 字符；上传前请去掉页眉页脚。",
            )

    return app


# ---------------------------------------------------------------------------
# 主入口
# ---------------------------------------------------------------------------


def main() -> int:
    """命令行入口：``python -m jqskill_mcp.server``。"""
    if not _mcp_available():
        sys.stderr.write(
            "joinquant-skill MCP server 需要 mcp 包。\n"
            'Suggested fix: pip install "mcp[cli]"\n'
        )
        return 1

    logging.basicConfig(
        level=os.environ.get("JQSKILL_MCP_LOG_LEVEL", "WARNING"),
        format="%(asctime)s %(name)s %(levelname)s %(message)s",
    )
    app = build_server()
    log.info("Starting %s v%s (stdio transport)", SERVER_NAME, SERVER_VERSION)
    app.run()  # 默认 stdio
    return 0


if __name__ == "__main__":
    sys.exit(main())
