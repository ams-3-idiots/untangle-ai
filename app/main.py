"""앱 시작점."""

from fastapi import FastAPI

from app.api.middleware import RequestIdMiddleware
from app.api.v1.router import api_router
from app.core.config import settings
from app.core.openapi import API_DESCRIPTION, OPENAPI_TAGS
from app.exceptions.handlers import register_exception_handlers

app = FastAPI(
    title=settings.app_name,
    description=API_DESCRIPTION,
    openapi_tags=OPENAPI_TAGS,
)

app.add_middleware(RequestIdMiddleware)
register_exception_handlers(app)
app.include_router(api_router, prefix=settings.api_v1_prefix)
