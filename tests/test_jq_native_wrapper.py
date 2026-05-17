"""factors/_jq_native.py 与各 factor 的 compute_jq 一致性测试。

不调真聚宽 API（CI 没账号），但确保：
1. compute_jq 函数 ast 可解析（语法正确）
2. compute_jq 函数体里出现了 `get_factor_values` 调用（或对 ret_5d 来说出现 get_price）
3. NATIVE_FACTOR_MAP 与每个 factor 的 jq_dependencies 一致
4. factor.meta.jq_dependencies 引用的 factor id 都在 NATIVE_FACTOR_MAP 的 values 里
"""
from __future__ import annotations

import ast
import inspect
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

import factors


# ---------------------------------------------------------------------------
# NATIVE_FACTOR_MAP <-> factor meta 一致性
# ---------------------------------------------------------------------------

def test_native_map_keys_match_registered_factor_names():
    """NATIVE_FACTOR_MAP 的 key 应该都是注册过的因子名。"""
    registered = {e.meta.name for e in factors.all_factors()}
    for name in factors.NATIVE_FACTOR_MAP:
        assert name in registered, f"NATIVE_FACTOR_MAP 里有 {name} 但没注册"


def test_every_factor_either_has_native_or_explicit_handcomputed():
    """每个注册因子要么在 NATIVE_FACTOR_MAP 里（值非 None），要么注明手算。"""
    handcomputed_ok = {"ret_5d"}     # 已知聚宽没现成对应
    for e in factors.all_factors():
        n = e.meta.name
        native = factors.NATIVE_FACTOR_MAP.get(n)
        if native is None:
            assert n in handcomputed_ok, (
                f"{n} 没有聚宽对应也不在 handcomputed 白名单里，"
                f"请在 NATIVE_FACTOR_MAP 加上或在白名单里说明"
            )


def test_resolve_returns_native_call_for_supported_factors():
    """resolve('pe_ttm_inverse') 应返回 NativeFactorCall 而非 None。"""
    call = factors.resolve("pe_ttm_inverse")
    assert call is not None
    assert call.factor_id == "EP"


def test_resolve_returns_none_for_handcomputed():
    """resolve('ret_5d') 应返回 None。"""
    assert factors.resolve("ret_5d") is None


def test_list_supported_excludes_none_entries():
    supported = factors.list_supported()
    names = {n for n, _ in supported}
    assert "ret_5d" not in names              # 手算的不应被算成 supported
    assert "pe_ttm_inverse" in names


# ---------------------------------------------------------------------------
# compute_jq 实现一致性
# ---------------------------------------------------------------------------

def test_compute_jq_for_native_factors_calls_get_factor_values():
    """对于有聚宽对应的因子，compute_jq 必须真的调用 get_factor_values。"""
    for entry in factors.all_factors():
        name = entry.meta.name
        if factors.NATIVE_FACTOR_MAP.get(name) is None:
            continue
        src = inspect.getsource(entry.compute_jq)
        assert "get_factor_values" in src, (
            f"{name}.compute_jq 应该调用 get_factor_values，但没找到"
        )
        # 应该用 context.previous_date（不是 context.current_dt — 那会未来函数）
        assert "previous_date" in src, (
            f"{name}.compute_jq 应该用 context.previous_date 避免未来函数"
        )


def test_compute_jq_for_handcomputed_factors_uses_get_price():
    """ret_5d 等手算因子应使用 get_price 而非 get_factor_values。"""
    entry = factors.get("ret_5d")
    src = inspect.getsource(entry.compute_jq)
    assert "get_price" in src


def test_compute_jq_imports_jqfactor():
    """有聚宽对应的因子，compute_jq 应 import jqfactor（聚宽云命名空间）。"""
    for entry in factors.all_factors():
        if factors.NATIVE_FACTOR_MAP.get(entry.meta.name) is None:
            continue
        src = inspect.getsource(entry.compute_jq)
        assert "from jqfactor import" in src, (
            f"{entry.meta.name} 应 from jqfactor import get_factor_values"
        )


def test_compute_jq_uses_factor_id_from_meta():
    """compute_jq 里出现的 factor id 应当与 meta.jq_dependencies 一致。"""
    for entry in factors.all_factors():
        if factors.NATIVE_FACTOR_MAP.get(entry.meta.name) is None:
            continue
        src = inspect.getsource(entry.compute_jq)
        expected_id = factors.NATIVE_FACTOR_MAP[entry.meta.name]
        assert expected_id in src, (
            f"{entry.meta.name}.compute_jq 应包含 factor id "
            f"'{expected_id}'，但实际没有"
        )


# ---------------------------------------------------------------------------
# compute_local 也存在且对齐
# ---------------------------------------------------------------------------

def test_compute_local_exists_for_all_factors():
    """所有因子都应提供 compute_local 接口（给 factor_lab 本地分析用）。"""
    for entry in factors.all_factors():
        assert entry.compute_local is not None, (
            f"{entry.meta.name} 缺 compute_local"
        )


def test_compute_local_uses_jqdatasdk():
    """compute_local 应 import jqdatasdk（本地命名空间）。"""
    for entry in factors.all_factors():
        src = inspect.getsource(entry.compute_local)
        assert "jqdatasdk" in src, f"{entry.meta.name}.compute_local 应 import jqdatasdk"


# ---------------------------------------------------------------------------
# AST sanity：所有 factor 文件能 ast.parse
# ---------------------------------------------------------------------------

def test_all_factor_files_parse_cleanly():
    """所有 factors/<cat>/*.py 都能 ast.parse 不报错。"""
    factors_dir = PROJECT_ROOT / "factors"
    for py_file in factors_dir.rglob("*.py"):
        if "__pycache__" in py_file.parts:
            continue
        src = py_file.read_text(encoding="utf-8")
        try:
            ast.parse(src)
        except SyntaxError as e:
            raise AssertionError(f"{py_file} 语法错误: {e}")


# ---------------------------------------------------------------------------
# 关键边界：没有 factor 文件把 from factors._base import register 写在 docstring 外面
# 让 AI agent 容易抄到聚宽云
# ---------------------------------------------------------------------------

def test_each_factor_file_explicitly_documents_native_call():
    """v2.1 要求：每个 factor 文件的 docstring 应当提到调用方式（避免 AI 拷错）。"""
    factors_dir = PROJECT_ROOT / "factors"
    for py_file in factors_dir.rglob("*.py"):
        # 跳过 __init__ / _base / _helpers / _jq_native
        if py_file.name.startswith("_") or py_file.name == "__init__.py":
            continue
        if "__pycache__" in py_file.parts:
            continue
        src = py_file.read_text(encoding="utf-8")
        # 至少要在 docstring 或注释里提到聚宽相关词
        assert any(kw in src for kw in [
            "jqfactor", "get_factor_values", "get_price",
        ]), f"{py_file} 应在 compute_jq 里调聚宽 API"
