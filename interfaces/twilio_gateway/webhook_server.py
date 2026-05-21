"""
Twilio MMS Gateway Interface — Webhook Server

Think of this like a smart doorbell for your home automation system.
When Mom sends a text, it's like she's ringing the doorbell.
This code checks it's really Mom (not a stranger), makes sure she doesn't
ring too many times (rate limiting), and then lets her in to give commands.
"""

from __future__ import annotations

import hmac
import hashlib
import time
from typing import Annotated

from fastapi import FastAPI, Form, Request, HTTPException, Depends, status
from fastapi.responses import PlainTextResponse
from pydantic import BaseModel, Field, field_validator
from twilio.request_validator import RequestValidator

from command_parser import CommandParser, ParsedCommand
from response_builder import ResponseBuilder
from auth_manager import AuthManager, AuthResult
from twilio_client import TwilioClient

# =============================================================================
# Pydantic Models — Like labeled bins for organizing mail
# =============================================================================

class TwilioWebhookPayload(BaseModel):
    """
    This is like a labeled basket where we sort all the pieces
    of a text message when it arrives from Twilio.
    """
    from_number: str = Field(..., alias="From")
    to_number: str = Field(..., alias="To")
    body: str = Field(default="", alias="Body")
    num_media: int = Field(default=0, alias="NumMedia")
    media_url_0: str | None = Field(default=None, alias="MediaUrl0")
    message_sid: str = Field(..., alias="MessageSid")

    @field_validator("from_number", "to_number", mode="before")
    @classmethod
    def _normalize_phone(cls, value: str) -> str:
        """
        Phone numbers come in messy like shoes at the front door.
        This tidies them up so they always look the same.
        """
        cleaned = "".join(ch for ch in value if ch.isdigit() or ch == "+")
        return cleaned.strip()

    @field_validator("body", mode="before")
    @classmethod
    def _strip_body(cls, value: str | None) -> str:
        """
        Sometimes texts have extra spaces like crumbs on a counter.
        This wipes them clean.
        """
        return (value or "").strip()


class WebhookConfig(BaseModel):
    """
    These are the house rules — like a notepad by the door
    with passwords and speed limits written down.
    """
    twilio_account_sid: str = Field(default="")
    twilio_auth_token: str = Field(default="")
    rate_limit_window_seconds: int = Field(default=60)
    rate_limit_max_requests: int = Field(default=10)


# =============================================================================
# Rate Limiter — Like a timer on a water faucet
# =============================================================================

class SlidingWindowRateLimiter:
    """
    Imagine a mom who keeps pressing the light switch on and off too fast.
    This is like a little timer that says "Wait a minute!" if she presses
    it too many times in a row.
    """

    def __init__(self, window_seconds: int = 60, max_requests: int = 10) -> None:
        self.window_seconds = window_seconds
        self.max_requests = max_requests
        self._buckets: dict[str, list[float]] = {}

    def is_allowed(self, key: str) -> bool:
        """
        Checks if this person still has "presses" left in their bucket.
        It's like counting how many cookies are left in the jar.
        """
        now = time.time()
        window_start = now - self.window_seconds

        # Grab the old list of timestamps, or start a fresh empty jar
        timestamps = self._buckets.get(key, [])

        # Throw away the stale cookies (too old to count)
        timestamps = [ts for ts in timestamps if ts > window_start]

        if len(timestamps) >= self.max_requests:
            self._buckets[key] = timestamps
            return False

        timestamps.append(now)
        self._buckets[key] = timestamps
        return True


# =============================================================================
# Webhook Server — The smart front door
# =============================================================================

class TwilioWebhookServer:
    """
    This is the whole smart front door system.
    It listens for the doorbell (webhook), checks ID, and decides
    what to do next — just like a home automation hub.
    """

    def __init__(self, config: WebhookConfig) -> None:
        self.config = config
        self.app = FastAPI(title="SimplePod Twilio Gateway", version="1.0.0")
        self.rate_limiter = SlidingWindowRateLimiter(
            window_seconds=config.rate_limit_window_seconds,
            max_requests=config.rate_limit_max_requests,
        )
        self.auth_manager = AuthManager()
        self.command_parser = CommandParser()
        self.response_builder = ResponseBuilder()
        self.twilio_client = TwilioClient(
            account_sid=config.twilio_account_sid,
            auth_token=config.twilio_auth_token,
        )
        self._validator: RequestValidator | None = None
        if config.twilio_auth_token:
            self._validator = RequestValidator(config.twilio_auth_token)
        self._register_routes()

    def _register_routes(self) -> None:
        """
        This sticks the "doorbell buttons" onto the house.
        Without this, the doorbell wouldn't be connected to anything!
        """
        self.app.post("/webhook/sms", response_class=PlainTextResponse)(self.handle_sms)
        self.app.get("/health")(self.health_check)

    def _verify_twilio_signature(self, request: Request) -> bool:
        """
        This is like checking the peephole before opening the door.
        Twilio signs every request with a secret handshake.
        If the handshake doesn't match, we don't open up!
        """
        if self._validator is None:
            # No lock installed yet — assume it's safe (dev mode only!)
            return True

        url = str(request.url)
        params = dict(request.query_params)

        # For POST forms, Twilio also includes the form body in the signature
        try:
            signature = request.headers.get("X-Twilio-Signature", "")
        except Exception:
            return False

        return self._validator.validate(url, params, signature)

    async def health_check(self) -> dict[str, str]:
        """
        A quick "ping" to make sure the house lights are still on.
        Like asking "Is anyone home?" and hearing "Yep!"
        """
        return {"status": "ok", "gateway": "twilio"}

    async def handle_sms(
        self,
        request: Request,
        payload: Annotated[TwilioWebhookPayload, Depends()],
    ) -> str:
        """
        This is what happens when Mom texts the house.
        1. Check the peephole (signature)
        2. Check she's not spamming the doorbell (rate limit)
        3. Look up her keycard (auth)
        4. Read her note (parse command)
        5. Do what she asked (execute)
        6. Text her back with the answer (respond)
        """
        # --- Step 1: Peephole check ---
        if not self._verify_twilio_signature(request):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Invalid Twilio signature",
            )

        # --- Step 2: Doorbell spam check ---
        if not self.rate_limiter.is_allowed(payload.from_number):
            return self.response_builder.rate_limit_response(
                self.config.rate_limit_window_seconds
            )

        # --- Step 3: Keycard lookup ---
        auth_result: AuthResult = self.auth_manager.authenticate(payload.from_number)
        if not auth_result.authorized:
            return self.response_builder.unauthorized_response()

        # --- Step 4: Read Mom's note ---
        command: ParsedCommand = self.command_parser.parse(payload.body)

        # --- Step 5 & 6: Do the thing and text back ---
        return await self._execute_command(command, auth_result, payload)

    async def _execute_command(
        self,
        command: ParsedCommand,
        auth_result: AuthResult,
        payload: TwilioWebhookPayload,
    ) -> str:
        """
        This is the robot butler that actually walks around the house
        and does what Mom asked — then texts her a little report.
        """
        match command.action:
            case "status":
                return self.response_builder.status_response(auth_result.role)
            case "agents":
                return self.response_builder.agents_response()
            case "nodes":
                return self.response_builder.nodes_response()
            case "breaker":
                return self.response_builder.breaker_response(command.target)
            case "stop":
                if auth_result.role not in ("operator", "admin"):
                    return self.response_builder.permission_denied_response("stop")
                return self.response_builder.stop_response(command.target)
            case "picture":
                if auth_result.role == "observer":
                    return self.response_builder.permission_denied_response("picture")
                image_path = await self.response_builder.generate_status_chart()
                await self.twilio_client.send_mms_with_image(
                    to=payload.from_number,
                    from_=payload.to_number,
                    body=self.response_builder.status_response(auth_result.role),
                    media_url=f"file://{image_path}",
                )
                return self.response_builder.acknowledge_image_sent()
            case "help":
                return self.response_builder.help_response(auth_result.role)
            case _:
                return self.response_builder.unknown_command_response(command.raw_input)


def create_app(config: WebhookConfig | None = None) -> FastAPI:
    """
    This is like the electrician wiring up the whole house.
    Call this, and you get a fully working smart doorbell system.
    """
    if config is None:
        config = WebhookConfig()
    server = TwilioWebhookServer(config)
    return server.app
