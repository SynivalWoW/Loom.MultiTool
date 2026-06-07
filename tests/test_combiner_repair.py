import struct

from combiner_repair import find_max_combo_index, repair_combiner
from core_parser import M2File, SkinFile, FLAG_USE_TEXTURE_COMBINER_COMBOS
from utils.offsets import M2Offsets
from tests._fixtures import make_m2, make_skin, write_file


def _read_combiner(path):
    with M2File(path) as m2:
        n = m2.read_field(M2Offsets.nTextureCombiner)
        raw = m2.read_array(M2Offsets.nTextureCombiner, M2Offsets.ofsTextureCombiner, stride=2)
        flags = m2.global_flags
    return n, list(struct.unpack('<%dH' % n, raw)), flags


def test_find_max_combo_index(tmp_path):
    skin = write_file(str(tmp_path / 'm00.skin'), make_skin(batches=[(0, 1), (2, 2)]))
    assert find_max_combo_index(SkinFile(skin)) == 3


def test_repair_rebuilds_truncated_stub(tmp_path):
    # flag set but a truncated [1, 4] stub while a batch needs slot 3 -> OOB risk.
    m2 = write_file(str(tmp_path / 'm.m2'), make_m2(global_flags=0x08, combiner_values=[1, 4]))
    skin = write_file(str(tmp_path / 'm00.skin'), make_skin(batches=[(2, 2)]))

    result = repair_combiner(m2, skin)

    assert result['action'] == 'repaired'
    assert result['combiner_array'] == [0, 1, 2, 3]
    n, values, flags = _read_combiner(m2)
    assert n == 4
    assert values == [0, 1, 2, 3]
    assert flags & FLAG_USE_TEXTURE_COMBINER_COMBOS


def test_repair_sets_missing_flag(tmp_path):
    # flag NOT set, but batches reference combos -> must add the flag and the array.
    m2 = write_file(str(tmp_path / 'm.m2'), make_m2(global_flags=0x00))
    skin = write_file(str(tmp_path / 'm00.skin'), make_skin(batches=[(0, 2)]))

    result = repair_combiner(m2, skin)

    assert result['action'] == 'repaired'
    _, values, flags = _read_combiner(m2)
    assert values == [0, 1]
    assert flags & FLAG_USE_TEXTURE_COMBINER_COMBOS


def test_repair_skips_when_already_large_enough(tmp_path):
    m2 = write_file(str(tmp_path / 'm.m2'), make_m2(global_flags=0x08, combiner_values=[0, 1, 2, 3, 4, 5, 6, 7]))
    skin = write_file(str(tmp_path / 'm00.skin'), make_skin(batches=[(2, 2)]))  # needs slot 3 only

    result = repair_combiner(m2, skin)

    assert result['action'] == 'skipped'
    assert result['combiner_len'] == 8
    assert result['combiner_array'] == list(range(8))


def test_repair_force_without_skin(tmp_path):
    m2 = write_file(str(tmp_path / 'm.m2'), make_m2(global_flags=0x00))
    result = repair_combiner(m2, None, force=True)
    assert result['action'] == 'repaired'
    assert result['combiner_len'] == 1
    assert result['combiner_array'] == [0]
