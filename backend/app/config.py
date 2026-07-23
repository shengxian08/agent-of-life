"""
核心配置模块 v4.0 - 前沿技术栈全配置
"""
from __future__ import annotations

from pathlib import Path

from pydantic_settings import BaseSettings
from pydantic import Field, SecretStr


class Settings(BaseSettings):
    """应用全局配置"""

    # === LLM (OpenAI 兼容接口) ===
    openai_api_key: SecretStr = Field(default=SecretStr("sk-xxx"), alias="OPENAI_API_KEY")
    openai_base_url: str = Field(default="https://api.deepseek.com/v1", alias="OPENAI_BASE_URL")
    openai_model: str = Field(default="deepseek-chat", alias="OPENAI_MODEL")
    llm_temperature: float = Field(default=0.3, ge=0.0, le=2.0)
    llm_max_tokens: int = Field(default=4096, ge=1, le=131072)

    # === Embedding (BGE-M3 中文优化) ===
    embedding_model_name: str = Field(
        default="./data/models/bge-m3-local",
        alias="EMBEDDING_MODEL_NAME",
        description="BGE-M3 本地路径 (D盘), 无需联网"
    )
    embedding_device: str = Field(default="cpu", alias="EMBEDDING_DEVICE")
    embedding_dim: int = Field(default=1024, ge=64, le=4096, description="BGE-M3 输出维度")

    # === Reranker (BGE-Reranker-v2) ===
    reranker_model_name: str = Field(
        default="BAAI/bge-reranker-v2-m3",
        alias="RERANKER_MODEL_NAME",
        description="Cross-encoder 重排序模型"
    )
    use_reranker: bool = Field(default=True, alias="USE_RERANKER")
    reranker_top_n: int = Field(default=5, ge=1, le=50)

    # === Hybrid Retrieval ===
    hybrid_alpha: float = Field(default=0.7, ge=0.0, le=1.0, description="RRF 融合权重：向量分占比")
    retrieval_top_k: int = Field(default=20, ge=1, le=100, description="初次检索候选数")
    final_top_k: int = Field(default=5, ge=1, le=50, description="最终返回文档数")

    # === Redis ===
    redis_url: str = Field(default="redis://localhost:6379/0", alias="REDIS_URL")
    redis_max_connections: int = Field(default=20, ge=1, le=100)
    use_redis: bool = Field(default=True)

    # === Database ===
    database_url: str = Field(
        default="sqlite+aiosqlite:///./data/household.db",
        alias="DATABASE_URL"
    )

    # === ChromaDB ===
    chroma_persist_dir: str = Field(default="./data/chroma", alias="CHROMA_PERSIST_DIR")

    # === LangGraph Checkpointer (SQLite) ===
    checkpoint_db_path: str = Field(
        default="./data/checkpoints.db",
        alias="CHECKPOINT_DB_PATH"
    )

    # === App ===
    app_host: str = Field(default="0.0.0.0", alias="APP_HOST")
    app_port: int = Field(default=8000, ge=1, le=65535, alias="APP_PORT")
    app_debug: bool = Field(default=True, alias="APP_DEBUG")
    app_name: str = "家务事务全权代办 Agent"
    app_version: str = "5.0.0"

    # === Auth (JWT) ===
    jwt_secret: str = Field(default="agent-of-life-secret-change-me", alias="JWT_SECRET")
    jwt_algorithm: str = Field(default="HS256")
    jwt_expire_minutes: int = Field(default=1440, ge=1)

    # === Agent ===
    agent_max_iterations: int = Field(default=10, ge=1, le=50)
    agent_max_tool_calls: int = Field(default=8, ge=1, le=30)
    agent_parallel_tools: bool = Field(default=True, description="是否允许并行工具调用")
    conversation_history_limit: int = Field(default=40, ge=1, le=200)

    # === Memory ===
    memory_consolidation_threshold: int = Field(
        default=6, ge=2, le=50, description="对话超过此条数触发摘要固化"
    )
    memory_long_term_ttl_days: int = Field(default=90, ge=1, le=365)

    # === Household ===
    electricity_off_peak_start: str = Field(default="22:00")
    electricity_off_peak_end: str = Field(default="06:00")
    default_city: str = Field(default="北京")
    default_location: str = Field(default="朝阳区")

    # === Monitoring ===
    otel_enabled: bool = Field(default=False, alias="OTEL_ENABLED")
    log_level: str = Field(default="INFO", alias="LOG_LEVEL")

    # === Rate Limiting ===
    rate_limit_enabled: bool = Field(default=True, alias="RATE_LIMIT_ENABLED")
    rate_limit_requests: int = Field(default=60, ge=1, alias="RATE_LIMIT_REQUESTS")
    rate_limit_window_seconds: int = Field(default=60, ge=1, alias="RATE_LIMIT_WINDOW")

    # === Security: CORS ===
    cors_allowed_origins: str = Field(
        default="*",
        alias="CORS_ALLOWED_ORIGINS",
        description="逗号分隔的允许来源，生产环境应限制为具体域名"
    )

    # === API Key 兼容性属性 (SecretStr → str) ===
    @property
    def api_key(self) -> str:
        """返回原始 API Key 字符串，向后兼容"""
        return self.openai_api_key.get_secret_value()

    # === Paths ===
    @property
    def data_dir(self) -> Path:
        p = Path("./data")
        p.mkdir(parents=True, exist_ok=True)
        return p

    @property
    def vector_db_dir(self) -> Path:
        p = Path(self.chroma_persist_dir)
        p.mkdir(parents=True, exist_ok=True)
        return p

    @property
    def checkpoint_dir(self) -> Path:
        p = Path(self.checkpoint_db_path).parent
        p.mkdir(parents=True, exist_ok=True)
        return p

    model_config = {
        "env_file": ".env",
        "env_file_encoding": "utf-8",
        "extra": "ignore",
    }


# 全局单例配置
settings = Settings()
