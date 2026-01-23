from jose import jwt
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from app.core.config import settings

security = HTTPBearer()

def get_current_user(
    credentials: HTTPAuthorizationCredentials = Depends(security)
):
    # Bypass authentication when explicitly disabled (development only)
    if getattr(settings, "DISABLE_AUTH", False):
        return {"sub": "dev", "roles": ["dev"]}

    try:
        if not settings.JWT_PUBLIC_KEY:
            raise Exception("Missing JWT public key")

        payload = jwt.decode(
            credentials.credentials,
            settings.JWT_PUBLIC_KEY,
            algorithms=[settings.JWT_ALGORITHM],
        )
        return payload
    except Exception:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid token"
        )