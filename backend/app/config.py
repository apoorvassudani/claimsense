"""Central configuration. Secrets come from environment / .env only (never from code or the frontend)."""
import os
from dotenv import load_dotenv

load_dotenv()


class Settings:
    database_url: str = os.getenv(
        "DATABASE_URL", "postgresql+psycopg://claimsense:claimsense@localhost:5432/claimsense"
    )
    # mock = offline rule-based extractor (for tests/demo)
    # openai_compat = Groq OpenAI-compatible endpoint | azure = Azure OpenAI
    llm_provider: str = os.getenv("LLM_PROVIDER", "mock")
    llm_api_key: str = os.getenv("LLM_API_KEY", "")
    llm_model: str = os.getenv("LLM_MODEL", "openai/gpt-oss-20b")
    llm_base_url: str = os.getenv("LLM_BASE_URL", "https://api.groq.com/openai/v1")
    llm_timeout_s: float = float(os.getenv("LLM_TIMEOUT_S", "20"))
    # Blank = don't send temperature (needed for reasoning models that only allow the default).
    llm_temperature: str = os.getenv("LLM_TEMPERATURE", "0")

    # Azure OpenAI (used when LLM_PROVIDER=azure)
    azure_openai_endpoint: str = os.getenv("AZURE_OPENAI_ENDPOINT", "")
    azure_openai_api_key: str = os.getenv("AZURE_OPENAI_API_KEY", "")
    azure_openai_api_version: str = os.getenv("AZURE_OPENAI_API_VERSION", "2024-10-21")
    azure_openai_chat_deployment: str = os.getenv("AZURE_OPENAI_CHAT_DEPLOYMENT", "")
    azure_openai_embedding_deployment: str = os.getenv("AZURE_OPENAI_EMBEDDING_DEPLOYMENT", "")

    # Authentication. AUTH_SECRET signs login tokens: set a long random value in .env (and in the cloud settings).
    auth_secret: str = os.getenv("AUTH_SECRET", "")
    auth_token_minutes: int = int(os.getenv("AUTH_TOKEN_MINUTES", "480"))
    # Password for the three demo accounts (intake01, reviewer01, admin01), created when no users exist.
    demo_password: str = os.getenv("DEMO_PASSWORD", "")

    # OCR for scanned images and scanned PDFs.
    # auto = Document Intelligence if configured, else the Azure OpenAI chat model's vision; or force one:
    # docintel | vision | none
    ocr_provider: str = os.getenv("OCR_PROVIDER", "auto")
    azure_docintel_endpoint: str = os.getenv("AZURE_DOCINTEL_ENDPOINT", "")
    azure_docintel_api_key: str = os.getenv("AZURE_DOCINTEL_API_KEY", "")
    azure_docintel_api_version: str = os.getenv("AZURE_DOCINTEL_API_VERSION", "2024-11-30")

    # Azure AI Search (RAG over policy wording). Without these, retrieval falls back to local keyword search.
    azure_search_endpoint: str = os.getenv("AZURE_SEARCH_ENDPOINT", "")
    azure_search_api_key: str = os.getenv("AZURE_SEARCH_API_KEY", "")
    azure_search_index: str = os.getenv("AZURE_SEARCH_INDEX", "policy-clauses")
    azure_search_api_version: str = os.getenv("AZURE_SEARCH_API_VERSION", "2024-07-01")
    # "", timeout, quota, malformed, slow  -> used to demo failure handling
    simulate_failure: str = os.getenv("SIMULATE_FAILURE", "")
    slow_call_ms: int = int(os.getenv("SLOW_CALL_MS", "5000"))
    log_file: str = os.getenv("LOG_FILE", "logs/claimsense.jsonl")
    otel_console: bool = os.getenv("OTEL_CONSOLE", "0") == "1"
    cors_origins: list[str] = os.getenv("CORS_ORIGINS", "http://localhost:5173").split(",")
    max_upload_bytes: int = 5 * 1024 * 1024

    @property
    def search_enabled(self) -> bool:
        return bool(self.azure_search_endpoint and self.azure_search_api_key
                    and self.azure_openai_endpoint and self.azure_openai_api_key
                    and self.azure_openai_embedding_deployment)

    @property
    def model_label(self) -> str:
        if self.llm_provider == "mock":
            return "mock:offline-extractor"
        if self.llm_provider == "azure":
            return f"azure:{self.azure_openai_chat_deployment}"
        return f"{self.llm_provider}:{self.llm_model}"


settings = Settings()
