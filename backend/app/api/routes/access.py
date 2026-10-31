"""Access-code check for deployed demos (see app.core.protection)."""

from fastapi import APIRouter, Request, Response, status
from pydantic import BaseModel, Field

from app.core.protection import ACCESS_HEADER, access_code_valid

router = APIRouter(prefix="/api/v1", tags=["access"])


class AccessStatus(BaseModel):
    required: bool
    granted: bool  # the X-Access-Code header (if any) is valid


class AccessAttempt(BaseModel):
    code: str = Field(min_length=1, max_length=200)


@router.get("/access", response_model=AccessStatus)
async def access_status(request: Request) -> AccessStatus:
    settings = request.app.state.settings
    return AccessStatus(
        required=settings.access_code is not None,
        granted=access_code_valid(settings, request.headers.get(ACCESS_HEADER)),
    )


@router.post("/access", status_code=status.HTTP_204_NO_CONTENT)
async def check_access(body: AccessAttempt, request: Request) -> Response:
    """Validate a code before the UI stores it. Attempts are rate limited per client."""
    if not access_code_valid(request.app.state.settings, body.code):
        return Response(status_code=status.HTTP_401_UNAUTHORIZED)
    return Response(status_code=status.HTTP_204_NO_CONTENT)
