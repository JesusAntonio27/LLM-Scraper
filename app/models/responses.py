from pydantic import BaseModel
from typing import Optional

class URLMeta(BaseModel):
    tokens_input: int = 0
    tokens_output: int = 0
    model_used: Optional[str] = None
    cost_usd: float = 0.0
    fetch_ms: Optional[int] = None
    preprocess_ms: Optional[int] = None
    llm_ms: Optional[int] = None
    strategy_used: Optional[str] = None  # "trafilatura" | "structural" | "raw_html"
    agentic: Optional[bool] = False
    iterations: Optional[int] = 0
    cost_breakdown: Optional[dict] = None

class URLResult(BaseModel):
    url: str
    status: str            # "extracted" | "skipped" | "failed"
    content_hash: Optional[str] = None
    data: Optional[dict] = None
    meta: URLMeta = URLMeta()

class OutputBlock(BaseModel):
    records: list[dict] = []
    csv: Optional[str] = None
    schema_used: Optional[dict] = None

class Summary(BaseModel):
    total: int = 0
    extracted: int = 0
    skipped: int = 0
    failed: int = 0
    total_tokens: int = 0
    total_cost_usd: float = 0.0
    total_ms: int = 0
    cost_note: Optional[str] = None

class ExtractResponse(BaseModel):
    results: list[URLResult]
    output: OutputBlock
    summary: Summary

class DiscoverResponse(BaseModel):
    domain: str
    suggested_schema: dict
    suggested_instructions: Optional[str] = None
    confidence: Optional[float] = None
    notes: Optional[str] = None
    meta: URLMeta = URLMeta()

class PreprocessResponse(BaseModel):
    markdown: str
    content_hash: str
    original_size_kb: float
    processed_size_kb: float
    estimated_tokens: Optional[int] = 0
    fetch_ms: int
    strategy_used: Optional[str] = None

class HealthResponse(BaseModel):
    status: str       # "ok" | "degraded"
    oxylabs: str      # "ok" | "error: <mensaje>"
    anthropic: str    # "ok" | "error: <mensaje>"
    timestamp: str    # ISO 8601
