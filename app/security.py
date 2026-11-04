
import os
import secrets

from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials

API_TOKEN = os.getenv("API_TOKEN")

if not API_TOKEN:
    raise RuntimeError("La variable API_TOKEN n'est pas configurée")

bearer_scheme = HTTPBearer()


def verify_token(
    credentials: HTTPAuthorizationCredentials = Depends(bearer_scheme),
):
    if not secrets.compare_digest(credentials.credentials, API_TOKEN):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token invalide",
            headers={"WWW-Authenticate": "Bearer"},
        )

    return True
