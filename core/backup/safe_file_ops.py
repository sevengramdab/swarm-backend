"""
Mandatory Backup Protocol — Safe File Operations
Heritage: update_game_ini.py

ELI5: These are the insulated gloves every electrician wears.
No matter how simple the job — tightening a screw, swapping a breaker —
the gloves go on FIRST. That means a photo (backup) gets snapped BEFORE
any hand touches the panel. The panel itself stays bolted to the wall;
we just open the door, do the work, and close it again.
"""

from __future__ import annotations

import asyncio
import json
from contextlib import contextmanager
from pathlib import Path
from typing import Any, Callable, Generator, overload

from .backup_engine import BackupEngine, BackupRecord, get_engine

# Optional YAML support — like having both standard and metric drivers
try:
    import yaml  # type: ignore[import]
    _YAML_AVAILABLE = True
except ImportError:
    _YAML_AVAILABLE = False


# -----------------------------------------------------------------------
# Core safe primitives
# -----------------------------------------------------------------------

def safe_read(
    path: Path | str,
    *,
    encoding: str = "utf-8",
    engine: BackupEngine | None = None,
) -> str:
    """
    ELI5: The electrician opens the panel door to read the labels.
    But first — *click* — a photo goes into the archive.
    The labels are read, the door stays shut afterward.
    """
    target = Path(path).resolve()
    eng = engine or get_engine()
    if target.exists():
        eng.backup_before_operation(target)
    # If the file doesn't exist, there's nothing to back up;
    # we let the caller handle the FileNotFoundError naturally.
    with open(target, "r", encoding=encoding) as fh:
        return fh.read()


async def async_safe_read(
    path: Path | str,
    *,
    encoding: str = "utf-8",
    engine: BackupEngine | None = None,
) -> str:
    """
    ELI5: Same label-reading job, but the electrician is on a scissor lift
    and the photo gets snapped while they're still hoisting up.
    """
    target = Path(path).resolve()
    eng = engine or get_engine()
    if target.exists():
        await eng.async_backup_before_operation(target)
    return await asyncio.to_thread(_read_text, target, encoding)


def _read_text(path: Path, encoding: str) -> str:
    with open(path, "r", encoding=encoding) as fh:
        return fh.read()


def safe_write(
    path: Path | str,
    content: str,
    *,
    encoding: str = "utf-8",
    engine: BackupEngine | None = None,
) -> BackupRecord | None:
    """
    ELI5: The electrician strips out the old wiring diagram and tapes up
    a brand-new one.  *Click* — photo FIRST.  Then the old sheet comes
    off the panel and the new one goes on, right in the same spot.
    """
    target = Path(path).resolve()
    eng = engine or get_engine()
    record = None
    if target.exists():
        record = eng.backup_before_operation(target)
    target.parent.mkdir(parents=True, exist_ok=True)
    with open(target, "w", encoding=encoding) as fh:
        fh.write(content)
    return record


async def async_safe_write(
    path: Path | str,
    content: str,
    *,
    encoding: str = "utf-8",
    engine: BackupEngine | None = None,
) -> BackupRecord | None:
    target = Path(path).resolve()
    eng = engine or get_engine()
    record = None
    if target.exists():
        record = await eng.async_backup_before_operation(target)
    target.parent.mkdir(parents=True, exist_ok=True)
    await asyncio.to_thread(_write_text, target, content, encoding)
    return record


def _write_text(path: Path, content: str, encoding: str) -> None:
    with open(path, "w", encoding=encoding) as fh:
        fh.write(content)


def safe_modify(
    path: Path | str,
    modifier_fn: Callable[[str], str],
    *,
    encoding: str = "utf-8",
    engine: BackupEngine | None = None,
) -> BackupRecord:
    """
    ELI5: The electrician needs to re-route two wires.
    *Click* — backup photo.  They read the current diagram,
    mentally trace the new route, then physically move the wires
    and tape the updated diagram back onto the panel.
    """
    target = Path(path).resolve()
    eng = engine or get_engine()
    if not target.exists():
        raise FileNotFoundError(f"No panel to modify at {target}")

    record = eng.backup_before_operation(target)
    with open(target, "r", encoding=encoding) as fh:
        original = fh.read()

    modified = modifier_fn(original)

    with open(target, "w", encoding=encoding) as fh:
        fh.write(modified)

    return record


async def async_safe_modify(
    path: Path | str,
    modifier_fn: Callable[[str], str],
    *,
    encoding: str = "utf-8",
    engine: BackupEngine | None = None,
) -> BackupRecord:
    target = Path(path).resolve()
    eng = engine or get_engine()
    if not target.exists():
        raise FileNotFoundError(f"No panel to modify at {target}")

    record = await eng.async_backup_before_operation(target)
    original = await asyncio.to_thread(_read_text, target, encoding)
    modified = modifier_fn(original)
    await asyncio.to_thread(_write_text, target, modified, encoding)
    return record


# -----------------------------------------------------------------------
# JSON operations
# -----------------------------------------------------------------------

def safe_json_load(
    path: Path | str,
    *,
    engine: BackupEngine | None = None,
    **json_kwargs: Any,
) -> Any:
    """
    ELI5: The panel has a digital display showing JSON schematics.
    Snap a photo, then read the display.
    """
    text = safe_read(path, engine=engine)
    return json.loads(text, **json_kwargs)


async def async_safe_json_load(
    path: Path | str,
    *,
    engine: BackupEngine | None = None,
    **json_kwargs: Any,
) -> Any:
    text = await async_safe_read(path, engine=engine)
    return json.loads(text, **json_kwargs)


def safe_json_dump(
    path: Path | str,
    data: Any,
    *,
    indent: int = 2,
    engine: BackupEngine | None = None,
    **json_kwargs: Any,
) -> BackupRecord | None:
    """
    ELI5: Upload a fresh JSON schematic to the panel's digital display.
    Photo first, then overwrite the display in-place.
    """
    payload = json.dumps(data, indent=indent, default=str, **json_kwargs)
    return safe_write(path, payload, engine=engine)


async def async_safe_json_dump(
    path: Path | str,
    data: Any,
    *,
    indent: int = 2,
    engine: BackupEngine | None = None,
    **json_kwargs: Any,
) -> BackupRecord | None:
    payload = json.dumps(data, indent=indent, default=str, **json_kwargs)
    return await async_safe_write(path, payload, engine=engine)


# -----------------------------------------------------------------------
# YAML operations
# -----------------------------------------------------------------------

def safe_yaml_load(
    path: Path | str,
    *,
    engine: BackupEngine | None = None,
    **yaml_kwargs: Any,
) -> Any:
    """
    ELI5: Some panels use old-school YAML blueprints instead of JSON.
    Same rule: photo first, then read the blueprint.
    """
    if not _YAML_AVAILABLE:
        raise ImportError(
            "YAML driver missing. Install PyYAML to use safe_yaml_load."
        )
    text = safe_read(path, engine=engine)
    return yaml.safe_load(text, **yaml_kwargs)


async def async_safe_yaml_load(
    path: Path | str,
    *,
    engine: BackupEngine | None = None,
    **yaml_kwargs: Any,
) -> Any:
    if not _YAML_AVAILABLE:
        raise ImportError(
            "YAML driver missing. Install PyYAML to use async_safe_yaml_load."
        )
    text = await async_safe_read(path, engine=engine)
    return yaml.safe_load(text, **yaml_kwargs)


def safe_yaml_dump(
    path: Path | str,
    data: Any,
    *,
    default_flow_style: bool = False,
    engine: BackupEngine | None = None,
    **yaml_kwargs: Any,
) -> BackupRecord | None:
    """
    ELI5: Post an updated YAML blueprint to the panel.
    Photo first, then tape the new blueprint right over the old one.
    """
    if not _YAML_AVAILABLE:
        raise ImportError(
            "YAML driver missing. Install PyYAML to use safe_yaml_dump."
        )
    payload = yaml.dump(data, default_flow_style=default_flow_style, **yaml_kwargs)
    return safe_write(path, payload, engine=engine)


async def async_safe_yaml_dump(
    path: Path | str,
    data: Any,
    *,
    default_flow_style: bool = False,
    engine: BackupEngine | None = None,
    **yaml_kwargs: Any,
) -> BackupRecord | None:
    if not _YAML_AVAILABLE:
        raise ImportError(
            "YAML driver missing. Install PyYAML to use async_safe_yaml_dump."
        )
    payload = yaml.dump(data, default_flow_style=default_flow_style, **yaml_kwargs)
    return await async_safe_write(path, payload, engine=engine)


# -----------------------------------------------------------------------
# Context manager for complex multi-step edits
# -----------------------------------------------------------------------

class SafeEdit:
    """
    ELI5: Sometimes the electrician has a 12-step rewiring plan.
    They can't finish in one motion — they need to:
      1. Snap the photo (backup)
      2. Open the panel
      3. Move wire A, test, move wire B, test again …
      4. Close the panel
    If anything goes wrong at step 7, the entire session can be rolled back
    to the original photo.

    Usage:
        with SafeEdit("/path/to/panel.ini") as edit:
            text = edit.content
            text = text.replace("old_breaker", "new_breaker")
            edit.content = text
            # … more steps …
        # On clean exit, the panel is overwritten with edit.content.
        # On exception, the original wiring is restored automatically.
    """

    @overload
    def __init__(
        self,
        path: Path | str,
        *,
        encoding: str = "utf-8",
        engine: BackupEngine | None = None,
        autocommit: bool = True,
    ) -> None: ...

    def __init__(
        self,
        path: Path | str,
        *,
        encoding: str = "utf-8",
        engine: BackupEngine | None = None,
        autocommit: bool = True,
    ) -> None:
        self.target = Path(path).resolve()
        self.encoding = encoding
        self.engine = engine or get_engine()
        self.autocommit = autocommit
        self._record: BackupRecord | None = None
        self._content: str = ""
        self._dirty = False
        self._entered = False

    @property
    def content(self) -> str:
        if not self._entered:
            raise RuntimeError("SafeEdit context not entered. Use 'with' statement.")
        return self._content

    @content.setter
    def content(self, value: str) -> None:
        if not self._entered:
            raise RuntimeError("SafeEdit context not entered. Use 'with' statement.")
        self._content = value
        self._dirty = True

    def __enter__(self) -> SafeEdit:
        # *Click* — photo first
        if self.target.exists():
            self._record = self.engine.backup_before_operation(self.target)
            with open(self.target, "r", encoding=self.encoding) as fh:
                self._content = fh.read()
        else:
            self._content = ""
        self._entered = True
        return self

    def __exit__(self, exc_type: Any, exc_val: Any, exc_tb: Any) -> None:
        try:
            if exc_type is not None:
                # Something sparked — restore from the photo
                if self._record is not None:
                    self.engine.restore_from_backup(self._record)
                return

            if self.autocommit and self._dirty:
                self.target.parent.mkdir(parents=True, exist_ok=True)
                with open(self.target, "w", encoding=self.encoding) as fh:
                    fh.write(self._content)
        finally:
            self._entered = False
            self._dirty = False

    async def __aenter__(self) -> SafeEdit:
        if self.target.exists():
            self._record = await self.engine.async_backup_before_operation(
                self.target
            )
            self._content = await asyncio.to_thread(
                _read_text, self.target, self.encoding
            )
        else:
            self._content = ""
        self._entered = True
        return self

    async def __aexit__(self, exc_type: Any, exc_val: Any, exc_tb: Any) -> None:
        try:
            if exc_type is not None:
                if self._record is not None:
                    await self.engine.async_restore_from_backup(self._record)
                return

            if self.autocommit and self._dirty:
                self.target.parent.mkdir(parents=True, exist_ok=True)
                await asyncio.to_thread(
                    _write_text, self.target, self._content, self.encoding
                )
        finally:
            self._entered = False
            self._dirty = False
