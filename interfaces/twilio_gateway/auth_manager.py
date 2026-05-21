"""
Twilio MMS Gateway Interface — Auth Manager

Think of this like a smart lock system on your front door.
Different people have different keys:
- Mom has a gold key (admin) — she can do EVERYTHING.
- Your sibling has a silver key (operator) — they can turn lights on/off.
- A neighbor has a bronze key (observer) — they can only peek through the window.

This file checks whose key is at the door and decides what they're allowed to do.
"""

from __future__ import annotations

import hashlib
import secrets
from dataclasses import dataclass, field
from typing import Iterable

from pydantic import BaseModel, Field, field_validator


# =============================================================================
# Role Definitions — Like colored keycards
# =============================================================================

class Role(str, Enum):
    """
    The three colors of keycards.
    Each color opens different doors in the house.
    """
    OBSERVER = "observer"
    OPERATOR = "operator"
    ADMIN = "admin"


class Role(str, Enum):
    """
    The three colors of keycards.
    Each color opens different doors in the house.
    """
    OBSERVER = "observer"
    OPERATOR = "operator"
    ADMIN = "admin"


# =============================================================================
# Permission Matrix — Like a chart on the fridge showing who can do what
# =============================================================================

# This is the master list of chores and which keycards can do them.
# It's like a chore chart with checkmarks.
PERMISSIONS: dict[Role, set[str]] = {
    Role.ADMIN: {
        "status", "agents", "nodes", "breaker", "stop", "picture", "help",
        "register", "unregister", "promote", "demote",
    },
    Role.OPERATOR: {
        "status", "agents", "nodes", "breaker", "stop", "picture", "help",
    },
    Role.OBSERVER: {
        "status", "agents", "nodes", "help",
    },
}


# =============================================================================
# Data Models — Like a guest book by the door
# =============================================================================

class PhoneRecord(BaseModel):
    """
    One entry in the guest book.
    It stores a phone number, the person's name, their keycard color,
    and a secret PIN (like a backup password).
    """
    phone_number: str = Field(..., min_length=10)
    name: str = Field(default="Guest")
    role: Role = Field(default=Role.OBSERVER)
    is_active: bool = Field(default=True)
    pin_hash: str | None = Field(default=None)

    @field_validator("phone_number", mode="before")
    @classmethod
    def _normalize_phone(cls, value: str) -> str:
        """
        Phone numbers are like shoes at the door — messy.
        This tidies them up so +1 (555) 123-4567 becomes +15551234567.
        """
        return "".join(ch for ch in str(value) if ch.isdigit() or ch == "+").strip()


@dataclass(frozen=True, slots=True)
class AuthResult:
    """
    This is the little green or red light by the door after scanning a keycard.
    It says: YES you're in, WHO you are, and WHAT you can touch.
    """
    authorized: bool
    phone_number: str
    role: str
    name: str
    permissions: tuple[str, ...] = field(default_factory=tuple)


# =============================================================================
# Auth Manager — The smart lock brain
# =============================================================================

class AuthManager:
    """
    This is the brain inside the smart lock.
    It reads keycards, looks them up in the guest book,
    and decides who gets to come inside.
    """

    def __init__(self) -> None:
        """
        Set up the lock with an empty guest book.
        In a real house, you'd load this from a safe (database).
        """
        self._registry: dict[str, PhoneRecord] = {}

    # -------------------------------------------------------------------------
    # Public API
    # -------------------------------------------------------------------------

    def authenticate(self, phone_number: str) -> AuthResult:
        """
        Scan a keycard (phone number) and decide if the door opens.
        It's like the little beep and flash when you tap your fob.
        """
        normalized = self._normalize(phone_number)
        record = self._registry.get(normalized)

        if record is None or not record.is_active:
            return AuthResult(
                authorized=False,
                phone_number=normalized,
                role=Role.OBSERVER.value,
                name="Unknown",
                permissions=(),
            )

        perms = PERMISSIONS.get(record.role, set())
        return AuthResult(
            authorized=True,
            phone_number=normalized,
            role=record.role.value,
            name=record.name,
            permissions=tuple(sorted(perms)),
        )

    def can(self, phone_number: str, action: str) -> bool:
        """
        Quick check: Does this person's keycard let them do THIS specific thing?
        Like asking "Can my sibling use the oven?" and checking the rules.
        """
        result = self.authenticate(phone_number)
        if not result.authorized:
            return False
        return action in result.permissions

    def register(
        self,
        phone_number: str,
        name: str,
        role: Role = Role.OBSERVER,
        pin: str | None = None,
    ) -> PhoneRecord:
        """
        Add a new person to the guest book and cut them a keycard.
        Only the homeowner (admin) should be able to do this.
        It's like adding a fingerprint to the smart lock.
        """
        normalized = self._normalize(phone_number)
        record = PhoneRecord(
            phone_number=normalized,
            name=name,
            role=role,
            is_active=True,
            pin_hash=self._hash_pin(pin) if pin else None,
        )
        self._registry[normalized] = record
        return record

    def unregister(self, phone_number: str) -> bool:
        """
        Remove someone's keycard from the system.
        Like deleting a fingerprint from the smart lock.
        """
        normalized = self._normalize(phone_number)
        if normalized in self._registry:
            del self._registry[normalized]
            return True
        return False

    def promote(self, phone_number: str, new_role: Role) -> bool:
        """
        Upgrade someone's keycard color.
        Like giving the babysitter a better key so they can lock up too.
        """
        normalized = self._normalize(phone_number)
        record = self._registry.get(normalized)
        if record is None:
            return False
        updated = PhoneRecord(
            phone_number=record.phone_number,
            name=record.name,
            role=new_role,
            is_active=record.is_active,
            pin_hash=record.pin_hash,
        )
        self._registry[normalized] = updated
        return True

    def demote(self, phone_number: str, new_role: Role) -> bool:
        """
        Downgrade someone's keycard color.
        Like taking away oven privileges after a burnt pizza.
        """
        return self.promote(phone_number, new_role)

    def list_users(self) -> Iterable[PhoneRecord]:
        """
        Read the whole guest book.
        Like flipping through the keycard log to see who has access.
        """
        return self._registry.values()

    def verify_pin(self, phone_number: str, pin: str) -> bool:
        """
        Check a backup password.
        Like entering a numeric code on the keypad when your phone is dead.
        """
        normalized = self._normalize(phone_number)
        record = self._registry.get(normalized)
        if record is None or record.pin_hash is None:
            return False
        return secrets.compare_digest(record.pin_hash, self._hash_pin(pin))

    # -------------------------------------------------------------------------
    # Helpers
    # -------------------------------------------------------------------------

    @staticmethod
    def _normalize(phone_number: str) -> str:
        """
        Clean up a phone number so it always matches.
        Like making sure the keycard reader doesn't care if your
        key is upside-down.
        """
        return "".join(ch for ch in phone_number if ch.isdigit() or ch == "+").strip()

    @staticmethod
    def _hash_pin(pin: str) -> str:
        """
        Scramble a PIN so we never store the real number.
        It's like writing a secret code instead of the real password.
        """
        return hashlib.sha256(pin.encode("utf-8")).hexdigest()
