"""
research_importer CLI — 研报复现端到端工作流。

启用方式
========
.. code-block:: bash

    python -m research_importer --help

子命令
======

1) ``extract``：把 PDF 抽成纯文本

   .. code-block:: bash

       python -m research_importer extract path/to/report.pdf -o report.txt

2) ``fetch``：用 akshare 抓某只股票最近的研报清单（带摘要）

   .. code-block:: bash

       python -m research_importer fetch --code 600519 --limit 5 -o moutai.txt

3) ``build-prompt``：把文本变成可直接发给 Claude / GPT 的 system + user prompt

   .. code-block:: bash

       python -m research_importer build-prompt report.txt \\
           --source "中信证券《选股因子系列》2024-09" \\
           -o prompt.json

4) ``codegen``：拿 LLM 抽取出的 JSON 生成聚宽策略代码

   .. code-block:: bash

       python -m research_importer codegen extracted.json -o strategies/my_strat/

   默认拒绝未知非 native 因子，避免静默生成全 0 排序；只想先拿骨架时可显式
   加 ``--allow-placeholders``，再人工补完 NaN/TODO 占位。

5) ``pipeline``：流水线（要求你自己处理 LLM 这一步）

   .. code-block:: bash

       # 输出：text → prompt → 提示你把 prompt 发给 LLM →
       #       拿 JSON 回来塞进文件 → codegen 生成策略
       python -m research_importer pipeline path/to/report.pdf -o strategies/my_strat/

总体设计
========
所有「调 LLM」的步骤都**不内置**到本 CLI 里——本工具不持有用户的 API key。
你可以把 prompt 通过任意客户端（Claude Desktop / OpenAI Playground / 本地 ollama）
发给 LLM，把回的 JSON 存成文件再调 ``codegen``。

详细工作流见 ``WORKFLOW.md`` 的「研报复现」章节。
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from research_importer.extractor import (
    PDFExtractionError,
    clean_text,
    extract_text,
)
from research_importer.parser import (
    ExtractedStrategy,
    build_extract_prompt,
)


# ---------------------------------------------------------------------------
# extract — PDF → 文本
# ---------------------------------------------------------------------------


def _cmd_extract(args) -> int:
    src = Path(args.pdf)
    if not src.exists():
        print(f"[error] 文件不存在：{src}", file=sys.stderr)
        return 1
    try:
        text = extract_text(src)
    except PDFExtractionError as exc:
        print(f"[error] {exc}", file=sys.stderr)
        return 2
    text = clean_text(text)
    if args.output:
        out = Path(args.output)
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(text, encoding="utf-8")
        print(f"[ok] {len(text)} 字符已写入 {out}", file=sys.stderr)
    else:
        sys.stdout.write(text)
    return 0


# ---------------------------------------------------------------------------
# fetch — akshare 抓研报清单
# ---------------------------------------------------------------------------


def _cmd_fetch(args) -> int:
    try:
        from research_importer.extractor.akshare_loader import (
            AkshareNotInstalled,
            fetch_stock_reports,
            summary_to_extractable_text,
        )
    except ImportError as exc:
        print(f"[error] {exc}", file=sys.stderr)
        return 2

    try:
        reports = fetch_stock_reports(args.code, limit=args.limit)
    except AkshareNotInstalled as exc:
        print(f"[error] {exc}", file=sys.stderr)
        return 2
    except RuntimeError as exc:
        print(f"[error] {exc}", file=sys.stderr)
        return 3

    if not reports:
        print(f"[warn] akshare 没返回 {args.code} 的研报，可能代码错或近期无研报。",
              file=sys.stderr)
        return 0

    if args.format == "json":
        payload = [r.to_dict() for r in reports]
        text = json.dumps(payload, ensure_ascii=False, indent=2)
    else:
        # text 模式：每条研报转成可抽取文本，用分隔线串起来
        text = "\n\n" + ("=" * 60 + "\n").join(
            summary_to_extractable_text(r) + "\n" for r in reports
        )

    if args.output:
        out = Path(args.output)
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(text, encoding="utf-8")
        print(
            f"[ok] 拉到 {len(reports)} 篇研报，已写入 {out}",
            file=sys.stderr,
        )
    else:
        sys.stdout.write(text)
    return 0


# ---------------------------------------------------------------------------
# build-prompt — text → LLM prompt
# ---------------------------------------------------------------------------


def _cmd_build_prompt(args) -> int:
    src = Path(args.text)
    if not src.exists():
        print(f"[error] 文件不存在：{src}", file=sys.stderr)
        return 1
    text = src.read_text(encoding="utf-8")
    system, user = build_extract_prompt(text, source_hint=args.source)
    payload = {
        "system_prompt": system,
        "user_prompt": user,
        "expected_schema": "research_importer.parser.schema.ExtractedStrategy",
        "next_step": (
            "把 system_prompt 与 user_prompt 发给 Claude / GPT / DeepSeek，"
            "把模型输出的 JSON 存成文件再调 `python -m research_importer codegen`。"
        ),
    }
    out_text = json.dumps(payload, ensure_ascii=False, indent=2)
    if args.output:
        out = Path(args.output)
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(out_text, encoding="utf-8")
        print(f"[ok] prompt 已写入 {out}", file=sys.stderr)
    else:
        sys.stdout.write(out_text)
    return 0


# ---------------------------------------------------------------------------
# codegen — JSON → 聚宽策略代码
# ---------------------------------------------------------------------------


def _cmd_codegen(args) -> int:
    from research_importer.generator import write_strategy

    src = Path(args.json_file)
    if not src.exists():
        print(f"[error] 文件不存在：{src}", file=sys.stderr)
        return 1
    try:
        payload = json.loads(src.read_text(encoding="utf-8-sig"))
    except json.JSONDecodeError as exc:
        print(f"[error] {src} 不是合法 JSON：{exc}", file=sys.stderr)
        return 2

    try:
        strategy = ExtractedStrategy.from_dict(payload)
    except Exception as exc:
        print(f"[error] schema 反序列化失败：{exc}", file=sys.stderr)
        return 3

    out_dir = Path(args.output)
    try:
        code_path = write_strategy(
            strategy,
            out_dir,
            hold_num=args.hold_num,
            allow_placeholders=args.allow_placeholders,
        )
    except ValueError as exc:
        print(f"[error] 生成策略失败：{exc}", file=sys.stderr)
        return 5
    print(f"[ok] 生成策略：{code_path}", file=sys.stderr)
    print(f"[ok] 元数据：{out_dir / '_meta.yaml'}", file=sys.stderr)

    # 顺手跑 lint
    if not args.no_lint:
        from scripts.strategy_lint import lint_file, render_report
        report = lint_file(code_path, strict=False)
        print("\n" + render_report(report), file=sys.stderr)
        if not report.passed:
            return 4
    return 0


# ---------------------------------------------------------------------------
# pipeline — extract → prompt → (你调 LLM) → codegen
# ---------------------------------------------------------------------------


def _cmd_pipeline(args) -> int:
    out_dir = Path(args.output)
    out_dir.mkdir(parents=True, exist_ok=True)

    # Step 1: extract
    src = Path(args.pdf)
    if not src.exists():
        print(f"[error] 文件不存在：{src}", file=sys.stderr)
        return 1
    try:
        text = clean_text(extract_text(src))
    except PDFExtractionError as exc:
        print(f"[error] PDF 抽取失败：{exc}", file=sys.stderr)
        return 2

    text_path = out_dir / "01_extracted_text.txt"
    text_path.write_text(text, encoding="utf-8")
    print(f"[step 1] 已抽取 {len(text)} 字符 → {text_path}", file=sys.stderr)

    # Step 2: build prompt
    system, user = build_extract_prompt(text, source_hint=args.source)
    prompt_path = out_dir / "02_llm_prompt.json"
    prompt_path.write_text(
        json.dumps(
            {"system_prompt": system, "user_prompt": user},
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )
    print(f"[step 2] LLM prompt 已写入 → {prompt_path}", file=sys.stderr)

    # Step 3: 提示用户去调 LLM
    extracted_json_path = out_dir / "03_extracted.json"
    print("", file=sys.stderr)
    print("=" * 60, file=sys.stderr)
    print("现在需要你手动完成「调 LLM」这一步：", file=sys.stderr)
    print(
        f"  1. 打开 {prompt_path}",
        file=sys.stderr,
    )
    print(
        "  2. 把 system_prompt 和 user_prompt 发给 Claude / GPT / DeepSeek",
        file=sys.stderr,
    )
    print(
        f"  3. 把模型输出的 JSON 存到 {extracted_json_path}",
        file=sys.stderr,
    )
    print(
        "  4. 重新跑：",
        file=sys.stderr,
    )
    print(
        f"     python -m research_importer codegen {extracted_json_path} -o {out_dir}/strategy",
        file=sys.stderr,
    )
    print("=" * 60, file=sys.stderr)

    # 已经存在的 extracted.json 就顺手 codegen
    if extracted_json_path.exists():
        print(
            f"\n[step 3] 检测到 {extracted_json_path} 已存在，自动 codegen ...",
            file=sys.stderr,
        )
        args.json_file = str(extracted_json_path)
        args.output = str(out_dir / "strategy")
        args.no_lint = False
        return _cmd_codegen(args)

    return 0


# ---------------------------------------------------------------------------
# argparse 入口
# ---------------------------------------------------------------------------


def _build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="research_importer",
        description="研报 → 聚宽策略代码 端到端工作流（不内置 LLM 调用）",
    )
    sub = p.add_subparsers(dest="cmd", required=True)

    sp = sub.add_parser("extract", help="PDF → 纯文本")
    sp.add_argument("pdf", help="本地 PDF 文件路径")
    sp.add_argument("-o", "--output", help="输出文本文件；缺省走 stdout")
    sp.set_defaults(func=_cmd_extract)

    sp = sub.add_parser("fetch", help="用 akshare 抓某股票研报清单 + 摘要")
    sp.add_argument("--code", required=True,
                    help="股票代码 6 位（如 600519、000001），不带交易所后缀")
    sp.add_argument("--limit", type=int, default=20,
                    help="最多返回多少篇研报")
    sp.add_argument("--format", choices=["text", "json"], default="text",
                    help="输出格式：text 适合直接喂 LLM，json 适合二次处理")
    sp.add_argument("-o", "--output", help="输出文件；缺省 stdout")
    sp.set_defaults(func=_cmd_fetch)

    sp = sub.add_parser("build-prompt", help="文本 → LLM system+user prompt")
    sp.add_argument("text", help="包含研报文本的本地文件")
    sp.add_argument("--source", help="研报来源（如券商名 + 标题 + 日期），帮助 LLM 校准")
    sp.add_argument("-o", "--output", help="输出 JSON；缺省 stdout")
    sp.set_defaults(func=_cmd_build_prompt)

    sp = sub.add_parser("codegen", help="LLM 抽取的 JSON → 聚宽策略 .py + _meta.yaml")
    sp.add_argument("json_file", help="LLM 输出的 JSON（ExtractedStrategy 形式）")
    sp.add_argument("-o", "--output", required=True, help="输出目录")
    sp.add_argument("--hold-num", type=int, default=20, help="持仓数量上限")
    sp.add_argument("--no-lint", action="store_true",
                    help="生成后不自动跑 strategy_lint")
    sp.add_argument("--allow-placeholders", action="store_true",
                    help="允许未知非 native 因子生成 NaN/TODO 占位；默认直接失败，避免静默全 0")
    sp.set_defaults(func=_cmd_codegen)

    sp = sub.add_parser("pipeline",
                        help="一条龙：extract → build-prompt → (你调 LLM) → codegen")
    sp.add_argument("pdf", help="本地 PDF")
    sp.add_argument("-o", "--output", required=True,
                    help="输出目录（会写入 01_extracted_text.txt / 02_llm_prompt.json 等）")
    sp.add_argument("--source", help="研报来源")
    sp.add_argument("--hold-num", type=int, default=20)
    sp.add_argument("--no-lint", action="store_true")
    sp.add_argument("--allow-placeholders", action="store_true",
                    help="允许未知非 native 因子生成 NaN/TODO 占位；默认直接失败")
    sp.set_defaults(func=_cmd_pipeline)

    return p


def main(argv=None) -> int:
    parser = _build_parser()
    args = parser.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
