from pydantic_settings import BaseSettings
from typing import Optional

class Settings(BaseSettings):
    PROJECT_NAME: str = "AeroTwin API"
    VERSION: str = "1.0.0"
    API_V1_STR: str = "/api/v1"
    
    # Security
    JWT_SECRET: str
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 60 * 24 * 8  # 8 days
    REFRESH_TOKEN_EXPIRE_MINUTES: int = 60 * 24 * 30  # 30 days
    EDGE_API_KEY: str = "changeme-edge-api-key"
    ALERT_COOLDOWN_MINUTES: int = 5

    # Accuracy-First Phase 5 (Health Fusion Improvements). A single
    # vibration anomaly can plausibly trigger BOTH the Fault model
    # ("Accelerometer Failure") and the dedicated Bearing CNN from the
    # same underlying signal — without this, that one event gets
    # penalized twice. Default on; a config flag (not a silent, hardcoded
    # change) so it can be disabled to compare fusion behavior directly.
    HEALTH_FUSION_DEDUP_CORRELATED_SOURCES: bool = True

    # Copilot LLM provider — see backend/AeroTwin_Rag/llm_providers.py.
    # Default stays "gemini" so existing deployments that haven't set
    # LLM_PROVIDER keep working unchanged; set it to "groq" once
    # GROQ_API_KEY is configured to make Groq primary instead.
    LLM_PROVIDER: str = "gemini"
    LLM_FALLBACK_ENABLED: bool = True
    GEMINI_API_KEY: Optional[str] = None
    GEMINI_MODEL: str = "gemini-3.8-flash"
    GROQ_API_KEY: Optional[str] = None
    GROQ_MODEL: str = "openai/gpt-oss-120b"
    OLLAMA_BASE_URL: str = "http://localhost:11434"
    OLLAMA_MODEL: Optional[str] = None

    # Database
    DATABASE_URL: str
    
    # MQTT & Redis
    MQTT_BROKER_URL: Optional[str] = None
    REDIS_URL: Optional[str] = None

    # Deployment
    # "production" turns on `assert_production_safe()` at startup: the app
    # refuses to boot with the well-known development defaults for secrets,
    # or with a wildcard CORS origin, instead of silently serving them.
    ENVIRONMENT: str = "development"
    # Comma-separated list of allowed browser origins, e.g.
    # "https://aerotwin.example.com". "*" is only acceptable in development.
    CORS_ORIGINS: str = "*"

    # Health Fusion freshness. A stored prediction older than this (relative
    # to the reading being fused) is ignored rather than fused, so a stopped
    # stream or a restart (which empties the in-memory RUL/Fault windows)
    # can't keep an old fault/RUL row driving today's health score.
    HEALTH_FUSION_MAX_PREDICTION_AGE_SECONDS: float = 60.0
    # Fault model input coverage. The fault model was trained on 32 real UAV
    # channels; the piston-engine adapter can only drive some of them from
    # measured telemetry and fills the rest with fixed placeholders (see
    # fault_adapter.PLACEHOLDER_CHANNELS). Below this share of measured-driven
    # channels the fault output is ADVISORY: still returned and displayed, but
    # excluded from Health Fusion (no penalty, no forced-zero, no alert).
    # [NEEDS VERIFICATION]: 0.6 is a first-pass value, not a validated one.
    FAULT_MIN_INPUT_COVERAGE: float = 0.6
    # GET /engines/{id}/health-score flags the score as `stale` when the
    # newest persisted score is older than this.
    HEALTH_SCORE_STALE_AFTER_SECONDS: float = 300.0

    class Config:
        env_file = ".env"
        case_sensitive = True

    @property
    def cors_origins_list(self) -> list[str]:
        return [o.strip() for o in self.CORS_ORIGINS.split(",") if o.strip()]

    def assert_production_safe(self) -> None:
        """Raise RuntimeError listing every unsafe setting when ENVIRONMENT=production."""
        if self.ENVIRONMENT.lower() != "production":
            return
        problems = []
        weak = ("changeme", "supersecret", "local-dev", "secret-change")
        if len(self.JWT_SECRET) < 32 or any(w in self.JWT_SECRET.lower() for w in weak):
            problems.append("JWT_SECRET is short (<32 chars) or a known development placeholder")
        if len(self.EDGE_API_KEY) < 16 or any(w in self.EDGE_API_KEY.lower() for w in weak):
            problems.append("EDGE_API_KEY is short (<16 chars) or a known development placeholder")
        if "*" in self.cors_origins_list or not self.cors_origins_list:
            problems.append("CORS_ORIGINS must list the real frontend origin(s), not '*'")
        if problems:
            raise RuntimeError("Refusing to start with unsafe production settings: " + "; ".join(problems))

settings = Settings()
