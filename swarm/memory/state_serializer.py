#!/usr/bin/env python3
"""
state_serializer.py
===================
Compressed state serialization for ephemeral handoff.

ELI5 Analogy:
  In AutoCAD, you can use ETRANSMIT to bundle a drawing with all
  its external references, fonts, and plot styles into a single
  ZIP file. That ZIP can be emailed to another office and opened
  perfectly. StateSerializer does the same thing for an agent's
  brain — it packs every thought (state) into a tiny suitcase
  (compressed bytes) with a version sticker, so the next agent
  can unpack it and keep working without missing a beat.
"""

from __future__ import annotations

import json
import struct
from dataclasses import dataclass
from typing import Any, Dict, Optional

import zstandard as zstd
from pydantic import BaseModel, Field


class CompressedState(BaseModel):
    """
    The suitcase — versioned, compressed, and labeled.

    ELI5: Like a shipping crate with a barcode (version),
          a weight stamp (original_size), and a packing list
          (schema_hash) so the receiving dock knows exactly
          what's inside before opening it.
    """

    version: int = 1
    data: bytes  # zstd-compressed JSON
    original_size: int
    schema_hash: str = ""  # simple hash of key structure for compatibility
    compression_level: int = 3


class StateSerializer:
    """
    The packing department.

    ELI5: This is the ETRANSMIT wizard in AutoCAD. You tell it
          which drawing (state dict) to send, it bundles every
          layer and block reference, squashes it with a heavy
          press (ZSTD compression), and slaps a version label
          on the crate so the recipient knows if their software
          can open it.
    """

    CURRENT_VERSION: int = 1

    def __init__(self, compression_level: int = 3) -> None:
        self.compression_level = compression_level
        self._compressor = zstd.ZstdCompressor(level=compression_level)
        self._decompressor = zstd.ZstdDecompressor()

    def serialize(self, state: Dict[str, Any]) -> CompressedState:
        """
        ELI5: Click ETRANSMIT → select all references → create ZIP.
              The original drawing might be 50 MB, but the ZIP
              is only 5 MB because compression squeezes out the
              empty whitespace and repeated patterns.
        """
        raw_json = json.dumps(state, separators=(",", ":"), ensure_ascii=False).encode("utf-8")
        original_size = len(raw_json)

        compressed = self._compressor.compress(raw_json)
        schema_hash = self._compute_schema_hash(state)

        return CompressedState(
            version=self.CURRENT_VERSION,
            data=compressed,
            original_size=original_size,
            schema_hash=schema_hash,
            compression_level=self.compression_level,
        )

    def deserialize(self, compressed_state: CompressedState) -> Dict[str, Any]:
        """
        ELI5: The receiving office gets the ZIP, checks the version
              label ("AutoCAD 2024 file? We have 2024, good."),
              unzips it, and opens the drawing exactly as it was
              in the original office.
        """
        if compressed_state.version != self.CURRENT_VERSION:
            raise ValueError(
                f"State version mismatch: expected {self.CURRENT_VERSION}, "
                f"got {compressed_state.version}"
            )

        raw_json = self._decompressor.decompress(compressed_state.data)
        if len(raw_json) != compressed_state.original_size:
            raise ValueError(
                f"Decompressed size mismatch: expected {compressed_state.original_size}, "
                f"got {len(raw_json)}"
            )

        return json.loads(raw_json.decode("utf-8"))

    @staticmethod
    def _compute_schema_hash(state: Dict[str, Any]) -> str:
        """
        ELI5: Before shipping, you make a quick sketch of the crate's
              contents — just the top-level categories (layers, blocks,
              dimensions). The receiving dock compares sketches to make
              sure they ordered the right thing.
        """
        if not isinstance(state, dict):
            return ""
        # Simple hash: sorted top-level keys joined.
        keys = sorted(state.keys())
        import hashlib
        return hashlib.sha256(",".join(keys).encode("utf-8")).hexdigest()[:16]

    def estimate_transfer_time(self, compressed_state: CompressedState, bandwidth_mbps: float = 100.0) -> float:
        """
        ELI5: The truck driver asks, "How big is the crate and what's
              the speed limit?" We divide crate size by speed limit
              to estimate delivery time.
        """
        bytes_per_second = (bandwidth_mbps * 1_000_000) / 8
        return len(compressed_state.data) / bytes_per_second
