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
    openai_model: str = Field(default="deepseek-v4-pro", alias="OPENAI_MODEL")
    llm_temperature: float = Field(default=0.3, ge=0.0, le=2.0)
    llm_max_tokens: int = Field(default=4096, ge=1, le=131072)

    # === Vision LLM (多模态图片识别) ===
    vision_enabled: bool = Field(default=False, alias="VISION_ENABLED")
    vision_model: str = Field(default="gpt-4o", alias="VISION_MODEL", description="视觉模型名称")
    vision_base_url: str = Field(default="", alias="VISION_BASE_URL", description="视觉模型 API 地址，留空则用 openai_base_url")
    vision_api_key: str = Field(default="", alias="VISION_API_KEY", description="视觉模型 API Key，留空则用 openai_api_key")

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
    use_reranker: bool = Field(default=False, alias="USE_RERANKER")
    reranker_top_n: int = Field(default=5, ge=1, le=50)

    # === Hybrid Retrieval ===
    hybrid_alpha: float = Field(default=0.7, ge=0.0, le=1.0, description="RRF 融合权重：向量分占比")
    retrieval_top_k: int = Field(default=20, ge=1, le=100, description="初次检索候选数")
    final_top_k: int = Field(default=5, ge=1, le=50, description="最终返回文档数")
    retrieval_min_dense_score: float = Field(default=0.35, ge=0.0, le=1.0, description="Dense 检索最低相关度阈值，低于此分数剔除")
    retrieval_use_hyde: bool = Field(default=True, description="是否启用 HyDE 假设文档增强召回")

    # === Redis ===
    redis_url: str = Field(default="redis://localhost:6379/0", alias="REDIS_URL")
    redis_max_connections: int = Field(default=20, ge=1, le=100)
    use_redis: bool = Field(default=True)

    # === Database ===
    database_url: str = Field(
        default="postgresql+asyncpg://postgres:agent2026@localhost:5432/household",
        alias="DATABASE_URL"
    )

    # === Qdrant (向量库) ===
    qdrant_url: str = Field(default="http://localhost:6333", alias="QDRANT_URL")
    qdrant_collection: str = Field(default="household_memory", alias="QDRANT_COLLECTION")

    # === LangGraph Checkpointer (SQLite) — 已废弃，项目使用自研 ReAct，不依赖 LangGraph ===
    checkpoint_db_path: str = Field(
        default="./data/checkpoints.db",
        alias="CHECKPOINT_DB_PATH",
        description="[DEPRECATED] 项目已切换为自研 ReAct 循环，不再使用 LangGraph"
    )

    # === App ===
    app_host: str = Field(default="0.0.0.0", alias="APP_HOST")
    app_port: int = Field(default=8000, ge=1, le=65535, alias="APP_PORT")
    app_debug: bool = Field(default=True, alias="APP_DEBUG")
    app_name: str = "家务事务全权代办 Agent"
    app_version: str = "5.5.0"

    # === Auth (JWT) ===
    jwt_secret: str = Field(default="agent-of-life-secret-change-me", alias="JWT_SECRET")
    jwt_algorithm: str = Field(default="HS256")
    jwt_expire_minutes: int = Field(default=1440, ge=1)

    # === Agent ===
    agent_max_iterations: int = Field(default=10, ge=1, le=50)
    agent_max_tool_calls: int = Field(default=8, ge=1, le=30)
    agent_parallel_tools: bool = Field(default=True, description="是否允许并行工具调用")
    agent_token_budget: int = Field(default=12000, ge=2000, le=64000, description="单次请求累计 Token 上限，超限强制截断")
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

    # === External APIs ===
    kuaidi100_customer: str = Field(default="", alias="KUAIDI100_CUSTOMER",
                                     description="快递100 企业账号，注册 https://api.kuaidi100.com")
    kuaidi100_key: str = Field(default="", alias="KUAIDI100_KEY",
                                description="快递100 API Key")

    # === Monitoring ===
    otel_enabled: bool = Field(default=False, alias="OTEL_ENABLED")
    log_level: str = Field(default="INFO", alias="LOG_LEVEL")

    # === Admin ===
    admin_user_id: str = Field(default="user_001", alias="ADMIN_USER_ID", description="管理员用户ID")

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
        """兼容旧接口 — Qdrant 不需要本地目录，保留用于日志"""
        p = Path("./data/qdrant_snapshots")
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
