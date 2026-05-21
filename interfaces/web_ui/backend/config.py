"""
ELI5: This is the label sheet inside your electrical panel door.
       It tells every electrician (developer) what voltage (settings)
       each circuit expects, so nobody accidentally fries a wire.
"""

from typing import List
from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    """House rules written on the inside of the breaker-box door."""

    app_name: str = "SimplePod Swarm Backend"
    debug: bool = False
    cors_origins: List[str] = ["http://localhost:3000", "http://localhost:5173"]
    cors_allow_credentials: bool = True
    cors_allow_methods: List[str] = ["*"]
    cors_allow_headers: List[str] = ["*"]

    class Config:
        # ELI5: Every setting can be overridden by sticky-notes (env vars)
        #       that start with "SIMPLEPOD_" so they’re easy to spot.
        env_prefix = "SIMPLEPOD_"
        env_file = ".env"
        extra = "ignore"


# ELI5: One master label sheet shared by the whole house.
settings = Settings()
