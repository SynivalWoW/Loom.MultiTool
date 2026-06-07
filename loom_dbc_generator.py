"""loom_dbc_generator.py — raw binary WDBC writer for retroported display records.

The existing ``csv_editor.py`` only round-trips DBC data through the ``dbcpy``/CSV layer; this
module emits genuine little-endian WDBC binaries (the format the 3.3.5a client / MPQ patch
loads). Field layout is taken from the dataclasses already defined under ``dbc_records/`` so
the column order stays the single source of truth.

WDBC layout::

    char  magic[4] = "WDBC"
    u32   record_count
    u32   field_count
    u32   record_size            (== field_count * 4)
    u32   string_block_size
    record_count * record_size   bytes of fixed-width records
    string_block_size            bytes (index 0 is the empty string)

Pure-stdlib (``struct``/``dataclasses``); imports no GUI/Windows modules.
"""

from __future__ import annotations

import dataclasses
import struct
import sys
from typing import Sequence

from dbc_records.creature_display_info import CreatureDisplayInfoRecord

WDBC_MAGIC = b'WDBC'
_HEADER_STRUCT = struct.Struct('<4sIIII')

_TYPE_NAMES = {'int': int, 'float': float, 'str': str}


def types_of(record_cls) -> list[type]:
    """Resolve a dataclass's field python-types (handles string annotations too)."""
    resolved: list[type] = []
    for field in dataclasses.fields(record_cls):
        ftype = field.type
        if isinstance(ftype, str):
            ftype = _TYPE_NAMES[ftype]
        resolved.append(ftype)
    return resolved


def build_dbc_bytes(field_types: Sequence[type], rows: Sequence[Sequence]) -> bytes:
    """Serialise ``rows`` into a complete WDBC byte string."""
    string_block = bytearray(b'\x00')  # offset 0 == empty string
    string_offsets: dict[str, int] = {'': 0}

    def intern(text: str) -> int:
        if text in string_offsets:
            return string_offsets[text]
        offset = len(string_block)
        string_block.extend(text.encode('utf-8') + b'\x00')
        string_offsets[text] = offset
        return offset

    field_count = len(field_types)
    record_bytes = bytearray()

    for row in rows:
        if len(row) != field_count:
            raise ValueError(f'row has {len(row)} values, expected {field_count}')
        for ftype, value in zip(field_types, row):
            if ftype is int:
                record_bytes += struct.pack('<i', int(value))
            elif ftype is float:
                record_bytes += struct.pack('<f', float(value))
            elif ftype is str:
                record_bytes += struct.pack('<I', intern(str(value)))
            else:
                raise TypeError(f'unsupported DBC field type: {ftype!r}')

    header = _HEADER_STRUCT.pack(
        WDBC_MAGIC, len(rows), field_count, field_count * 4, len(string_block),
    )
    return bytes(header + record_bytes + string_block)


def write_dbc(path: str, field_types: Sequence[type], rows: Sequence[Sequence]) -> int:
    """Write a WDBC file and return the number of bytes written."""
    data = build_dbc_bytes(field_types, rows)
    with open(path, 'wb') as handle:
        handle.write(data)
    return len(data)


def parse_dbc(data: bytes) -> dict:
    """Parse a WDBC byte string back into header + raw record/string sections (for validation)."""
    magic, record_count, field_count, record_size, string_block_size = _HEADER_STRUCT.unpack_from(data, 0)
    if magic != WDBC_MAGIC:
        raise ValueError(f'invalid DBC magic: {magic!r}')
    start = _HEADER_STRUCT.size
    records_end = start + record_count * record_size
    return {
        'magic': magic.decode('ascii'),
        'record_count': record_count,
        'field_count': field_count,
        'record_size': record_size,
        'string_block_size': string_block_size,
        'records': data[start:records_end],
        'string_block': data[records_end:records_end + string_block_size],
    }


def creature_display_info_row(mapping: dict, display_id: int) -> list:
    """Build a CreatureDisplayInfo row (in field order) from a Loom_ID_Map entry + display id."""
    textures = mapping.get('texture_slots', {})
    internal_name = mapping.get('internal_name', '')
    return [
        display_id,                              # id
        mapping.get('model', 0),                 # model (CreatureModelData id)
        mapping.get('sound', 0),                 # sound
        0,                                       # extra_display_information
        float(mapping.get('scale', 1.0)),        # scale
        255,                                     # opacity
        str(textures.get('body', internal_name)),  # texture1
        str(textures.get('eyes', '')),           # texture2
        '',                                      # texture3
        '',                                      # portrait_texturename
        0,                                       # blood_level
        0,                                       # blood
        0,                                       # npc_sounds
        int(bool(mapping.get('requirements', {}).get('emitter_fix', False))),  # particles
        0,                                       # creature_geoset_data
        0,                                       # object_effect_package_id
    ]


def generate_creature_display_info(path: str, mapping: dict, display_id: int) -> int:
    """Write a single-row CreatureDisplayInfo.dbc for one retroported model."""
    field_types = types_of(CreatureDisplayInfoRecord)
    row = creature_display_info_row(mapping, display_id)
    return write_dbc(path, field_types, [row])


def _main(argv: list[str]) -> int:  # pragma: no cover - thin CLI wrapper
    if len(argv) < 3:
        print('usage: python loom_dbc_generator.py <out.dbc> <display_id> [internal_name]')
        return 2
    out, display_id = argv[1], int(argv[2])
    mapping = {'internal_name': argv[3] if len(argv) > 3 else 'loom_model'}
    size = generate_creature_display_info(out, mapping, display_id)
    print(f'wrote {size} bytes -> {out}')
    return 0


if __name__ == '__main__':  # pragma: no cover
    raise SystemExit(_main(sys.argv))
