import struct

import pytest

from core_parser import M2File, SkinFile, TextureBatch, FLAG_USE_TEXTURE_COMBINER_COMBOS
from utils.binary import Binary
from utils.offsets import M2Offsets
from tests._fixtures import make_m2, make_skin, write_file


def test_m2file_header_reads(tmp_path):
    path = write_file(str(tmp_path / 'm.m2'), make_m2(global_flags=0x08, n_name=5, n_views=3, n_particle=2, n_ribbon=1))
    with M2File(path) as m2:
        assert m2.magic == b'MD20'
        assert m2.is_converted is True
        assert m2.global_flags & FLAG_USE_TEXTURE_COMBINER_COMBOS
        assert m2.n_name == 5
        assert m2.n_views == 3
        assert m2.n_particle_emitters == 2
        assert m2.n_ribbon_emitters == 1


def test_m2file_not_converted(tmp_path):
    data = bytearray(make_m2())
    data[0:4] = b'MD21'
    path = write_file(str(tmp_path / 'legion.m2'), bytes(data))
    with M2File(path) as m2:
        assert m2.is_converted is False


def test_m2file_requires_context(tmp_path):
    path = write_file(str(tmp_path / 'm.m2'), make_m2())
    m2 = M2File(path)
    with pytest.raises(RuntimeError):
        _ = m2.fh


def test_m2file_read_and_append_array(tmp_path):
    path = write_file(str(tmp_path / 'm.m2'), make_m2(combiner_values=[1, 4]))
    with M2File(path) as m2:
        raw = m2.read_array(M2Offsets.nTextureCombiner, M2Offsets.ofsTextureCombiner, stride=2)
        assert struct.unpack('<2H', raw) == (1, 4)

        offset = m2.append_array(struct.pack('<3H', 7, 8, 9))
        assert offset % 16 == 0

    with M2File(path) as m2:
        appended = struct.unpack('<3H', Binary.read_bytes(m2.fh, offset, 6))
        assert appended == (7, 8, 9)


def test_skinfile_batches(tmp_path):
    path = write_file(str(tmp_path / 'm00.skin'), make_skin(batches=[(0, 1), (2, 2)]))
    skin = SkinFile(path)
    assert skin.magic == b'SKIN'
    assert skin.n_texture_units == 2
    assert skin.n_submeshes == 1
    batches = list(skin.iter_batches())
    assert [b.texture_combo_index for b in batches] == [0, 2]
    # batch (2, 2) touches slots 2 and 3 -> highest slot is 3
    assert skin.max_combo_slot() == 3


def test_skinfile_no_batches(tmp_path):
    path = write_file(str(tmp_path / 'm00.skin'), make_skin(batches=[]))
    assert SkinFile(path).max_combo_slot() == -1


def test_m2file_is_md21(tmp_path):
    data = bytearray(make_m2())
    data[0:4] = b'MD21'
    path = write_file(str(tmp_path / 'legion.m2'), bytes(data))
    with M2File(path) as m2:
        assert m2.is_md21 is True
        assert m2.is_converted is False


def test_m2file_vertices_and_texture_filenames(tmp_path):
    path = write_file(str(tmp_path / 'm.m2'), make_m2(n_vertices=12345, textures=['Creature/Cat/CatBody.blp', 'Creature/Cat/CatEyes.blp']))
    with M2File(path) as m2:
        assert m2.n_vertices == 12345
        names = m2.read_texture_filenames()
        assert names == ['Creature/Cat/CatBody.blp', 'Creature/Cat/CatEyes.blp']


def test_texture_batch_zero_count_uses_one():
    batch = TextureBatch(0, 0, 0, 0, 0, texture_count=0, texture_combo_index=5)
    # with a zero count we still reserve one slot
    assert batch.max_combo_slot == 5
