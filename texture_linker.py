"""texture_linker.py — restore MD20 texture filenames from the Legion TXID chunk + wow.export manifest.

Retail (MD21) models reference textures by FileDataID (the ``TXID`` chunk) and leave the MD20 inline
texture-filename strings empty. The MD21->MD20 converter drops ``TXID``, so the downgraded model has
no texture paths and renders untextured. This module re-wires them so retroports are actually
textured:

  * For every texture slot whose ``TXID`` FileDataID != 0 (a *hard-coded* texture), the manifest
    supplies the ``.blp`` basename; we embed ``<mpq_subdir>\\<basename>`` into the M2 texture string.
  * Slots with FileDataID 0 are *replaceable* monster-skin slots (M2 texture type 11/12/13) that the
    client fills at runtime from ``CreatureDisplayInfo.TextureVariation[type-11]`` (e.g. a per-race
    druid body skin). We report those indices so the DBC layer can populate texture1/2/3.

Pure-stdlib (``struct``/``json``/``os``); imports no GUI/Windows modules.
"""

from __future__ import annotations

import json
import struct

from utils.offsets import M2Lengths, M2Offsets

MD20_MAGIC = b'MD20'
MD21_MAGIC = b'MD21'

# M2 texture type -> CreatureDisplayInfo.TextureVariation index (texture1/2/3 in the DBC).
REPLACEABLE_TYPES = {11: 0, 12: 1, 13: 2}


def read_txid_fileids(md21_path: str) -> list[int]:
    """Return the texture FileDataIDs from a Legion MD21's TXID chunk (one per texture slot).

    Empty list when the file is not MD21 or has no TXID chunk (already-MD20 / non-Legion models).
    """
    with open(md21_path, 'rb') as handle:
        data = handle.read()
    if data[:4] != MD21_MAGIC:
        return []
    md20_size = struct.unpack_from('<I', data, 4)[0]
    pos = 8 + md20_size
    while pos + 8 <= len(data):
        chunk_id = data[pos:pos + 4]
        size = struct.unpack_from('<I', data, pos + 4)[0]
        if chunk_id == b'TXID':
            body = data[pos + 8:pos + 8 + size]
            return [struct.unpack_from('<I', body, i * 4)[0] for i in range(size // 4)]
        pos += 8 + size
    return []


def manifest_texture_map(manifest_path: str) -> dict[int, str]:
    """Map texture FileDataID -> ``.blp`` basename from a wow.export ``*.manifest.json``."""
    with open(manifest_path) as handle:
        manifest = json.load(handle)
    mapping: dict[int, str] = {}
    for texture in manifest.get('textures', []):
        fdid = texture.get('fileDataID')
        path = texture.get('file', '')
        if fdid:
            mapping[fdid] = path.replace('/', '\\').rsplit('\\', 1)[-1]
    return mapping


def _read_texture_entries(data: bytes) -> list[dict]:
    count = struct.unpack_from('<I', data, M2Offsets.nTextures)[0]
    offset = struct.unpack_from('<I', data, M2Offsets.ofsTextures)[0]
    entries = []
    for i in range(count):
        base = offset + i * M2Lengths.texture
        ttype, _flags, nlen, nofs = struct.unpack_from('<IIII', data, base)
        entries.append({'index': i, 'base': base, 'type': ttype, 'nlen': nlen, 'nofs': nofs})
    return entries


def wire_textures(m2_path: str, txid_fileids: list[int], manifest_map: dict[int, str], mpq_subdir: str) -> dict:
    """Embed hard-coded texture paths into an MD20 and report its replaceable TextureVariation slots.

    Hard-coded filenames are appended as a string block at end-of-file and the texture records'
    ``filename`` M2Array (count/offset) are re-pointed at them. Returns
    ``{'embedded': {slot: path}, 'texture_variations': {variation_index: None}, 'texture_count': n}``.
    """
    with open(m2_path, 'rb') as handle:
        data = bytearray(handle.read())
    if data[:4] != MD20_MAGIC:
        raise ValueError(f'not an MD20 model: {m2_path}')

    entries = _read_texture_entries(data)
    subdir = mpq_subdir.rstrip('\\')
    appended = bytearray()
    string_base = len(data)
    embedded: dict[int, str] = {}

    for entry in entries:
        slot = entry['index']
        fdid = txid_fileids[slot] if slot < len(txid_fileids) else 0
        if fdid and fdid in manifest_map:
            full = f'{subdir}\\{manifest_map[fdid]}' if subdir else manifest_map[fdid]
            raw = full.encode('ascii', 'replace') + b'\x00'
            offset = string_base + len(appended)
            appended += raw
            struct.pack_into('<II', data, entry['base'] + 8, len(raw), offset)  # nFilename, ofsFilename
            embedded[slot] = full

    variations: dict[int, None] = {}
    for entry in entries:
        if entry['type'] in REPLACEABLE_TYPES:
            variations[REPLACEABLE_TYPES[entry['type']]] = None

    data += appended
    with open(m2_path, 'wb') as handle:
        handle.write(data)

    return {'embedded': embedded, 'texture_variations': variations, 'texture_count': len(entries)}
