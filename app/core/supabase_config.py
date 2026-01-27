from supabase import create_client
from app.core.config import settings


def get_supabase_client():
    url = settings.SUPABASE_URL
    key = settings.SUPABASE_KEY
    if not url or not key:
        raise RuntimeError("SUPABASE_URL and SUPABASE_KEY must be set in environment")
    return create_client(url, key)


# create a module-level client for reuse
_client = None


def client():
    global _client
    if _client is None:
        _client = get_supabase_client()
    return _client
