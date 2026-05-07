"""
OrbitScribe Swarm Backend
FastAPI service for multi-agent LLM orchestration.
"""
import os
import socket

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from api.routes import router as api_router
from core import config

app = FastAPI(title="OrbitScribe Swarm", version="3.0.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Include API routes
app.include_router(api_router, prefix="/api")

# Legacy direct endpoints for OrbitScribe HTML compatibility
@app.get("/api/health")
async def health():
    return {"status": "ok", "api_mode": config.API_MODE, "version": "3.0.0"}

@app.get("/api/mode")
async def get_mode():
    return {"mode": config.API_MODE}

if __name__ == "__main__":
    import uvicorn

    # Create socket with SO_REUSEADDR so we can rebind immediately after restart
    # (prevents "address already in use" errors on Windows when old sockets are in TIME_WAIT)
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    try:
        sock.bind((config.HOST, config.PORT))
    except OSError as e:
        print(f"[FATAL] Could not bind to {config.HOST}:{config.PORT} — {e}")
        raise

    uvicorn_config = uvicorn.Config(app, log_level="info")
    server = uvicorn.Server(uvicorn_config)
    server.run(sockets=[sock])
