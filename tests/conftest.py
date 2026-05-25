#!/usr/bin/env python3
# -*- coding: utf-8 -*-
import pytest
from simplepod import SimplePod#!/usr/bin/env python3
# Test edit file action#!/usr/bin/env python3
"""
conftest.py
===========
Shared pytest fixtures.

ELI5: Like the shared toolbox every electrician grabs from
      before starting a job. Instead of buying new pliers for
      every test, we keep one good pair here.
"""

from __future__ import annotations

import asyncio
import tempfile
from pathlib import Path
from typing import AsyncGenerator

import pytest
import pytest_asyncio


@pytest_asyncio.fixture
async def temp_dir() -> AsyncGenerator[Path, None]:
    """A clean workbench for each test."""
    with tempfile.TemporaryDirectory() as td:
        yield Path(td)


@pytest_asyncio.fixture
async def event_loop():
    """Provide a fresh event loop for async tests."""
    loop = asyncio.get_event_loop_policy().new_event_loop()
    yield loop
    loop.close()
