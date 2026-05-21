#!/usr/bin/env python3
"""
test_backup_engine.py
=====================
Unit tests for the Mandatory Backup Protocol.

ELI5: Before the electrician touches the Main Breaker, we make sure
      the camera (backup engine) takes a photo and saves it to the
      fireproof safe (backup directory) with today's date and time.
"""

from __future__ import annotations

import shutil
from pathlib import Path

import pytest

from core.backup.backup_engine import BackupEngine, BackupRecord
from core.backup.safe_file_ops import safe_read, safe_write, SafeEdit


class TestBackupEngine:
    @pytest.fixture
    def engine(self, tmp_path: Path) -> BackupEngine:
        backup_dir = tmp_path / "ark_backups"
        return BackupEngine(backup_dir=backup_dir)

    @pytest.fixture
    def sample_file(self, tmp_path: Path) -> Path:
        target = tmp_path / "game.ini"
        target.write_text("original_content")
        return target

    def test_backup_creates_record(self, engine: BackupEngine, sample_file: Path) -> None:
        """
        ELI5: Take a photo of the breaker panel. The photo should
              end up in the safe with a label showing when it was taken.
        """
        record = engine.backup(sample_file)
        assert isinstance(record, BackupRecord)
        assert record.backup_path.exists()
        assert "PST" in record.timestamp_label or "PDT" in record.timestamp_label

    def test_restore_overwrites_in_place(self, engine: BackupEngine, sample_file: Path) -> None:
        """
        ELI5: The electrician made a mistake. Use the photo to redraw
              the wiring exactly as it was — right on the same panel,
              no duplicate panels allowed.
        """
        record = engine.backup(sample_file)
        sample_file.write_text("modified_content")
        assert sample_file.read_text() == "modified_content"

        success = engine.restore(record)
        assert success is True
        assert sample_file.read_text() == "original_content"

    def test_safe_write_backs_up_then_writes(self, tmp_path: Path) -> None:
        """
        ELI5: The safe file wrapper is like an electrician who refuses
              to touch a wire until they've photographed it first.
        """
        target = tmp_path / "config.json"
        target.write_text("{}")
        safe_write(target, '{"key": "value"}')
        assert target.read_text() == '{"key": "value"}'

    def test_safe_edit_context_manager_rollback(self, tmp_path: Path) -> None:
        """
        ELI5: The electrician opens the panel, starts working, but
              then drops their screwdriver across the bus bars (exception).
              The automatic safety system slams the panel shut and
              restores the original wiring from the photo.
        """
        target = tmp_path / "important.cfg"
        target.write_text("original")

        try:
            with SafeEdit(target) as safe_path:
                safe_path.write_text("halfway_done")
                raise RuntimeError("Sparks fly!")
        except RuntimeError:
            pass

        assert target.read_text() == "original"
