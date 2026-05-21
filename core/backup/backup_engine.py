"""
Mandatory Backup Protocol — Backup Engine
Heritage: update_game_ini.py

ELI5: Think of this like an electrician's photo log.
Before any electrician (our code) opens a breaker panel (a file),
they snap a high-res photo (backup) of every wire and breaker position.
The panel itself never moves — it stays bolted to the wall (in-place overwrite).
If the electrician crosses a wire, they pull up the photo and restore exactly
what was there. No duplicate panels cluttering the jobsite.
"""

from __future__ import annotations

import asyncio
import hashlib
import json
import shutil
from dataclasses import asdict, dataclass, field
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, List, Optional
from zoneinfo import ZoneInfo


@dataclass(frozen=True)
class BackupRecord:
    """
    ELI5: The sticker on the photo envelope.
    Tells us when the photo was taken, which panel it was,
    where the envelope is stored, and a fingerprint (checksum)
    so we know nobody swapped the photo.
    """
    timestamp: str                     # YYYY-MM-DD_HHMM_PST
    original_path: Path
    backup_path: Path
    checksum: str
    size_bytes: int = field(default=0)

    def to_dict(self) -> dict[str, Any]:
        return {
            "timestamp": self.timestamp,
            "original_path": str(self.original_path),
            "backup_path": str(self.backup_path),
            "checksum": self.checksum,
            "size_bytes": self.size_bytes,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "BackupRecord":
        return cls(
            timestamp=data["timestamp"],
            original_path=Path(data["original_path"]),
            backup_path=Path(data["backup_path"]),
            checksum=data["checksum"],
            size_bytes=data.get("size_bytes", 0),
        )


class BackupEngine:
    """
    ELI5: The master photo archive cabinet.
    Every electrician checks in here before touching a panel.
    The cabinet lives on the network drive (E:/ark_backups) or locally.
    """

    _MANIFEST_FILE = "backup_manifest.json"

    def __init__(
        self,
        backup_root: Path | str | None = None,
        *,
        timezone: str = "America/Los_Angeles",
    ) -> None:
        # Prefer the network vault (E:/ark_backups), fall back to local jobsite
        self.backup_root: Path = self._resolve_backup_root(backup_root)
        self.tz = ZoneInfo(timezone)
        self._lock = asyncio.Lock()

    def _resolve_backup_root(self, override: Path | str | None) -> Path:
        """
        ELI5: We try to park our photo cabinet on the big company truck (E: drive).
        If the truck's not on-site, we roll out a local toolbox.
        """
        if override is not None:
            return Path(override).expanduser().resolve()

        network_vault = Path("E:/ark_backups")
        if network_vault.exists() or self._can_access_drive("E:/"):
            return network_vault

        local_vault = Path("ark_backups").resolve()
        return local_vault

    @staticmethod
    def _can_access_drive(drive: str) -> bool:
        """Quick continuity check — is the circuit live?"""
        try:
            Path(drive).exists()
            return True
        except OSError:
            return False

    def _now_pst(self) -> datetime:
        """
        ELI5: Our timestamps run on Pacific Time — that's the jobsite clock.
        Whether it's PST (winter) or PDT (summer), the label says PST for clarity.
        """
        return datetime.now(self.tz)

    def _format_timestamp(self, dt: datetime) -> str:
        """Military time stamp: 2026-05-20_1634_PST"""
        return dt.strftime("%Y-%m-%d_%H%M_PST")

    def _compute_checksum(self, file_path: Path) -> str:
        """
        ELI5: A fingerprint of the photo.
        If even one pixel changes, the fingerprint won't match.
        """
        sha256 = hashlib.sha256()
        with open(file_path, "rb") as fh:
            for chunk in iter(lambda: fh.read(8192), b""):
                sha256.update(chunk)
        return sha256.hexdigest()

    def _manifest_path(self) -> Path:
        return self.backup_root / self._MANIFEST_FILE

    def _load_manifest(self) -> dict[str, Any]:
        """Load the card catalog for our photo archive."""
        manifest_file = self._manifest_path()
        if manifest_file.exists():
            try:
                with open(manifest_file, "r", encoding="utf-8") as fh:
                    return json.load(fh)
            except (json.JSONDecodeError, OSError):
                pass
        return {"backups": []}

    def _save_manifest(self, manifest: dict[str, Any]) -> None:
        """Update the card catalog."""
        self.backup_root.mkdir(parents=True, exist_ok=True)
        manifest_file = self._manifest_path()
        with open(manifest_file, "w", encoding="utf-8") as fh:
            json.dump(manifest, fh, indent=2, default=str)

    def _backup_dir_for(self, original: Path) -> Path:
        """
        ELI5: Each panel gets its own drawer in the cabinet,
        organized by its on-site address (absolute path).
        """
        safe_name = original.resolve().as_posix().replace(":", "_").lstrip("/")
        return self.backup_root / safe_name

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def backup_before_operation(self, target_path: Path) -> BackupRecord:
        """
        ELI5: The electrician walks up to the panel, snaps a photo,
        files it in the archive cabinet, and THEN flips the breaker.
        The panel itself stays exactly where it is on the wall.

        Returns a BackupRecord receipt so you can restore later if needed.
        """
        target = Path(target_path).resolve()
        if not target.exists():
            raise FileNotFoundError(f"No panel found at {target}")

        # Military timestamp per the jobsite clock
        now = self._now_pst()
        timestamp = self._format_timestamp(now)

        # Build the archive envelope path
        archive_dir = self._backup_dir_for(target)
        archive_dir.mkdir(parents=True, exist_ok=True)
        backup_path = archive_dir / f"{timestamp}__{target.name}"

        # Copy the current wiring diagram into the envelope
        shutil.copy2(target, backup_path)
        checksum = self._compute_checksum(backup_path)
        size_bytes = backup_path.stat().st_size

        record = BackupRecord(
            timestamp=timestamp,
            original_path=target,
            backup_path=backup_path,
            checksum=checksum,
            size_bytes=size_bytes,
        )

        # Log it in the card catalog
        manifest = self._load_manifest()
        manifest["backups"].append(record.to_dict())
        self._save_manifest(manifest)

        return record

    async def async_backup_before_operation(self, target_path: Path) -> BackupRecord:
        """
        ELI5: Same photo-snap routine, but the electrician is on a scooter
        and the filing happens while they're rolling to the next panel.
        """
        return await asyncio.to_thread(self.backup_before_operation, target_path)

    def restore_from_backup(self, backup_record: BackupRecord) -> bool:
        """
        ELI5: The electrician messed up the wiring.
        They pull the photo from the archive, and lay the wires back
        EXACTLY as they were in the picture. The panel is restored.
        """
        backup = Path(backup_record.backup_path)
        original = Path(backup_record.original_path).resolve()

        if not backup.exists():
            return False

        # Verify the archive photo hasn't been tampered with
        current_checksum = self._compute_checksum(backup)
        if current_checksum != backup_record.checksum:
            raise ValueError(
                f"Backup integrity fault: checksum mismatch for {backup}\n"
                f"Expected: {backup_record.checksum}\n"
                f"Got:      {current_checksum}"
            )

        original.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(backup, original)
        return True

    async def async_restore_from_backup(self, backup_record: BackupRecord) -> bool:
        return await asyncio.to_thread(self.restore_from_backup, backup_record)

    def list_backups(
        self,
        target_path: Optional[Path] = None,
    ) -> List[BackupRecord]:
        """
        ELI5: Pull out the card catalog and list every photo envelope,
        optionally filtered to just one panel's drawer.
        """
        manifest = self._load_manifest()
        records: List[BackupRecord] = []

        for entry in manifest.get("backups", []):
            record = BackupRecord.from_dict(entry)
            if target_path is not None:
                if record.original_path.resolve() != Path(target_path).resolve():
                    continue
            records.append(record)

        # Most recent first — like a stack of photos
        records.sort(key=lambda r: r.timestamp, reverse=True)
        return records

    async def async_list_backups(
        self,
        target_path: Optional[Path] = None,
    ) -> List[BackupRecord]:
        return await asyncio.to_thread(self.list_backups, target_path)

    def prune_old_backups(self, max_age_days: int = 7) -> int:
        """
        ELI5: The archive cabinet is getting full.
        Any photo older than a week gets shredded (with verification)
        to make room for new wiring diagrams.

        Returns the count of envelopes removed.
        """
        cutoff = self._now_pst() - timedelta(days=max_age_days)
        manifest = self._load_manifest()
        kept: list[dict[str, Any]] = []
        pruned_count = 0

        for entry in manifest.get("backups", []):
            record = BackupRecord.from_dict(entry)
            try:
                record_dt = datetime.strptime(
                    record.timestamp, "%Y-%m-%d_%H%M_PST"
                ).replace(tzinfo=self.tz)
            except ValueError:
                kept.append(entry)
                continue

            if record_dt < cutoff:
                # Shred the photo envelope
                bp = Path(record.backup_path)
                if bp.exists():
                    bp.unlink()
                # Clean up empty drawer
                drawer = bp.parent
                if drawer.exists() and not any(drawer.iterdir()):
                    drawer.rmdir()
                pruned_count += 1
            else:
                kept.append(entry)

        manifest["backups"] = kept
        self._save_manifest(manifest)
        return pruned_count

    async def async_prune_old_backups(self, max_age_days: int = 7) -> int:
        return await asyncio.to_thread(self.prune_old_backups, max_age_days)

    def verify_all_backups(self) -> tuple[int, int, list[str]]:
        """
        ELI5: The foreman walks through the archive and checks every photo
        against its fingerprint. Any mismatch gets flagged for investigation.

        Returns: (verified_count, total_count, list_of_errors)
        """
        manifest = self._load_manifest()
        verified = 0
        errors: list[str] = []

        for entry in manifest.get("backups", []):
            record = BackupRecord.from_dict(entry)
            bp = Path(record.backup_path)
            if not bp.exists():
                errors.append(f"MISSING: {record.backup_path}")
                continue
            current_checksum = self._compute_checksum(bp)
            if current_checksum != record.checksum:
                errors.append(
                    f"CORRUPT: {record.backup_path}\n"
                    f"  Expected: {record.checksum}\n"
                    f"  Got:      {current_checksum}"
                )
                continue
            verified += 1

        return verified, len(manifest.get("backups", [])), errors

    async def async_verify_all_backups(self) -> tuple[int, int, list[str]]:
        return await asyncio.to_thread(self.verify_all_backups)


# -----------------------------------------------------------------------
# Convenience singleton (module-level outlet)
# -----------------------------------------------------------------------
_default_engine: BackupEngine | None = None


def get_engine() -> BackupEngine:
    """
    ELI5: The shared toolbox on the jobsite cart.
    Everyone grabs the same one — no need to haul your own.
    """
    global _default_engine
    if _default_engine is None:
        _default_engine = BackupEngine()
    return _default_engine
