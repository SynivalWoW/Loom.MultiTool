import json
import struct

import pytest

from tests._fixtures import make_md20_textures, make_md21_txid
from texture_linker import _read_texture_entries, manifest_texture_map, read_txid_fileids, wire_textures


def test_read_txid_fileids(tmp_path):
    path = tmp_path / 'm.m2'
    path.write_bytes(make_md21_txid([111, 0, 222]))
    assert read_txid_fileids(str(path)) == [111, 0, 222]


def test_read_txid_skips_other_chunks(tmp_path):
    # an SFID chunk precedes TXID; the scanner must walk past it
    body = b'\x00' * 8
    out = bytearray(b'MD21' + struct.pack('<I', len(body)) + body)
    out += b'SFID' + struct.pack('<I', 4) + struct.pack('<I', 999)
    out += b'TXID' + struct.pack('<I', 8) + struct.pack('<II', 5, 6)
    path = tmp_path / 'm.m2'
    path.write_bytes(bytes(out))
    assert read_txid_fileids(str(path)) == [5, 6]


def test_read_txid_non_md21_or_missing(tmp_path):
    plain = tmp_path / 'a.m2'
    plain.write_bytes(b'MD20' + b'\x00' * 60)
    assert read_txid_fileids(str(plain)) == []
    no_txid = tmp_path / 'b.m2'
    no_txid.write_bytes(b'MD21' + struct.pack('<I', 4) + b'\x00\x00\x00\x00')  # MD21 but no TXID chunk
    assert read_txid_fileids(str(no_txid)) == []


def test_manifest_texture_map(tmp_path):
    path = tmp_path / 'x.manifest.json'
    path.write_text(
        json.dumps({'textures': [{'fileDataID': 111, 'file': '..\\creature\\x\\body.blp'}, {'fileDataID': 0, 'file': 'skip'}]})
    )
    assert manifest_texture_map(str(path)) == {111: 'body.blp'}


def test_wire_textures_embeds_hardcoded_and_reports_variations(tmp_path):
    # slots: [type0 fdid111 hard-coded] [type11 fdid0 replaceable] [type0 fdid222 hard-coded]
    m2 = tmp_path / 'model.m2'
    m2.write_bytes(make_md20_textures([0, 11, 0]))

    result = wire_textures(str(m2), [111, 0, 222], {111: 'starfield.blp', 222: 'fx.blp'}, 'Creature\\druidflightform')

    assert result['texture_count'] == 3
    assert result['embedded'] == {
        0: 'Creature\\druidflightform\\starfield.blp',
        2: 'Creature\\druidflightform\\fx.blp',
    }
    assert result['texture_variations'] == {0: None}  # type 11 -> CreatureDisplayInfo.TextureVariation[0]

    data = m2.read_bytes()
    entries = _read_texture_entries(data)

    def name(entry):
        return data[entry['nofs']:entry['nofs'] + entry['nlen']].split(b'\x00')[0].decode()

    assert name(entries[0]) == 'Creature\\druidflightform\\starfield.blp'
    assert name(entries[2]) == 'Creature\\druidflightform\\fx.blp'
    assert entries[1]['nlen'] == 0  # replaceable slot is left empty for the DBC to fill


def test_wire_textures_without_subdir_prefix(tmp_path):
    m2 = tmp_path / 'model.m2'
    m2.write_bytes(make_md20_textures([0]))
    result = wire_textures(str(m2), [7], {7: 'plain.blp'}, '')
    assert result['embedded'] == {0: 'plain.blp'}


def test_wire_textures_rejects_non_md20(tmp_path):
    m2 = tmp_path / 'bad.m2'
    m2.write_bytes(b'MD21' + b'\x00' * 60)
    with pytest.raises(ValueError, match='not an MD20'):
        wire_textures(str(m2), [], {}, 'Creature\\x')
