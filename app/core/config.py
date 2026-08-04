import json

from pydantic import field_validator
from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    # DSPACE configuration
    DSPACE_COLLECTION_UUID: str
    DSPACE_API_BASE_URL: str

    DATABASE_URL: str

    # Java authentication service URL (e.g. http://localhost:8080)
    JAVA_SERVICE_URL: str = "http://localhost:8080"

    # When True, authentication is bypassed (useful only in development)
    DISABLE_AUTH: bool = False

    # Enable/disable request & response logging middleware
    REQUEST_LOGGING_ENABLED: bool = True

    # Logging level for request/response logs (DEBUG, INFO, WARNING, ...)
    LOG_LEVEL: str = "INFO"

    # Storage provider selection ("supabase" | "r2")
    STORAGE_PROVIDER: str = "supabase"

    # Supabase storage configuration
    SUPABASE_URL: str | None = None
    SUPABASE_KEY: str | None = None
    SUPABASE_BUCKET: str = "ia-docs-uce"

    # Cloudflare R2 storage configuration (S3-compatible)
    R2_ACCESS_KEY_ID: str | None = None
    R2_SECRET_ACCESS_KEY: str | None = None
    R2_ENDPOINT: str | None = None
    R2_BUCKET: str = ""
    R2_PUBLIC_URL: str | None = None

    # OAI-PMH journals list.
    # Override via env var OAI_JOURNALS as a JSON string:
    #   OAI_JOURNALS='[{"nombre":"...","oai_url":"..."}]'
    OAI_JOURNALS: list[dict] = [
        {
            "nombre": "GEEKS DECC-Reports (ESPE)",
            "oai_url": "https://journal.espe.edu.ec/ojs/index.php/geeks/oai",
        },
        {
            "nombre": "Maskana (U. Cuenca)",
            "oai_url": "https://publicaciones.ucuenca.edu.ec/ojs/index.php/maskana/oai",
        },
        {
            "nombre": "Investigación, Tecnología e Innovación (U. Guayaquil)",
            "oai_url": "https://revistas.ug.edu.ec/index.php/iti/oai",
        },
        {
            "nombre": "Ingenius (U. Politécnica Salesiana)",
            "oai_url": "https://revistas.ups.edu.ec/index.php/ingenius/oai",
        },
    ]

    @field_validator("OAI_JOURNALS", mode="before")
    @classmethod
    def parse_oai_journals(cls, v):
        if isinstance(v, str):
            return json.loads(v)
        return v

    model_config = {
        "env_file": ".env",
        # allow extra env vars (e.g. ENV, DISABLE_NLP) without raising
        "extra": "ignore",
    }


settings = Settings()