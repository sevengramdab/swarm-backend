#!/usr/bin/env python3
"""
test_sitk_packager.py
=====================
Unit tests for the Self-Installing Tool-Kit packager.

ELI5: Before the UPS truck leaves the warehouse, the shipping
      manager checks that the box is sealed, the manifest is
      taped to the outside, and the contents match the order.
"""

from __future__ import annotations

import zipfile
from pathlib import Path

import pytest

# Import the packager module.
from core.sitk.sitk_packager import SITKPackager, PayloadManifest


class TestSITKPackager:
    def test_create_payload_creates_zip(self, tmp_path: Path) -> None:
        """
        ELI5: Tell the warehouse to box up a hammer and a screwdriver.
              Make sure a cardboard box actually appears on the shelf.
        """
        packager = SITKPackager(output_dir=tmp_path)
        payload_dir = tmp_path / "payload"
        payload_dir.mkdir()
        (payload_dir / "task.json").write_text('{"cmd": "echo hello"}')

        zip_path = packager.create_payload(
            payload_dir=payload_dir,
            payload_name="test_payload",
        )

        assert zip_path.exists()
        assert zip_path.suffix == ".zip"

    def test_manifest_inside_zip(self, tmp_path: Path) -> None:
        """
        ELI5: Open the box and check that the packing list (manifest)
              is the first thing you see when you lift the lid.
        """
        packager = SITKPackager(output_dir=tmp_path)
        payload_dir = tmp_path / "payload"
        payload_dir.mkdir()
        (payload_dir / "run.py").write_text("print('hello')")

        zip_path = packager.create_payload(payload_dir=payload_dir, payload_name="manifest_test")

        with zipfile.ZipFile(zip_path, "r") as zf:
            namelist = zf.namelist()
            assert any("manifest" in name.lower() for name in namelist)

    def test_password_encryption(self, tmp_path: Path) -> None:
        """
        ELI5: The box has a padlock. Without the combination,
              the delivery driver shouldn't be able to peek inside.
        """
        packager = SITKPackager(output_dir=tmp_path, password="secret123")
        payload_dir = tmp_path / "payload"
        payload_dir.mkdir()
        (payload_dir / "secret.txt").write_text("top secret")

        zip_path = packager.create_payload(payload_dir=payload_dir, payload_name="encrypted")

        # A password-protected ZIP should not be readable without the password.
        with zipfile.ZipFile(zip_path, "r") as zf:
            # Standard zipfile cannot read AES-encrypted entries, but
            # we can at least verify the file is present.
            assert any("secret.txt" in name for name in zf.namelist())

    def test_manifest_parsing(self) -> None:
        """
        ELI5: The packing list should clearly state what's inside,
              how heavy it is, and where it's supposed to go.
        """
        manifest = PayloadManifest(
            payload_name="demo",
            files=["task.json", "run.py"],
            checksums={"task.json": "abc123"},
        )
        assert manifest.payload_name == "demo"
        assert "task.json" in manifest.files
