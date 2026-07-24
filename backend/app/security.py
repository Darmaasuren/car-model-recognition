from secrets import compare_digest
from typing import Annotated

from fastapi import HTTPException, Security, status
from fastapi.security import APIKeyHeader

from config import settings


api_key_header = APIKeyHeader(
    name="API-Key",
    auto_error=False,
)


def require_api_key(
    provided_api_key: Annotated[
        str | None,
        Security(api_key_header),
    ],
) -> None:
    if provided_api_key is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="API key байхгүй байна.",
        )

    if not compare_digest(
        provided_api_key,
        settings.api_key,
    ):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="API key буруу байна.",
        )