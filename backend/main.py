"""Curia API application assembly."""

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from .routes.catalog import router as catalog_router
from .routes.conversations import router as conversations_router
from .routes.execution import router as execution_router
from .routes.metrics import router as metrics_router
from .routes.prompts import router as prompts_router
from .routes.repositories import router as repositories_router
from .routes.sessions import router as sessions_router
from .routes.settings import router as settings_router
from .routes.turns import router as turns_router

# Explicit common ports (docs / defaults). Regex covers alternate Vite ports
# when 5173 is taken (e.g. PolitySphere) so Observatory is not CORS-blocked.
LOCAL_ORIGINS = (
    "http://localhost:5173",
    "http://localhost:5174",
    "http://localhost:5175",
    "http://localhost:3000",
    "http://127.0.0.1:5173",
    "http://127.0.0.1:5174",
    "http://127.0.0.1:5175",
    "http://127.0.0.1:3000",
)
# Any localhost / 127.0.0.1 / [::1] port for local Observatory + API splits
# (IPv6 localhost shows up on some Windows/WSL browser stacks).
LOCAL_ORIGIN_REGEX = r"https?://(localhost|127\.0\.0\.1|\[::1\])(:\d+)?"


def create_app() -> FastAPI:
    application = FastAPI(title="Curia API")
    for router in (
        conversations_router,
        repositories_router,
        settings_router,
        turns_router,
        execution_router,
        prompts_router,
        metrics_router,
        catalog_router,
        sessions_router,
    ):
        application.include_router(router)

    application.add_middleware(
        CORSMiddleware,
        allow_origins=list(LOCAL_ORIGINS),
        allow_origin_regex=LOCAL_ORIGIN_REGEX,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    @application.get("/")
    async def healthcheck():
        return {"status": "ok", "service": "Curia API"}

    return application


app = create_app()


if __name__ == "__main__":
    import uvicorn

    uvicorn.run("backend.main:app", host="0.0.0.0", port=8001)
