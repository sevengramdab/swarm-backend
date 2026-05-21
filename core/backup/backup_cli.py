"""
Mandatory Backup Protocol — Backup CLI
Heritage: update_game_ini.py

ELI5: This is the foreman's clipboard.
From the jobsite trailer, the foreman can:
  - Check how full the photo archive is (status)
  - Tell an electrician to rewind a panel to yesterday's wiring (restore)
  - Shred old photos older than a week (prune)
  - Walk the archive with a magnifying glass and compare fingerprints (verify)
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path
from typing import Sequence

from .backup_engine import BackupEngine, BackupRecord, get_engine


# -----------------------------------------------------------------------
# CLI command implementations
# -----------------------------------------------------------------------

def cmd_status(engine: BackupEngine, args: argparse.Namespace) -> int:
    """
    ELI5: The foreman opens the archive cabinet and counts drawers,
    photos, and total square footage of paper stored.
    """
    manifest_path = engine._manifest_path()
    backups = engine.list_backups()

    total_files = len(backups)
    unique_targets = len({b.original_path for b in backups})
    total_bytes = sum(b.size_bytes for b in backups)

    print("+==============================================+")
    print("|      SIMPLEPOD BACKUP ARCHIVE STATUS         |")
    print("+==============================================+")
    print(f"  Archive vault    : {engine.backup_root}")
    print(f"  Manifest         : {manifest_path}")
    print(f"  Timezone         : {engine.tz.key}")
    print()
    print(f"  Total backups    : {total_files}")
    print(f"  Unique panels    : {unique_targets}")
    print(f"  Total size       : {total_bytes:,} bytes ({_human_size(total_bytes)})")
    print("+==============================================+")
    return 0


def cmd_restore(engine: BackupEngine, args: argparse.Namespace) -> int:
    """
    ELI5: The foreman hands the electrician a specific photo envelope
    and says "Rewind this panel to exactly how it looked at 1634 on May 20."
    The electrician pulls the photo and restores the wiring.
    """
    target = Path(args.target).resolve()
    backups = engine.list_backups(target)

    if not backups:
        print(f"ERROR: No archived photos for panel {target}", file=sys.stderr)
        return 1

    chosen: BackupRecord | None = None
    if args.to_date:
        for b in backups:
            if b.timestamp == args.to_date:
                chosen = b
                break
        if chosen is None:
            print(
                f"ERROR: No backup with timestamp '{args.to_date}' found for {target}",
                file=sys.stderr,
            )
            print("Available timestamps:", file=sys.stderr)
            for b in backups:
                print(f"  - {b.timestamp}", file=sys.stderr)
            return 1
    else:
        chosen = backups[0]  # Most recent

    print(f"Restoring {target}")
    print(f"  From backup : {chosen.backup_path}")
    print(f"  Timestamp   : {chosen.timestamp}")
    print(f"  Checksum    : {chosen.checksum}")

    try:
        success = engine.restore_from_backup(chosen)
    except ValueError as exc:
        print(f"RESTORE FAILED — integrity fault:\n{exc}", file=sys.stderr)
        return 1

    if success:
        print("  Result      : [OK] RESTORED")
        return 0
    else:
        print("  Result      : [FAIL] BACKUP FILE MISSING", file=sys.stderr)
        return 1


def cmd_prune(engine: BackupEngine, args: argparse.Namespace) -> int:
    """
    ELI5: The archive cabinet is bursting at the seams.
    The foreman shreds every photo older than N days.
    """
    days = args.days
    print(f"Pruning backups older than {days} day(s) ...")
    count = engine.prune_old_backups(days)
    print(f"  Shredded {count} old photo envelope(s).")
    return 0


def cmd_verify(engine: BackupEngine, args: argparse.Namespace) -> int:
    """
    ELI5: The foreman walks every aisle of the archive with a UV lamp,
    checking each photo's hidden security watermark (checksum).
    Any mismatch is flagged immediately.
    """
    print("Running checksum verification across all backups ...")
    verified, total, errors = engine.verify_all_backups()

    print()
    print(f"  Verified : {verified} / {total}")
    print(f"  Faults   : {len(errors)}")

    if errors:
        print()
        print("FAULTS DETECTED:")
        for err in errors:
            print(f"  ! {err}")
        return 1

    print()
    print("[OK] All backups passed integrity check.")
    return 0


# -----------------------------------------------------------------------
# Helpers
# -----------------------------------------------------------------------

def _human_size(size_bytes: int) -> str:
    """ELI5: Convert raw byte count into something a human foreman can read."""
    for unit in ("B", "KB", "MB", "GB", "TB"):
        if size_bytes < 1024:
            return f"{size_bytes:.2f} {unit}"
        size_bytes /= 1024
    return f"{size_bytes:.2f} PB"


def _build_parser() -> argparse.ArgumentParser:
    """Wire up the foreman's clipboard with all available commands."""
    parser = argparse.ArgumentParser(
        prog="backup-cli",
        description="SimplePod Surgical Strike — Mandatory Backup Protocol CLI",
    )
    parser.add_argument(
        "--backup-root",
        type=str,
        default=None,
        help="Override the archive vault path (default: E:/ark_backups or ./ark_backups)",
    )

    sub = parser.add_subparsers(dest="command", required=True)

    # --- status ---
    sub.add_parser("status", help="Show archive vault statistics")

    # --- restore ---
    restore_p = sub.add_parser("restore", help="Restore a panel to a previous backup")
    restore_p.add_argument("target", type=str, help="Path to the original panel/file")
    restore_p.add_argument(
        "--to-date",
        type=str,
        default=None,
        help="Timestamp to restore to (YYYY-MM-DD_HHMM_PST). Default: most recent.",
    )

    # --- prune ---
    prune_p = sub.add_parser("prune", help="Remove old backups")
    prune_p.add_argument(
        "--days",
        type=int,
        default=7,
        help="Maximum age in days before shredding (default: 7)",
    )

    # --- verify ---
    sub.add_parser("verify", help="Verify checksum integrity of all backups")

    return parser


def main(argv: Sequence[str] | None = None) -> int:
    parser = _build_parser()
    args = parser.parse_args(argv)

    engine = get_engine()
    if args.backup_root:
        engine = BackupEngine(backup_root=args.backup_root)

    dispatch = {
        "status": cmd_status,
        "restore": cmd_restore,
        "prune": cmd_prune,
        "verify": cmd_verify,
    }

    handler = dispatch.get(args.command)
    if handler is None:
        parser.print_help()
        return 1

    return handler(engine, args)


if __name__ == "__main__":
    sys.exit(main())
