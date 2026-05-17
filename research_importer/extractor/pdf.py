"""
research_importer/extractor/pdf.py — PDF 文本抽取（多后端 fallback）。

后端选择
--------
按优先级尝试三个库：

1. **pypdfium2**（推荐）—— Google 维护，稳定快速，对中文友好
2. **pdfplumber** —— 适合带表格的研报，能 layout-aware
3. **PyPDF2** —— 老牌但格式糟糕情况下凑合

任一可用即可。
"""
from __future__ import annotations

import logging
from pathlib import Path
from typing import Optional


log = logging.getLogger(__name__)


class PDFExtractionError(RuntimeError):
    pass


def _try_pypdfium2(path: Path) -> Optional[str]:
    try:
        import pypdfium2 as pdfium  # type: ignore
    except ImportError:
        return None
    try:
        doc = pdfium.PdfDocument(str(path))
        pages = []
        for i in range(len(doc)):
            tp = doc[i].get_textpage()
            pages.append(tp.get_text_range())
            tp.close()
        doc.close()
        return "\n\n".join(pages)
    except Exception as e:
        log.warning("pypdfium2 failed: %s", e)
        return None


def _try_pdfplumber(path: Path) -> Optional[str]:
    try:
        import pdfplumber  # type: ignore
    except ImportError:
        return None
    try:
        with pdfplumber.open(str(path)) as pdf:
            return "\n\n".join((p.extract_text() or "") for p in pdf.pages)
    except Exception as e:
        log.warning("pdfplumber failed: %s", e)
        return None


def _try_pypdf2(path: Path) -> Optional[str]:
    try:
        from PyPDF2 import PdfReader  # type: ignore
    except ImportError:
        return None
    try:
        reader = PdfReader(str(path))
        return "\n\n".join(p.extract_text() or "" for p in reader.pages)
    except Exception as e:
        log.warning("PyPDF2 failed: %s", e)
        return None


def extract_text(path: str | Path) -> str:
    """
    抽取 PDF 全文。三个后端轮试，任一成功即返回。

    Raises
    ------
    PDFExtractionError
        所有后端都失败（通常是没装任何 PDF 库，或文件本身损坏）。
    """
    p = Path(path)
    if not p.exists():
        raise PDFExtractionError(f"文件不存在: {p}")

    for backend, fn in [
        ("pypdfium2", _try_pypdfium2),
        ("pdfplumber", _try_pdfplumber),
        ("PyPDF2", _try_pypdf2),
    ]:
        text = fn(p)
        if text and text.strip():
            log.info("PDF extracted via %s: %d chars", backend, len(text))
            return text

    raise PDFExtractionError(
        f"无法从 {p} 抽取文本。请装至少一个 PDF 库："
        "`pip install pypdfium2`（推荐）或 `pip install pdfplumber` 或 `pip install PyPDF2`"
    )


def clean_text(text: str) -> str:
    """轻量清洗：合并多余空白、去掉页眉页脚常见 pattern。"""
    import re
    # 去掉 "第 1 页" / "page 1 of 30" 这种页码
    text = re.sub(r"\n\s*第\s*\d+\s*页\s*共\s*\d+\s*页\s*\n", "\n", text)
    text = re.sub(r"\n\s*page\s+\d+\s+of\s+\d+\s*\n", "\n", text, flags=re.IGNORECASE)
    # 多余空行折叠
    text = re.sub(r"\n{3,}", "\n\n", text)
    # trailing whitespace
    text = "\n".join(line.rstrip() for line in text.splitlines())
    return text.strip()
