import httpx
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from app.core.config import settings

security = HTTPBearer()


async def get_current_user(
    credentials: HTTPAuthorizationCredentials = Depends(security)
):
    if getattr(settings, "DISABLE_AUTH", False):
        return {"sub": "dev", "roles": ["dev"]}

    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.post(
                f"{settings.JAVA_SERVICE_URL}/api/auth/validate",
                headers={"Authorization": f"Bearer {credentials.credentials}"},
            )

        if resp.status_code != 200:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid token",
            )

        return resp.json()

    except httpx.RequestError:
        raise HTTPException(
            status_code=status.HTTP_503_UNAVAILABLE,
            detail="Authentication service unavailable",
        )
