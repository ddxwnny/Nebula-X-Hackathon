from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from api.routes import get_disruption_monitor, get_journey_service, router as routes_router
from config import get_settings


@asynccontextmanager
async def lifespan(app: FastAPI):
    settings = get_settings()
    journey_service = get_journey_service()
    monitor = get_disruption_monitor(journey_service)
    if settings.enable_background_disruption_monitor:
        await monitor.start()
    yield
    if settings.enable_background_disruption_monitor:
        await monitor.stop()


app = FastAPI(title="Door-to-Door Route Planner", version="0.1.0", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:5173",
        "http://127.0.0.1:5173",
        "http://localhost:80",
        "http://127.0.0.1:80",
        "http://localhost",
        "http://127.0.0.1",
        "http://localhost:3000",
        "http://127.0.0.1:3000",
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
app.include_router(routes_router, prefix="/api/v1")


@app.get("/health")
async def health_check() -> dict[str, str]:
    return {"status": "ok"}
