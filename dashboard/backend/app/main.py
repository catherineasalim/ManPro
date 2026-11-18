from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.routes import alarms, health, replay, roi, telemetry
from app.core.config import API_PREFIX, CORS_ORIGINS

app = FastAPI(
    title="MetroPT-3 Predictive Maintenance Dashboard API",
    description="Historical telemetry replay, anomaly status, RUL and cost simulation.",
    version="1.0.0",
)
app.add_middleware(
    CORSMiddleware,
    allow_origins=CORS_ORIGINS,
    allow_credentials=False,
    allow_methods=["GET", "POST"],
    allow_headers=["*"],
)
for route in (health.router, replay.router, telemetry.router, alarms.router, roi.router):
    app.include_router(route, prefix=API_PREFIX)


@app.get("/", include_in_schema=False)
def root() -> dict[str, str]:
    return {"name": "MetroPT-3 Dashboard API", "docs": "/docs", "health": f"{API_PREFIX}/health"}
