import os
import logging
from contextlib import asynccontextmanager
from fastapi import FastAPI, HTTPException, Request, status
from fastapi.responses import JSONResponse
from fastapi.exceptions import RequestValidationError
from app.models import RunCreate, RunResponse
from app.db import init_db, list_runs, insert_run

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(name)s: %(message)s")
logger = logging.getLogger("celesto_api")

@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup: attempt to initialize DB tables and seeds if DB is ready
    try:
        init_db()
    except Exception as e:
        logger.warning(f"DB initialization on startup deferred or failed: {e}")
    yield
    # Shutdown

app = FastAPI(
    title="Celesto Sandbox Control Plane & Run Ledger API",
    description="API for managing Celesto sandboxes, evaluating hostile code submissions, and auditing agent tool executions.",
    version="1.0.0",
    lifespan=lifespan
)

@app.exception_handler(RequestValidationError)
async def validation_exception_handler(request: Request, exc: RequestValidationError):
    # Requirement 11 specifies returning 400 for bad sandbox_name, unknown state, or different execution_target
    raw_errors = exc.errors()
    serializable_errors = []
    for err in raw_errors:
        serializable_errors.append({
            "type": err.get("type"),
            "loc": err.get("loc"),
            "msg": str(err.get("msg")),
            "input": str(err.get("input"))
        })
    logger.warning(f"Validation error on {request.url.path}: {serializable_errors}")
    return JSONResponse(
        status_code=status.HTTP_400_BAD_REQUEST,
        content={"detail": serializable_errors, "error": "Invalid request parameters"}
    )

@app.get("/health", status_code=status.HTTP_200_OK)
async def health_check():
    return {"status": "ok"}

@app.get("/api/runs", response_model=list[RunResponse], status_code=status.HTTP_200_OK)
async def get_all_runs():
    runs = list_runs()
    return runs

@app.post("/api/runs", status_code=status.HTTP_201_CREATED)
async def create_new_run(payload: RunCreate):
    created = insert_run(payload.model_dump())
    return created

if __name__ == "__main__":
    import uvicorn
    port = int(os.getenv("API_PORT", "8080"))
    uvicorn.run("app.main:app", host="0.0.0.0", port=port, reload=False)
