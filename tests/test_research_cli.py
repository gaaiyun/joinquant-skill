"""research_importer 端到端 CLI 测试。

不依赖真实 PDF / 真实 LLM / 真实 akshare 网络访问；通过 monkeypatch + 临时
文件验证子命令链路。
"""
from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))


def _run_cli(args: list[str]) -> subprocess.CompletedProcess:
    """跑 python -m research_importer ...，返回 CompletedProcess。"""
    return subprocess.run(
        [sys.executable, "-m", "research_importer", *args],
        cwd=PROJECT_ROOT,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        env={"PYTHONIOENCODING": "utf-8", **__import__("os").environ},
        timeout=60,
    )


# ---------------------------------------------------------------------------
# --help 路径（也校验 subcommand 注册齐全）
# ---------------------------------------------------------------------------


def test_cli_help_lists_all_subcommands():
    p = _run_cli(["--help"])
    assert p.returncode == 0
    for sub in ("extract", "fetch", "build-prompt", "codegen", "pipeline"):
        assert sub in p.stdout, f"--help 没列出 {sub}"


@pytest.mark.parametrize("sub", ["extract", "fetch", "build-prompt", "codegen", "pipeline"])
def test_cli_subcommand_help(sub):
    p = _run_cli([sub, "--help"])
    assert p.returncode == 0
    assert "usage:" in p.stdout.lower()


# ---------------------------------------------------------------------------
# build-prompt：纯文本 → JSON prompt
# ---------------------------------------------------------------------------


def test_build_prompt_writes_valid_json(tmp_path):
    text_file = tmp_path / "report.txt"
    text_file.write_text("一段中文研报正文，提到 ROE_TTM 和 12-1 动量两个因子。", encoding="utf-8")
    out_file = tmp_path / "prompt.json"

    p = _run_cli([
        "build-prompt", str(text_file),
        "--source", "测试券商《示例研报》2024-09",
        "-o", str(out_file),
    ])
    assert p.returncode == 0, p.stderr

    payload = json.loads(out_file.read_text(encoding="utf-8"))
    assert "system_prompt" in payload
    assert "user_prompt" in payload
    # 研报正文与来源都应被嵌入到 user_prompt
    assert "ROE_TTM" in payload["user_prompt"]
    assert "测试券商" in payload["user_prompt"]


# ---------------------------------------------------------------------------
# codegen：JSON → 聚宽 strategy.py + _meta.yaml + 自动 lint
# ---------------------------------------------------------------------------


@pytest.fixture
def sample_extracted_json(tmp_path):
    p = tmp_path / "extracted.json"
    payload = {
        "title": "测试策略",
        "source": "ut",
        "rebalance_freq": "monthly",
        "universe": "中证 800",
        "primary_factors": [
            {"name": "roe_ttm", "chinese_name": "TTM ROE", "category": "quality",
             "definition": "x", "direction": "ascending", "weight": 0.5},
            {"name": "pe_ttm_inverse", "chinese_name": "TTM EP", "category": "value",
             "definition": "y", "direction": "ascending", "weight": 0.5},
        ],
        "benchmark": "000906.XSHG",
    }
    p.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
    return p


def test_codegen_produces_lint_clean_strategy(tmp_path, sample_extracted_json):
    out_dir = tmp_path / "out"
    p = _run_cli([
        "codegen", str(sample_extracted_json),
        "-o", str(out_dir),
        "--hold-num", "10",
    ])
    assert p.returncode == 0, p.stderr
    assert (out_dir / "strategy.py").exists()
    assert (out_dir / "_meta.yaml").exists()
    code = (out_dir / "strategy.py").read_text(encoding="utf-8")
    # 生成代码必须真的调聚宽 API
    assert "from jqfactor import get_factor_values" in code
    assert "context.previous_date" in code
    # native id 映射正确（ROE_TTM / EP）
    assert "ROE_TTM" in code
    assert "EP" in code


def test_codegen_invalid_json_exits_nonzero(tmp_path):
    bad = tmp_path / "bad.json"
    bad.write_text("not json at all", encoding="utf-8")
    out_dir = tmp_path / "out"
    p = _run_cli(["codegen", str(bad), "-o", str(out_dir)])
    assert p.returncode != 0


def test_codegen_accepts_utf8_bom_json(tmp_path, sample_extracted_json):
    """Windows PowerShell 5 的 UTF8 文件常带 BOM，codegen 应能读取。"""
    payload = sample_extracted_json.read_bytes()
    bom_json = tmp_path / "bom.json"
    bom_json.write_bytes(b"\xef\xbb\xbf" + payload)
    out_dir = tmp_path / "out-bom"

    p = _run_cli(["codegen", str(bom_json), "-o", str(out_dir)])
    assert p.returncode == 0, p.stderr
    assert (out_dir / "strategy.py").exists()


def test_codegen_missing_file_exits_nonzero(tmp_path):
    p = _run_cli(["codegen", str(tmp_path / "nope.json"), "-o", str(tmp_path / "out")])
    assert p.returncode != 0


# ---------------------------------------------------------------------------
# extract：缺文件 → 友好错误
# ---------------------------------------------------------------------------


def test_extract_missing_file_exits_nonzero(tmp_path):
    p = _run_cli(["extract", str(tmp_path / "nope.pdf")])
    assert p.returncode != 0
    assert "不存在" in p.stderr or "not found" in p.stderr.lower()


# ---------------------------------------------------------------------------
# pipeline：能跑到提示用户调 LLM 的那一步
# ---------------------------------------------------------------------------


def test_pipeline_missing_pdf_exits_nonzero(tmp_path):
    p = _run_cli(["pipeline", str(tmp_path / "nope.pdf"), "-o", str(tmp_path / "out")])
    assert p.returncode != 0


# ---------------------------------------------------------------------------
# Sample case：examples/case-research-replication/sample_extracted.json 必须
# 能被 codegen 处理通过
# ---------------------------------------------------------------------------


def test_sample_extracted_json_works_with_codegen(tmp_path):
    sample = PROJECT_ROOT / "examples" / "case-research-replication" / "sample_extracted.json"
    if not sample.exists():
        pytest.skip("sample json 不存在")
    out_dir = tmp_path / "out"
    p = _run_cli(["codegen", str(sample), "-o", str(out_dir), "--hold-num", "30"])
    assert p.returncode == 0, p.stderr
    assert (out_dir / "strategy.py").exists()
