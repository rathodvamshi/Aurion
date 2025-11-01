# ==================================================
# Project Maya Backend Configuration
# Centralized settings for DBs, APIs, AI, and services
# ==================================================

from pydantic_settings import BaseSettings, SettingsConfigDict
from pathlib import Path
from typing import Optional
import os


class Settings(BaseSettings):
    """
    Centralized configuration for all backend services.
    Loads from environment variables or a `.env` file.
    """

    # ==================================================
    # 🗄️ Database (MongoDB)
    # ==================================================
    MONGO_URI: str
    MONGO_DB: str = "MAYA"
    DATABASE_URL: Optional[str] = None  # Optional fallback DB URL

    # ==================================================
    # 🔐 JWT / Authentication
    # ==================================================
    SECRET_KEY: str
    ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 60
    REFRESH_TOKEN_EXPIRE_DAYS: int = 7

    # ==================================================
    # 🤖 AI / Embeddings / Vector DB
    # ==================================================
    PINECONE_API_KEY: str
    PINECONE_ENVIRONMENT: Optional[str] = None
    PINECONE_ENV: Optional[str] = None
    PINECONE_INDEX: str = "maya"
    PINECONE_HOST: str = ""
    PINECONE_DIMENSIONS: int = 1024
    PINECONE_METRIC: str = "cosine"
    PINECONE_CLOUD: str = "aws"
    PINECONE_REGION: str = "us-east-1"

    GEMINI_API_KEY: Optional[str] = None
    GEMINI_API_KEYS: Optional[str] = None
    ANTHROPIC_API_KEY: Optional[str] = None
    OPENAI_API_KEY: Optional[str] = None

    GOOGLE_MODEL: str = "gemini-1.5-flash"
    # Cohere removed
    COHERE_API_KEY: Optional[str] = None
    COHERE_MODEL: str = ""
    ANTHROPIC_MODEL: str = "claude-3-haiku-20240307"

    EMBEDDING_MODEL_VERSION: str = "text-embedding-004"

    # Timeout & failover configs
    AI_PROVIDER_FAILURE_TIMEOUT: int = 60
    AI_PRIMARY_TIMEOUT: float = 2.2
    AI_FALLBACK_TIMEOUT: float = 2.8
    AI_TIMEOUT: int | float | None = None  # Optional unified quick-timeout for simple manager
    AI_ENABLE_HEDGED: bool = False
    AI_HEDGE_DELAY_MS: int = 60
    AI_MAX_PARALLEL: int = 1
    AI_PROVIDER_ORDER: Optional[str] = None  # Comma-separated override order
    PRIMARY_PROVIDER: Optional[str] = None  # e.g., "gemini"
    FALLBACK_PROVIDER: Optional[str] = None  # e.g., "gemini"
    # Custom ordering specifically for fact extraction task (comma list, e.g., "gemini,anthropic")
    FACT_EXTRACT_PROVIDER_ORDER: Optional[str] = None

    # 🧠 Neo4j Knowledge Graph
    # ==================================================
    NEO4J_URI: str = "neo4j+s://bb2cd868.databases.neo4j.io"
    NEO4J_CONTAINER_URI: Optional[str] = None
    NEO4J_USER: str
    NEO4J_PASSWORD: str
    NEO4J_STARTUP_TIMEOUT_SECS: int = 12
    # Optional: explicit Aura database name (defaults to driver default if not set)
    NEO4J_DATABASE: Optional[str] = None
    NEO4J_QUERY_API_URL: str = "https://bb2cd868.databases.neo4j.io/db/{databaseName}/query/v2"

    # ==================================================
    # ⚡ Redis (Caching / Session)
    # ==================================================
    # Prefer REDIS_URL for Redis Cloud (e.g., rediss://:pass@host:6380/0)
    REDIS_URL: Optional[str] = None
    REDIS_HOST: str = "localhost"
    REDIS_PORT: int = 6379
    REDIS_DB: int = 0
    REDIS_PASSWORD: Optional[str] = None
    # Set REDIS_TLS=True when using host/port with Redis Cloud on 6380
    REDIS_TLS: bool = False

    # ==================================================
    # 📧 Email / Notifications (SMTP)
    # ==================================================
    MAIL_USERNAME: str
    MAIL_PASSWORD: str
    MAIL_FROM: str
    MAIL_SERVER: str = "smtp.gmail.com"
    MAIL_PORT: int = 587
    MAIL_STARTTLS: bool = True
    # Pre-wake buffer in seconds (env-driven)
    PREWAKE_BUFFER_SECONDS: int = 120  # 2 minutes default
    MAIL_SSL_TLS: bool = False

    SMTP_USER: Optional[str] = None
    SMTP_PASS: Optional[str] = None

    # ==================================================
    # 📊 API Limits / Quotas
    # ==================================================
    API_MONTHLY_LIMIT: int = 20

    # ==================================================
    # 🧬 Feature Toggles / Personalization
    # ==================================================
    ENABLE_PERSONA_RESPONSE: bool = True
    PERSONA_STYLE: str = "best_friend"
    PERSONA_MEMORY_TURNS: int = 15

    ENABLE_SUGGESTIONS: bool = True
    SUGGESTION_HISTORY_WINDOW: int = 30

    ENABLE_EMOTION_PERSONA: bool = True
    ENABLE_EMOJI_ENRICHMENT: bool = True
    EMOJI_MAX_AUTO_ADD: int = 3
    EMOJI_MAX_TOTAL: int = 6

    # ==================================================
    # 🧠 Memory System Configuration
    # ==================================================
    # Memory gating thresholds
    MEMORY_GATE_ENABLE: bool = True
    MEMORY_GATE_MIN_SALIENCE: float = 0.85
    MEMORY_GATE_MIN_TRUST: float = 0.55
    MEMORY_GATE_MIN_COMPOSITE: float = 0.35
    MEMORY_GATE_LOG_SKIPPED: bool = True
    
    # Memory storage settings
    MEMORY_STORAGE_ENABLED: bool = True
    MEMORY_CROSS_SESSION_ENABLED: bool = True
    MEMORY_AUTO_STORE_THRESHOLD: int = 10  # Minimum message length to auto-store
    
    # Advanced emotion settings
    ADV_EMOTION_ENABLE: bool = False
    ADV_EMOTION_CONFIDENCE_THRESHOLD: float = 0.7
    EMOTION_TREND_WINDOW: int = 10
    EMOTION_ESCALATION_THRESHOLD: int = 3

    # ==================================================
    # 🌐 External APIs
    # ==================================================
    YOUTUBE_API_KEY: Optional[str] = None
    NEWS_API_KEY: Optional[str] = None
    WEATHER_API_KEY: Optional[str] = None
    
    # ==================================================
    # 🔍 Real-Time Web Search APIs
    # ==================================================
    SERPAPI_KEY: Optional[str] = None
    GOOGLE_API_KEY: Optional[str] = None  # Reuse for Custom Search API
    GOOGLE_SEARCH_CX_ID: Optional[str] = None  # Custom Search Engine ID

    # ==================================================
    # 🕒 Timezone / Localization
    # ==================================================
    # Default timezone for all user-visible times (e.g., reminders) when not overridden.
    # IST = Asia/Kolkata
    DEFAULT_TIMEZONE: str = "Asia/Kolkata"

    # ==================================================
    # 🧩 Pydantic Settings
    # ==================================================
    model_config = SettingsConfigDict(
        env_file=str(Path(__file__).resolve().parents[1] / ".env"),
        env_prefix="",
        extra="ignore"
    )

    # ==================================================
    # 🧠 Post Initialization Adjustments
    # ==================================================
    def model_post_init(self, __context) -> None:
        """Normalize and auto-fill environment variables."""
        try:
            # Normalize Pinecone env var
            if not self.PINECONE_ENVIRONMENT and self.PINECONE_ENV:
                object.__setattr__(self, "PINECONE_ENVIRONMENT", self.PINECONE_ENV)

            # Backward compatibility for SMTP
            if not self.SMTP_USER and self.MAIL_USERNAME:
                object.__setattr__(self, "SMTP_USER", self.MAIL_USERNAME)
            if not self.SMTP_PASS and self.MAIL_PASSWORD:
                object.__setattr__(self, "SMTP_PASS", self.MAIL_PASSWORD)

            # Ensure GEMINI_API_KEYS is set from GEMINI_API_KEY if only one key is present
            if not self.GEMINI_API_KEYS and self.GEMINI_API_KEY:
                object.__setattr__(self, "GEMINI_API_KEYS", self.GEMINI_API_KEY)

            # Backward-compatibility: if AI_TIMEOUT is missing, prefer AI_PRIMARY_TIMEOUT for simple manager
            if not self.AI_TIMEOUT:
                object.__setattr__(self, "AI_TIMEOUT", self.AI_PRIMARY_TIMEOUT or 8)

            # Handle Docker-specific hostname adjustments
            if os.path.exists("/.dockerenv"):
                if self.NEO4J_CONTAINER_URI:
                    object.__setattr__(self, "NEO4J_URI", self.NEO4J_CONTAINER_URI)
                elif "localhost" in self.NEO4J_URI:
                    object.__setattr__(self, "NEO4J_URI", self.NEO4J_URI.replace("localhost", "neo4j"))

                if self.REDIS_HOST in ("localhost", "127.0.0.1"):
                    object.__setattr__(self, "REDIS_HOST", "redis")

        except Exception as e:
            print(f"[Config Warning] Environment normalization skipped: {e}")


# ==================================================
# 🌍 Global Settings Instance
# ==================================================
settings = Settings()

# Optional: log loaded environment for debugging (safe fields only)
if os.getenv("DEBUG_CONFIG", "false").lower() == "true":
    print("\n[✅ Config Loaded Successfully]")
    print(f"MongoDB: {settings.MONGO_DB}")
    print(f"Neo4j: {settings.NEO4J_URI}")
    print(f"Redis: {settings.REDIS_HOST}:{settings.REDIS_PORT}")
    print(f"Gemini configured: {bool(settings.GEMINI_API_KEY)}\n")
