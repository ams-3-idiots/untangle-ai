"""앱 시작점."""

from fastapi import FastAPI

from app.api.v1.router import api_router
from app.core.config import settings
from app.exceptions.handlers import register_exception_handlers

app = FastAPI(title=settings.app_name)

register_exception_handlers(app)
app.include_router(api_router, prefix=settings.api_v1_prefix)
