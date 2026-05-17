"""
mcp/server.py — joinquant-skill 的 MCP server。

把整个 skill 的能力暴露成 MCP tools，让任何 MCP 客户端（Claude Desktop /
Cursor / 自家 chatbot 等）都能调用：

- `list_factors` — 列出已注册因子，可按 category / keyword 过滤
- `get_factor` — 单个因子的完整 META + compute_jq 源代码
- `lint_strategy` — 对一段聚宽策略代码跑 lint
- `scaffold_strategy` — 按模板生成一个聚宽策略骨架
- `search_api` — 在 references / api.txt 里搜函数
- `extract_factors_from_research` — 把一段研报文本喂给 LLM，返回 ExtractedStrategy JSON

运行
----
```bash
pip install "mcp[cli]"
python -m mcp.server
```

或者 Claude Desktop 的 `claude_desktop_config.json`：

```json
{
  "mcpServers": {
    "joinquant-skill": {
      "command": "python",
      "args": ["-m", "mcp.server"],
      "cwd": "<你 clone 的 joinquant-skill 路径>"
    }
  }
}
```
"""
from __future__ import annotations

import inspect
import json
import sys
from pathlib import Path
from typing import Optional


# 让 `python -m mcp.server` 可直接跑
PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))


def _check_mcp_available() -> bool:
    try:
        import mcp  # noqa: F401
        return True
    except ImportError:
        return False


# ---------------------------------------------------------------------------
# Tool 实现（脱离 MCP 框架也能单独调，便于测试）
# ---------------------------------------------------------------------------

def list_factors_impl(category: Optional[str] = None, keyword: Optional[str] = None) -> list[dict]:
    """列出已注册因子。可选按 category / keyword 过滤。"""
    import factors
    entries = factors.all_factors()
    if category:
        entries = [e for e in entries if e.meta.category == category]
    if keyword:
        kw = keyword.lower()
        entries = [
            e for e in entries
            if kw in e.meta.name.lower()
            or kw in e.meta.chinese_name.lower()
            or kw in e.meta.description.lower()
        ]
    return [
        {
            "name": e.meta.name,
            "chinese_name": e.meta.chinese_name,
            "category": e.meta.category,
            "direction": e.meta.direction,
            "description": e.meta.description,
            "paper_refs": list(e.meta.paper_refs),
        }
        for e in entries
    ]


def get_factor_impl(name: str) -> dict:
    """单个因子的 META + compute_jq 源代码。"""
    import factors
    entry = factors.get(name)
    meta_dict = {
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
    }
    source = ""
    if entry.compute_jq:
        try:
            source = inspect.getsource(entry.compute_jq)
        except (OSError, TypeError):
            source = ""
    return {"meta": meta_dict, "compute_jq_source": source, "module": entry.module}


def lint_strategy_impl(code: str) -> dict:
    """对一段聚宽策略代码跑 lint。返回 LintReport 的 dict 形式。"""
    import tempfile
    from scripts.strategy_lint import lint_file
    with tempfile.NamedTemporaryFile(mode="w", suffix=".py", delete=False, encoding="utf-8") as f:
        f.write(code)
        tmp = Path(f.name)
    try:
        report = lint_file(tmp, strict=False)
        return report.to_dict()
    finally:
        try:
            tmp.unlink()
        except OSError:
            pass


def scaffold_strategy_impl(type: str, security: Optional[str] = None,
                           hold_num: Optional[int] = None) -> dict:
    """生成策略骨架代码（不写文件，返回 dict）。"""
    args = ["--type", type]
    if security:
        args += ["--security", security]
    if hold_num is not None:
        args += ["--hold-num", str(hold_num)]
    import subprocess
    proc = subprocess.run(
        [sys.executable, str(PROJECT_ROOT / "scripts" / "strategy_scaffold.py"), *args],
        capture_output=True, text=True, timeout=30,
    )
    return {
        "code": proc.stdout,
        "stderr": proc.stderr,
        "returncode": proc.returncode,
    }


def search_api_impl(query: str, context: int = 3) -> list[dict]:
    """在 api文档/api.txt 里搜关键词。"""
    api_txt = PROJECT_ROOT / "api文档" / "api.txt"
    if not api_txt.exists():
        return []
    lines = api_txt.read_text(encoding="utf-8").splitlines()
    hits = []
    q_lower = query.lower()
    for i, line in enumerate(lines):
        if q_lower in line.lower():
            start = max(0, i - context)
            end = min(len(lines), i + context + 1)
            hits.append({
                "line_number": i + 1,
                "match": line,
                "context": lines[start:end],
            })
            if len(hits) >= 30:
                break
    return hits


def extract_factors_from_research_impl(text: str, source_hint: Optional[str] = None) -> dict:
    """
    返回 prompt（**不直接调 LLM**） — 调用方拿到 prompt 后自行决定调哪个 LLM。

    这样 MCP server 自身**零 LLM 依赖**，cost 也由调用方控制。
    """
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
# MCP server 注册
# ---------------------------------------------------------------------------

def build_server():
    """构建 MCP server，注册所有 tool。"""
    if not _check_mcp_available():
        raise ImportError(
            'mcp 包未安装。运行：pip install "mcp[cli]"'
        )

    from mcp.server.fastmcp import FastMCP

    app = FastMCP("joinquant-skill")

    @app.tool()
    def list_factors(category: Optional[str] = None, keyword: Optional[str] = None) -> list[dict]:
        """列出已注册的聚宽策略因子，可按 category（value/momentum/quality/...）或关键词过滤。"""
        return list_factors_impl(category=category, keyword=keyword)

    @app.tool()
    def get_factor(name: str) -> dict:
        """获取单个因子的完整元数据 + compute_jq 源代码。"""
        return get_factor_impl(name)

    @app.tool()
    def lint_strategy(code: str) -> dict:
        """对一段聚宽策略代码跑静态 lint，返回 errors/warnings/api_calls。"""
        return lint_strategy_impl(code)

    @app.tool()
    def scaffold_strategy(type: str, security: Optional[str] = None,
                          hold_num: Optional[int] = None) -> dict:
        """按模板生成聚宽策略骨架。type ∈ {basic, multi-factor, rotation, momentum, mean-reversion}。"""
        return scaffold_strategy_impl(type, security=security, hold_num=hold_num)

    @app.tool()
    def search_api(query: str, context: int = 3) -> list[dict]:
        """在聚宽 API 文档里搜函数 / 关键词。"""
        return search_api_impl(query, context=context)

    @app.tool()
    def extract_factors_from_research(text: str, source_hint: Optional[str] = None) -> dict:
        """
        从研报文本抽取量化因子 → 返回 LLM prompt（不直接调 LLM）。

        调用方拿 prompt 后自己调 Claude / GPT / DeepSeek 等。
        """
        return extract_factors_from_research_impl(text, source_hint=source_hint)

    return app


def main() -> int:
    if not _check_mcp_available():
        print(
            'joinquant-skill MCP server 需要安装 mcp：\n'
            '    pip install "mcp[cli]"\n',
            file=sys.stderr,
        )
        return 1
    app = build_server()
    # FastMCP 的 run 默认 stdio transport — 适配 Claude Desktop / Cursor
    app.run()
    return 0


if __name__ == "__main__":
    sys.exit(main())
