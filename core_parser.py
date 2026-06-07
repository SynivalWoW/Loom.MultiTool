"""core_parser.py — unified binary I/O for retroported .m2 / .skin files.

This is the foundation module of the headless Loom retroporting pipeline. It wraps the
existing low-level ``utils.binary.Binary`` helpers and ``utils.offsets`` enums in two thin,
context-managed reader/writer classes so the higher-level repair modules
(``combiner_repair``, ``asset_linker``, ``loom_dbc_generator``) never have to juggle raw
offsets directly.

It is deliberately pure-stdlib (``struct``/``os`` only) so it runs head-less on Linux/CI
without importing the dearpygui GUI or any Windows-only dependency.
"""

from __future__ import annotations

import struct
from typing import BinaryIO, Iterator, NamedTuple

from utils.binary import Binary
from utils.offsets import M2Offsets, SkinOffsets, SkinLengths, SkinBatchOffsets

MD20_MAGIC = b'MD20'
MD21_MAGIC = b'MD21'
SKIN_MAGIC = b'SKIN'

# global_flags bit (0x08) advertising that a textureCombinerCombos array trails the header.
FLAG_USE_TEXTURE_COMBINER_COMBOS = 0x08


class TextureBatch(NamedTuple):
    """A single render batch (texture unit / M2Batch) decoded from a .skin file."""

    flags: int
    shader_id: int
    skin_section_index: int
    color_index: int
    material_index: int
    texture_count: int
    texture_combo_index: int

    @property
    def max_combo_slot(self) -> int:
        """Highest textureCombinerCombos slot this batch reads.

        A batch consumes ``texture_count`` consecutive entries starting at
        ``texture_combo_index``; the last slot it touches is therefore
        ``texture_combo_index + texture_count - 1``.
        """
        count = self.texture_count if self.texture_count > 0 else 1
        return self.texture_combo_index + count - 1


class M2File:
    """Context-managed read/write view over a converted (MD20) .m2 file.

    Example::

        with M2File(path) as m2:
            if m2.global_flags & FLAG_USE_TEXTURE_COMBINER_COMBOS:
                ...
    """

    def __init__(self, path: str, mode: str = 'rb+'):
        self.path = path
        self._mode = mode
        self._fh: BinaryIO | None = None

    def __enter__(self) -> 'M2File':
        self._fh = open(self.path, self._mode)
        return self

    def __exit__(self, exc_type, exc_val, exc_tb) -> None:
        if self._fh is not None:
            self._fh.close()
            self._fh = None

    @property
    def fh(self) -> BinaryIO:
        if self._fh is None:
            raise RuntimeError('M2File must be used as a context manager')
        return self._fh

    # -- header helpers -------------------------------------------------

    @property
    def magic(self) -> bytes:
        return Binary.read_bytes(self.fh, M2Offsets.mdMagic, length=4)

    @property
    def is_converted(self) -> bool:
        """True once the model carries the WotLK MD20 magic."""
        return self.magic == MD20_MAGIC

    def read_field(self, offset: int, length: int = 4) -> int:
        return Binary.get_int_from_bytes(self.fh, int(offset), length=length)

    def write_field(self, offset: int, value: int, length: int = 4) -> None:
        Binary.set_int_to_bytes(self.fh, int(offset), value, length=length)

    @property
    def global_flags(self) -> int:
        return self.read_field(M2Offsets.globalFlags)

    @property
    def n_views(self) -> int:
        # Canonical num_skin_profiles location per the MD20 spec (0x44).
        return self.read_field(M2Offsets.nViews)

    @property
    def n_name(self) -> int:
        return self.read_field(M2Offsets.nName)

    @property
    def n_particle_emitters(self) -> int:
        return self.read_field(M2Offsets.nParticleEmitters)

    @property
    def n_ribbon_emitters(self) -> int:
        return self.read_field(M2Offsets.nRibbonEmitters)

    # -- array helpers --------------------------------------------------

    def read_array(self, n_offset: int, ofs_offset: int, stride: int) -> bytes:
        """Read a header-referenced array (``n`` count + ``ofs`` pointer) as raw bytes."""
        count = self.read_field(n_offset)
        ofs = self.read_field(ofs_offset)
        return Binary.read_bytes(self.fh, ofs, length=count * stride)

    def append_array(self, payload: bytes) -> int:
        """Append ``payload`` at the (16-byte aligned) end of the file and return its offset."""
        Binary.write_zeros(self.fh)
        offset = Binary.write_to_end(self.fh, payload)
        Binary.write_zeros(self.fh)
        return offset


class SkinFile:
    """Read-only view over a WotLK file-based .skin, exposing its render batches."""

    def __init__(self, path: str):
        self.path = path
        with open(path, 'rb') as fh:
            self._data = fh.read()

    @property
    def magic(self) -> bytes:
        return self._data[SkinOffsets.magic:SkinOffsets.magic + 4]

    def _u32(self, offset: int) -> int:
        return struct.unpack_from('<I', self._data, offset)[0]

    def _u16(self, base: int, field: int) -> int:
        return struct.unpack_from('<H', self._data, base + field)[0]

    @property
    def n_texture_units(self) -> int:
        return self._u32(SkinOffsets.nTextureUnits)

    @property
    def ofs_texture_units(self) -> int:
        return self._u32(SkinOffsets.ofsTextureUnits)

    @property
    def n_submeshes(self) -> int:
        return self._u32(SkinOffsets.nSubmeshes)

    def iter_batches(self) -> Iterator[TextureBatch]:
        """Yield every decoded render batch (texture unit) in file order."""
        base = self.ofs_texture_units
        stride = int(SkinLengths.textureUnit)
        for i in range(self.n_texture_units):
            rec = base + i * stride
            yield TextureBatch(
                flags=self._u16(rec, SkinBatchOffsets.flags),
                shader_id=self._u16(rec, SkinBatchOffsets.shaderId),
                skin_section_index=self._u16(rec, SkinBatchOffsets.skinSectionIndex),
                color_index=self._u16(rec, SkinBatchOffsets.colorIndex),
                material_index=self._u16(rec, SkinBatchOffsets.materialIndex),
                texture_count=self._u16(rec, SkinBatchOffsets.textureCount),
                texture_combo_index=self._u16(rec, SkinBatchOffsets.textureComboIndex),
            )

    def max_combo_slot(self) -> int:
        """Highest textureCombinerCombos slot referenced across all batches (-1 if none)."""
        slots = [batch.max_combo_slot for batch in self.iter_batches()]
        return max(slots) if slots else -1
