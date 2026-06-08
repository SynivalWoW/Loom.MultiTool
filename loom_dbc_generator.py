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
import os
import struct
import sys
from typing import Sequence

import dbc_definitions

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


def append_rows_to_dbc(existing: bytes, field_types: Sequence[type], new_rows: Sequence[Sequence]) -> bytes:
    """Append ``new_rows`` to an existing WDBC, preserving every existing record and string.

    The string block only grows at the end, so existing string offsets stay valid; new strings are
    interned into the appended region (offset 0 remains the empty string). This is how a retroport's
    display rows are merged into the live server CreatureDisplayInfo.dbc / CreatureModelData.dbc.
    """
    magic, record_count, field_count, record_size, string_block_size = _HEADER_STRUCT.unpack_from(existing, 0)
    if magic != WDBC_MAGIC:
        raise ValueError(f'invalid DBC magic: {magic!r}')
    if field_count != len(field_types):
        raise ValueError(f'field-count mismatch: file has {field_count}, definition expects {len(field_types)}')

    start = _HEADER_STRUCT.size
    records_end = start + record_count * record_size
    existing_records = existing[start:records_end]
    string_block = bytearray(existing[records_end:records_end + string_block_size])
    string_offsets: dict[str, int] = {'': 0}

    def intern(text: str) -> int:
        if text in string_offsets:
            return string_offsets[text]
        offset = len(string_block)
        string_block.extend(text.encode('utf-8') + b'\x00')
        string_offsets[text] = offset
        return offset

    new_record_bytes = bytearray()
    for row in new_rows:
        if len(row) != field_count:
            raise ValueError(f'row has {len(row)} values, expected {field_count}')
        for ftype, value in zip(field_types, row):
            if ftype is int:
                new_record_bytes += struct.pack('<i', int(value))
            elif ftype is float:
                new_record_bytes += struct.pack('<f', float(value))
            elif ftype is str:
                new_record_bytes += struct.pack('<I', intern(str(value)))
            else:
                raise TypeError(f'unsupported DBC field type: {ftype!r}')

    header = _HEADER_STRUCT.pack(WDBC_MAGIC, record_count + len(new_rows), field_count, record_size, len(string_block))
    return bytes(header) + existing_records + bytes(new_record_bytes) + bytes(string_block)


def append_rows_to_dbc_file(path: str, field_types: Sequence[type], new_rows: Sequence[Sequence]) -> int:
    """Append rows to a WDBC file in place; returns the new total record count."""
    with open(path, 'rb') as handle:
        merged = append_rows_to_dbc(handle.read(), field_types, new_rows)
    with open(path, 'wb') as handle:
        handle.write(merged)
    return _HEADER_STRUCT.unpack_from(merged, 0)[1]


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


def creature_display_info_row(mapping: dict, display_id: int, model_id: int | None = None) -> list:
    """Build a CreatureDisplayInfo row (in field order) from a Loom_ID_Map entry + display id.

    Column order/types verified against WDBX Editor's authoritative ``WotLK 3.3.5 (12340)``
    definition (16 columns). ``model_id`` is the CreatureModelData id this display points at.
    """
    textures = mapping.get('texture_slots', {})
    internal_name = mapping.get('internal_name', '')
    return [
        display_id,                                          # id (ID)
        model_id if model_id is not None else mapping.get('model', 0),  # model (ModelID -> CreatureModelData.ID)
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


def generate_creature_display_info(path: str, mapping: dict, display_id: int, model_id: int | None = None) -> int:
    """Write a single-row CreatureDisplayInfo.dbc for one retroported model."""
    field_types = dbc_definitions.field_types('CreatureDisplayInfo')
    row = creature_display_info_row(mapping, display_id, model_id)
    return write_dbc(path, field_types, [row])


def creature_model_data_row(model_id: int, model_path: str, mapping: dict) -> list:
    """Build a CreatureModelData row (28 columns, verified against WDBX WotLK 12340)."""
    return [
        model_id,                                    # id (ID)
        0,                                           # flags
        model_path,                                  # model_path (ModelName, e.g. Creature\\folder\\name.m2)
        0,                                           # size_class
        float(mapping.get('scale', 1.0)),            # model_scale
        0,                                           # blood_level (BloodID)
        0,                                           # footprint (FootprintTextureID)
        0.0, 0.0, 0.0,                               # footprint texture length / width / particle scale
        0,                                           # foley_material_id
        0, 0,                                        # footstep / deaththud shake size
        0,                                           # sound_data (SoundID)
        float(mapping.get('collision_width', 0.0)),  # collision_width
        float(mapping.get('collision_height', 0.0)),  # collision_height
        0.0,                                         # mount_height
        0.0, 0.0, 0.0,                               # geo_box min x/y/z
        0.0, 0.0, 0.0,                               # geo_box max x/y/z
        1.0, 1.0,                                    # world / attached effect scale
        0.0, 0.0, 0.0,                               # missile collision radius / push / raise
    ]


def generate_creature_model_data(path: str, model_id: int, model_path: str, mapping: dict) -> int:
    """Write a single-row CreatureModelData.dbc pointing at the model file path."""
    field_types = dbc_definitions.field_types('CreatureModelData')
    row = creature_model_data_row(model_id, model_path, mapping)
    return write_dbc(path, field_types, [row])


def generate_display_chain(out_dir: str, mapping: dict, display_id: int, model_id: int | None = None, model_path: str | None = None) -> dict:
    """Write the full custom-display DBC chain: CreatureModelData + CreatureDisplayInfo (wired).

    CreatureDisplayInfo.ModelID -> CreatureModelData.ID -> ModelName (the .m2 path). This is the
    chain that ``player_shapeshift_model.DisplayID`` ultimately resolves to in the client.
    """
    model_id = model_id if model_id is not None else display_id
    internal = mapping.get('internal_name', 'model')
    if model_path is None:
        target = mapping.get('target_folder', '')
        entry = mapping.get('entry') or f'{internal}.m2'
        model_path = f'Creature\\{target}\\{entry}' if target else f'Creature\\{entry}'

    cmd_file = os.path.join(out_dir, f'{internal}_CreatureModelData.dbc')
    cdi_file = os.path.join(out_dir, f'{internal}_CreatureDisplayInfo.dbc')
    generate_creature_model_data(cmd_file, model_id, model_path, mapping)
    generate_creature_display_info(cdi_file, mapping, display_id, model_id=model_id)

    return {
        'creature_model_data': os.path.basename(cmd_file),
        'creature_display_info': os.path.basename(cdi_file),
        'model_id': model_id,
        'display_id': display_id,
        'model_path': model_path,
    }


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
