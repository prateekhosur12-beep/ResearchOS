"""Central configuration. Every tunable lives here (Lab 11 / Lab 12)."""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

BACKEND_ROOT = Path(__file__).resolve().parents[1]


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=str(BACKEND_ROOT / ".env"),
        env_file_encoding="utf-8",
        extra="ignore",
        case_sensitive=False,
    )

    # ---------- LLM ----------
    llm_provider: str = "ollama"
    ollama_base_url: str = "http://localhost:11434"
    ollama_model: str = "qwen2.5:3b"
    ollama_timeout: float = 180.0
    ollama_embed_model: str = "nomic-embed-text"
    ollama_embed_enabled: bool = True

    # ---------- Storage ----------
    database_url: str = "sqlite+aiosqlite:///./data/research.db"
    data_dir: str = "./data"
    export_dir: str = "./exports"

    # ---------- Scholarly sources ----------
    scholarly_contact_email: str = "student@example.edu"
    openalex_base_url: str = "https://api.openalex.org"
    crossref_base_url: str = "https://api.crossref.org"
    arxiv_base_url: str = "https://export.arxiv.org/api"
    scholarly_timeout: float = 25.0
    scholarly_max_retries: int = 2
    #: Multiplier for the per-provider minimum request spacing (0 disables it in tests).
    scholarly_throttle_scale: float = 1.0
    scholarly_concurrency: int = 4

    # ---------- Workflow policy ----------
    min_papers_for_analysis: int = 5
    default_result_limit: int = 20
    max_result_limit: int = 50
    max_discovery_attempts: int = 3
    max_graph_revisions: int = 2
    search_cache_ttl_seconds: int = 86400
    require_approval_before_export: bool = True
    #: seconds a cancelled run gets to unwind cooperatively before its task is killed
    cancel_grace_seconds: float = 8.0
    #: how many search queries the planner may dispatch per run
    max_search_queries: int = 5

    # ---------- MCP ----------
    mcp_enabled: bool = True
    mcp_server_module: str = "app.mcp.server"
    mcp_call_timeout: float = 90.0

    # ---------- Server ----------
    cors_origins: str = "*"
    log_level: str = "INFO"
    demo_mode: bool = False

    # convenience
    app_name: str = "Agentic AI Research Assistant"
    course_code: str = "26ECAC401"

    @property
    def data_path(self) -> Path:
        p = Path(self.data_dir)
        p = p if p.is_absolute() else (BACKEND_ROOT / p)
        p.mkdir(parents=True, exist_ok=True)
        return p

    @property
    def export_path(self) -> Path:
        p = Path(self.export_dir)
        p = p if p.is_absolute() else (BACKEND_ROOT / p)
        p.mkdir(parents=True, exist_ok=True)
        return p

    @property
    def resolved_database_url(self) -> str:
        """Make relative SQLite paths absolute so the app works from any CWD."""
        url = self.database_url
        prefix = "sqlite+aiosqlite:///"
        if url.startswith(prefix) and not url.startswith(prefix + "/"):
            rel = url[len(prefix):]
            db_path = (BACKEND_ROOT / rel).resolve()
            db_path.parent.mkdir(parents=True, exist_ok=True)
            return f"{prefix}{db_path}"
        return url

    @property
    def cors_origin_list(self) -> list[str]:
        if self.cors_origins.strip() == "*":
            return ["*"]
        return [o.strip() for o in self.cors_origins.split(",") if o.strip()]

    def public_snapshot(self) -> dict:
        """Config safe to expose to the UI (no secrets)."""
        return {
            "llm_provider": self.llm_provider,
            "ollama_base_url": self.ollama_base_url,
            "ollama_model": self.ollama_model,
            "ollama_timeout": self.ollama_timeout,
            "ollama_embed_model": self.ollama_embed_model,
            "database": self.database_url.split("://")[0],
            "sources": {
                "openalex": self.openalex_base_url,
                "crossref": self.crossref_base_url,
                "arxiv": self.arxiv_base_url,
            },
            "max_discovery_attempts": self.max_discovery_attempts,
            "max_graph_revisions": self.max_graph_revisions,
            "min_papers_for_analysis": self.min_papers_for_analysis,
            "require_approval_before_export": self.require_approval_before_export,
            "mcp_enabled": self.mcp_enabled,
            "demo_mode": self.demo_mode,
            "course_code": self.course_code,
        }


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
