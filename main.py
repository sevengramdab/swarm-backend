"""
OrbitScribe Swarm Backend
FastAPI service for multi-agent LLM orchestration.
"""
import os

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from api.routes import router as api_router
from core import config

app = FastAPI(title="OrbitScribe Swarm", version="1.0.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://127.0.0.1:*", "vscode-webview://*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Include API routes
app.include_router(api_router, prefix="/api")

# Legacy direct endpoints for OrbitScribe HTML compatibility
@app.get("/api/health")
async def health():
    return {"status": "ok", "api_mode": config.API_MODE, "version": "1.0.0"}

@app.get("/api/mode")
async def get_mode():
    return {"mode": config.API_MODE}

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host=config.HOST, port=config.PORT, log_level="info")
