import struct

from asset_linker import (
    get_nviews_from_skin,
    patch_nviews,
    count_skin_profiles,
    set_nviews_to_skin_count,
    validate_vertices,
    check_missing_assets,
    link_skins,
    link_anims,
    fix_nname,
    evaluate_emitters,
)
from core_parser import M2File
from utils.offsets import M2Offsets
from tests._fixtures import make_m2, make_skin, write_file


def test_get_nviews_thresholds(tmp_path):
    cases = {70: 4, 60: 3, 30: 2, 10: 1}
    for bone_count, expected in cases.items():
        path = write_file(str(tmp_path / f's{bone_count}.skin'), make_skin(submesh_bone_count=bone_count))
        assert get_nviews_from_skin(path) == expected


def test_patch_nviews_raises_value(tmp_path):
    write_file(str(tmp_path / 'model00.skin'), make_skin(submesh_bone_count=70))
    m2 = write_file(str(tmp_path / 'model.m2'), make_m2(n_views=1))

    assert patch_nviews(m2, str(tmp_path)) == 4
    with M2File(m2) as model:
        assert model.n_views == 4


def test_patch_nviews_no_skins(tmp_path):
    m2 = write_file(str(tmp_path / 'model.m2'), make_m2())
    assert patch_nviews(m2, str(tmp_path)) == 0


def test_set_nviews_to_skin_count(tmp_path):
    # two skin files present, but the bone-count heuristic would say 4 -> the count (2) wins.
    write_file(str(tmp_path / 'model00.skin'), make_skin(submesh_bone_count=70))
    write_file(str(tmp_path / 'model01.skin'), make_skin(submesh_bone_count=70))
    m2 = write_file(str(tmp_path / 'model.m2'), make_m2(n_views=1))

    assert count_skin_profiles(str(tmp_path)) == 2
    assert set_nviews_to_skin_count(m2, str(tmp_path)) == 2
    with M2File(m2) as model:
        assert model.n_views == 2


def test_set_nviews_no_skins(tmp_path):
    m2 = write_file(str(tmp_path / 'model.m2'), make_m2(n_views=1))
    assert set_nviews_to_skin_count(m2, str(tmp_path)) == 0


def test_validate_vertices(tmp_path):
    safe = write_file(str(tmp_path / 'safe.m2'), make_m2(n_vertices=10000))
    assert validate_vertices(safe) == {'vertex_count': 10000, 'vertex_safe': True, 'max_vertices': 21845}

    heavy = write_file(str(tmp_path / 'heavy.m2'), make_m2(n_vertices=30000))
    assert validate_vertices(heavy)['vertex_safe'] is False


def test_check_missing_assets(tmp_path):
    m2 = write_file(str(tmp_path / 'model.m2'), make_m2(textures=['Path\\To\\CatBody.blp', 'Path\\To\\CatEyes.blp']))
    write_file(str(tmp_path / 'CatBody.blp'), b'BLP')  # present
    write_file(str(tmp_path / 'stand.anim'), b'\x00')

    report = check_missing_assets(m2, str(tmp_path))
    assert report['missing_textures'] == ['CatEyes.blp']  # CatBody present, CatEyes missing
    assert report['anim_count'] == 1


def test_link_skins_strips_lod(tmp_path):
    write_file(str(tmp_path / 'model00.skin'), make_skin())
    write_file(str(tmp_path / 'model_lod01.skin'), make_skin())

    result = link_skins(str(tmp_path))

    assert 'model01.skin' in result
    assert 'model_lod01.skin' not in result
    assert (tmp_path / 'model01.skin').exists()


def test_link_anims(tmp_path):
    write_file(str(tmp_path / 'a0001.anim'), b'\x00')
    write_file(str(tmp_path / 'a0000.anim'), b'\x00')
    assert link_anims(str(tmp_path)) == ['a0000.anim', 'a0001.anim']


def test_fix_nname_repairs_then_skips(tmp_path):
    m2 = write_file(str(tmp_path / 'model.m2'), make_m2(n_name=0))

    first = fix_nname(m2, 'WindsaberCat')
    assert first['action'] == 'repaired'
    assert first['n_name'] == len(b'WindsaberCat') + 1

    with M2File(m2) as model:
        assert model.n_name == first['n_name']
        ofs = model.read_field(M2Offsets.ofsName)
        from utils.binary import Binary
        assert Binary.read_bytes(model.fh, ofs, first['n_name']).rstrip(b'\x00') == b'WindsaberCat'

    second = fix_nname(m2, 'WindsaberCat')
    assert second['action'] == 'skipped'


def test_evaluate_emitters_report_and_strip(tmp_path):
    m2 = write_file(str(tmp_path / 'model.m2'), make_m2(n_particle=2, n_ribbon=1))

    report = evaluate_emitters(m2)
    assert report['particles'] == 2
    assert report['ribbons'] == 1
    assert report['emitter_safe'] is False
    assert report['stripped'] is False

    stripped = evaluate_emitters(m2, strip=True)
    assert stripped['stripped'] is True
    assert stripped['emitter_safe'] is True
    with M2File(m2) as model:
        assert model.n_particle_emitters == 0
        assert model.n_ribbon_emitters == 0


def test_evaluate_emitters_safe_when_none(tmp_path):
    m2 = write_file(str(tmp_path / 'model.m2'), make_m2())
    report = evaluate_emitters(m2)
    assert report['emitter_safe'] is True
