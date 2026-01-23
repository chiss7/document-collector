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

    class Config:
        env_file = ".env"


settings = Settings()