from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    # DSPACE configuration
    DSPACE_COLLECTION_UUID: str
    DSPACE_API_BASE_URL: str

    DATABASE_URL: str
    # Make JWT public key optional so the app can run in dev without tokens
    JWT_PUBLIC_KEY: str | None = None
    JWT_ALGORITHM: str = "RS256"
    # When True, authentication is bypassed (useful only in development)
    DISABLE_AUTH: bool = False

    # Supabase storage configuration
    SUPABASE_URL: str | None = None
    SUPABASE_KEY: str | None = None
    SUPABASE_BUCKET: str = "ia-docs-uce"

    model_config = {
        "env_file": ".env",
        # allow extra env vars (e.g. ENV, DISABLE_NLP) without raising
        "extra": "ignore",
    }


settings = Settings()