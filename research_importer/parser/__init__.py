"""parser — LLM 抽取与结构化输出。"""
from research_importer.parser.schema import (  # noqa: F401
    ExtractedFactor,
    ExtractedStrategy,
)
from research_importer.parser.prompts import (  # noqa: F401
    build_extract_prompt,
    build_review_prompt,
    SYSTEM_PROMPT_EXTRACT,
    SYSTEM_PROMPT_REVIEW,
)
