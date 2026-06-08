import struct

import pytest

from loom_dbc_generator import (
    types_of,
    build_dbc_bytes,
    write_dbc,
    parse_dbc,
    append_rows_to_dbc,
    append_rows_to_dbc_file,
    generate_creature_display_info,
    creature_display_info_row,
    generate_creature_model_data,
    generate_display_chain,
)


def _read_string(parsed, offset):
    block = parsed['string_block']
    return block[offset:block.index(b'\x00', offset)].decode('utf-8')


def test_append_rows_to_dbc_preserves_existing_and_adds_new():
    field_types = [int, str]
    base = build_dbc_bytes(field_types, [[1, 'alpha'], [2, 'beta']])
    merged = append_rows_to_dbc(base, field_types, [[3, 'gamma'], [4, 'alpha']])

    parsed = parse_dbc(merged)
    assert parsed['record_count'] == 4
    rs = parsed['record_size']
    records = parsed['records']
    # existing rows keep their original string offsets (block only grew at the end)
    ids = [struct.unpack_from('<i', records, i * rs)[0] for i in range(4)]
    assert ids == [1, 2, 3, 4]
    names = [_read_string(parsed, struct.unpack_from('<I', records, i * rs + 4)[0]) for i in range(4)]
    assert names == ['alpha', 'beta', 'gamma', 'alpha']


def test_append_rows_to_dbc_rejects_field_count_mismatch():
    base = build_dbc_bytes([int, str], [[1, 'x']])
    with pytest.raises(ValueError, match='field-count mismatch'):
        append_rows_to_dbc(base, [int, int, int], [[1, 2, 3]])


def test_append_rows_to_dbc_rejects_bad_magic():
    with pytest.raises(ValueError, match='invalid DBC magic'):
        append_rows_to_dbc(b'XXXX' + b'\x00' * 16, [int], [[1]])


def test_append_rows_to_dbc_file_roundtrip(tmp_path):
    field_types = [int, str]
    path = tmp_path / 'x.dbc'
    write_dbc(str(path), field_types, [[1, 'a']])
    total = append_rows_to_dbc_file(str(path), field_types, [[2, 'b'], [3, 'c']])
    assert total == 3
    assert parse_dbc(path.read_bytes())['record_count'] == 3
from dbc_records.creature_display_info import CreatureDisplayInfoRecord


def test_types_of_creature_display_info():
    types = types_of(CreatureDisplayInfoRecord)
    assert len(types) == 16
    assert types[0] is int
    assert types[4] is float
    assert types[6] is str


def test_build_and_parse_roundtrip():
    field_types = [int, float, str]
    data = build_dbc_bytes(field_types, [[42, 1.5, 'hello'], [7, 0.0, 'hello']])

    parsed = parse_dbc(data)
    assert parsed['magic'] == 'WDBC'
    assert parsed['record_count'] == 2
    assert parsed['field_count'] == 3
    assert parsed['record_size'] == 12

    # first record: int 42, float 1.5, string offset -> 'hello'
    rec0 = parsed['records'][:12]
    assert struct.unpack('<i', rec0[0:4])[0] == 42
    assert struct.unpack('<f', rec0[4:8])[0] == 1.5
    str_offset = struct.unpack('<I', rec0[8:12])[0]
    block = parsed['string_block']
    end = block.index(b'\x00', str_offset)
    assert block[str_offset:end] == b'hello'

    # second record reuses the interned 'hello' offset
    rec1 = parsed['records'][12:24]
    assert struct.unpack('<I', rec1[8:12])[0] == str_offset


def test_build_dbc_rejects_bad_row_length():
    with pytest.raises(ValueError):
        build_dbc_bytes([int, int], [[1]])


def test_build_dbc_rejects_unknown_type():
    with pytest.raises(TypeError):
        build_dbc_bytes([bytes], [[b'x']])


def test_generate_creature_display_info(tmp_path):
    mapping = {
        'internal_name': 'WindsaberCat',
        'texture_slots': {'body': 'cat_body', 'eyes': 'cat_eyes'},
        'requirements': {'emitter_fix': True},
    }
    out = str(tmp_path / 'cdi.dbc')
    size = generate_creature_display_info(out, mapping, display_id=80040)
    assert size > 0

    with open(out, 'rb') as handle:
        parsed = parse_dbc(handle.read())
    assert parsed['magic'] == 'WDBC'
    assert parsed['record_count'] == 1
    assert parsed['field_count'] == 16
    # first field is the display id
    assert struct.unpack('<i', parsed['records'][0:4])[0] == 80040


def test_creature_display_info_row_defaults():
    row = creature_display_info_row({}, 5)
    assert len(row) == 16
    assert row[0] == 5
    assert row[13] == 0  # emitter_fix absent -> particles flag 0


def test_generate_creature_model_data(tmp_path):
    out = str(tmp_path / 'cmd.dbc')
    size = generate_creature_model_data(out, 5000, 'Creature\\druidcat2\\cat.m2', {'scale': 1.0})
    assert size > 0

    parsed = parse_dbc(open(out, 'rb').read())
    assert parsed['field_count'] == 28  # verified against WDBX WotLK 12340
    assert parsed['record_count'] == 1
    assert struct.unpack('<i', parsed['records'][0:4])[0] == 5000  # ID
    assert b'Creature\\druidcat2\\cat.m2' in parsed['string_block']  # ModelName path interned


def test_generate_display_chain_wires_modelid(tmp_path):
    mapping = {'internal_name': 'WindsaberCat', 'target_folder': 'druidcat', 'entry': 'cat.m2'}
    chain = generate_display_chain(str(tmp_path), mapping, 80042, model_id=80042)

    assert (tmp_path / 'WindsaberCat_CreatureModelData.dbc').exists()
    assert (tmp_path / 'WindsaberCat_CreatureDisplayInfo.dbc').exists()
    assert chain['model_path'] == 'Creature\\druidcat\\cat.m2'

    cdi = parse_dbc(open(tmp_path / 'WindsaberCat_CreatureDisplayInfo.dbc', 'rb').read())
    cmd = parse_dbc(open(tmp_path / 'WindsaberCat_CreatureModelData.dbc', 'rb').read())
    # CreatureDisplayInfo.ModelID (col 1) == CreatureModelData.ID (col 0) == model_id
    assert struct.unpack('<i', cdi['records'][4:8])[0] == 80042
    assert struct.unpack('<i', cmd['records'][0:4])[0] == 80042


def test_generate_display_chain_derives_model_path(tmp_path):
    chain = generate_display_chain(str(tmp_path), {'internal_name': 'Cat'}, 7)
    assert chain['model_path'] == 'Creature\\Cat.m2'  # no target_folder/entry -> derived from internal name
    assert chain['model_id'] == 7  # defaults to display_id
