"""
Twilio MMS Gateway Interface — Twilio Client

Think of this like a fancy intercom system for your smart home.
It can send plain voice messages (SMS), send voice messages with photos (MMS),
and even attach little picture charts so Mom can SEE what's happening
in the house, not just hear about it.
"""

from __future__ import annotations

import asyncio
from typing import Iterable

from twilio.rest import Client as TwilioRestClient
from twilio.base.exceptions import TwilioRestException


# =============================================================================
# Twilio Client — The smart intercom
# =============================================================================

class TwilioClient:
    """
    This is the intercom box on the wall.
    It knows Twilio's phone number and secret password,
    and it can ring Mom's phone to deliver messages.
    """

    def __init__(self, account_sid: str, auth_token: str) -> None:
        """
        Plug the intercom into the wall.
        We need Twilio's account number and password to work.
        """
        self.account_sid = account_sid
        self.auth_token = auth_token
        self._client: TwilioRestClient | None = None
        if account_sid and auth_token:
            self._client = TwilioRestClient(account_sid, auth_token)

    # -------------------------------------------------------------------------
    # Public API
    # -------------------------------------------------------------------------

    async def send_sms(
        self,
        to: str,
        from_: str,
        body: str,
    ) -> str | None:
        """
        Send a plain text message.
        Like speaking into the intercom — just words, no pictures.
        """
        if self._client is None:
            return None

        loop = asyncio.get_event_loop()
        try:
            message = await loop.run_in_executor(
                None,
                lambda: self._client.messages.create(  # type: ignore[union-attr]
                    to=to,
                    from_=from_,
                    body=body,
                ),
            )
            return message.sid  # type: ignore[union-attr]
        except TwilioRestException as exc:
            # The intercom line was busy — log it and move on
            return None

    async def send_mms(
        self,
        to: str,
        from_: str,
        body: str,
        media_urls: Iterable[str],
    ) -> str | None:
        """
        Send a text with attached photos.
        Like slipping snapshots into the intercom message tube.
        """
        if self._client is None:
            return None

        loop = asyncio.get_event_loop()
        try:
            message = await loop.run_in_executor(
                None,
                lambda: self._client.messages.create(  # type: ignore[union-attr]
                    to=to,
                    from_=from_,
                    body=body,
                    media_url=list(media_urls),
                ),
            )
            return message.sid  # type: ignore[union-attr]
        except TwilioRestException:
            return None

    async def send_mms_with_image(
        self,
        to: str,
        from_: str,
        body: str,
        media_url: str,
    ) -> str | None:
        """
        Send a text with ONE photo attached.
        This is the quick way when you only have one snapshot to share.
        Like sending a single Polaroid through the mail slot.
        """
        return await self.send_mms(
            to=to,
            from_=from_,
            body=body,
            media_urls=[media_url],
        )

    async def fetch_message_status(self, message_sid: str) -> dict[str, str | None]:
        """
        Check if a message was delivered.
        Like peeking at the mailbox to see if the letter arrived yet.
        """
        if self._client is None:
            return {"status": "no_client", "error": "Twilio not configured"}

        loop = asyncio.get_event_loop()
        try:
            message = await loop.run_in_executor(
                None,
                lambda: self._client.messages(message_sid).fetch(),  # type: ignore[union-attr]
            )
            return {
                "status": message.status,  # type: ignore[union-attr]
                "error": message.error_message,  # type: ignore[union-attr]
            }
        except TwilioRestException as exc:
            return {"status": "error", "error": str(exc)}

    # -------------------------------------------------------------------------
    # Batch helpers
    # -------------------------------------------------------------------------

    async def broadcast_sms(
        self,
        recipients: Iterable[str],
        from_: str,
        body: str,
    ) -> dict[str, str | None]:
        """
        Send the SAME text to a bunch of people at once.
        Like using the "all-call" button on an apartment intercom.
        """
        results: dict[str, str | None] = {}
        for recipient in recipients:
            sid = await self.send_sms(to=recipient, from_=from_, body=body)
            results[recipient] = sid
        return results
