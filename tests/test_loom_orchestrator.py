import json
import os

from loom_orchestrator import run_orchestration, find_entry_m2, find_entry_skin
from tests._fixtures import make_m2, make_md20_textures, make_md21_txid, make_skin, write_file


def _build_model_dir(tmp_path):
    write_file(str(tmp_path / 'model.m2'), make_m2(global_flags=0x08, combiner_values=[1, 4], n_name=0, n_views=1))
    write_file(str(tmp_path / 'model00.skin'), make_skin(submesh_bone_count=70, batches=[(2, 2)]))


def test_run_orchestration_full(tmp_path):
    _build_model_dir(tmp_path)
    mapping = {'internal_name': 'WindsaberCat', 'target_folder': 'druidcat', 'retail_id': 999}

    result = run_orchestration(str(tmp_path), mapping)

    assert result['status'] == 'ok'
    assert result['entry'] == 'model.m2'
    assert result['nViews'] == 1  # nViews == count of .skin files (one present)
    assert result['skin_count'] == 1
    assert result['combiner_array'] == [0, 1, 2, 3]
    assert result['combiner_action'] == 'repaired'
    assert 'emitter_safe' in result
    assert result['display_id'] == 999


def test_run_orchestration_no_m2(tmp_path):
    result = run_orchestration(str(tmp_path), {'internal_name': 'x'})
    assert result['status'] == 'error'
    assert 'no .m2' in result['error']


def test_run_orchestration_rejects_md21(tmp_path):
    data = bytearray(make_m2())
    data[0:4] = b'MD21'  # still a Legion chunked file
    write_file(str(tmp_path / 'model.m2'), bytes(data))
    result = run_orchestration(str(tmp_path), {'internal_name': 'x'})
    assert result['status'] == 'error'
    assert result['is_md21'] is True
    assert 'MD21' in result['error']


def test_run_orchestration_reports_validation(tmp_path):
    # over-heavy model + a referenced-but-missing texture => not valid
    write_file(
        str(tmp_path / 'model.m2'),
        make_m2(global_flags=0x08, combiner_values=[1, 4], n_vertices=30000, textures=['Path\\CatBody.blp']),
    )
    write_file(str(tmp_path / 'model00.skin'), make_skin(submesh_bone_count=70, batches=[(2, 2)]))

    result = run_orchestration(str(tmp_path), {'internal_name': 'Cat'})
    assert result['status'] == 'ok'
    assert result['is_md21'] is False
    assert result['skin_count'] == 1
    assert result['nViews'] == 1  # nViews == skin count (one .skin file)
    assert result['vertex_count'] == 30000
    assert result['vertex_safe'] is False
    assert result['missing_textures'] == ['CatBody.blp']
    assert result['valid'] is False


def test_run_orchestration_convert_then_repair(tmp_path, monkeypatch):
    # a still-MD21 model + convert=True with a fake converter that flips the magic to MD20.
    data = bytearray(make_m2(global_flags=0x08, combiner_values=[1, 4]))
    data[0:4] = b'MD21'
    write_file(str(tmp_path / 'model.m2'), bytes(data))
    write_file(str(tmp_path / 'model00.skin'), make_skin(submesh_bone_count=70, batches=[(2, 2)]))

    def fake_convert(m2_path, *args, **kwargs):
        buf = bytearray(open(m2_path, 'rb').read())
        buf[0:4] = b'MD20'
        open(m2_path, 'wb').write(buf)
        return {'converted': True, 'm2_path': m2_path, 'magic': 'MD20', 'returncode': 0}

    monkeypatch.setattr('loom_orchestrator.loom_converter.convert_m2', fake_convert)

    result = run_orchestration(str(tmp_path), {'internal_name': 'Cat'}, convert=True)
    assert result['status'] == 'ok'
    assert result['converted'] is True
    assert result['is_md21'] is False
    assert result['combiner_array'] == [0, 1, 2, 3]


def test_run_orchestration_heavy_but_loadable_is_valid(tmp_path):
    # 30k verts is over the conservative budget but under the 16-bit limit: loadable -> still valid.
    write_file(str(tmp_path / 'model.m2'), make_m2(global_flags=0x08, combiner_values=[1, 4], n_vertices=30000))
    write_file(str(tmp_path / 'model00.skin'), make_skin(submesh_bone_count=70, batches=[(2, 2)]))

    result = run_orchestration(str(tmp_path), {'internal_name': 'Cat'})
    assert result['vertex_safe'] is False
    assert result['vertex_loadable'] is True
    assert result['vertex_status'] == 'caution'
    assert result['valid'] is True  # no longer wrongly rejected


def test_run_orchestration_vertex_overflow_is_invalid(tmp_path):
    write_file(str(tmp_path / 'model.m2'), make_m2(global_flags=0x08, combiner_values=[1, 4], n_vertices=70000))
    write_file(str(tmp_path / 'model00.skin'), make_skin(submesh_bone_count=70, batches=[(2, 2)]))

    result = run_orchestration(str(tmp_path), {'internal_name': 'Cat'})
    assert result['vertex_status'] == 'overflow'
    assert result['valid'] is False


def test_run_orchestration_wires_textures_from_txid(tmp_path, monkeypatch):
    # Source MD21 carries a TXID chunk: slot0 hard-coded (fdid 111), slot1 replaceable (fdid 0).
    write_file(str(tmp_path / 'model.m2'), make_md21_txid([111, 0]))
    write_file(str(tmp_path / 'model00.skin'), make_skin(submesh_bone_count=70, batches=[(0, 1)]))
    (tmp_path / 'model.manifest.json').write_text(json.dumps({'textures': [{'fileDataID': 111, 'file': '..\\x\\body.blp'}]}))

    def fake_convert(m2_path, *args, **kwargs):
        # the real converter emits a flat MD20 with blank texture strings (type0 + type11 here)
        with open(m2_path, 'wb') as handle:
            handle.write(make_md20_textures([0, 11]))
        return {'converted': True, 'm2_path': m2_path, 'magic': 'MD20', 'returncode': 0}

    monkeypatch.setattr('loom_orchestrator.loom_converter.convert_m2', fake_convert)

    result = run_orchestration(str(tmp_path), {'internal_name': 'druidx'}, convert=True, fix_combiners=False)

    assert result['textures_wired'] == 1                 # the hard-coded slot got its filename back
    assert result['texture_variation_slots'] == [0]      # type 11 -> CreatureDisplayInfo.TextureVariation[0]
    assert b'Creature\\druidx\\body.blp' in open(str(tmp_path / 'model.m2'), 'rb').read()


def test_run_orchestration_generates_dbc(tmp_path):
    _build_model_dir(tmp_path)
    result = run_orchestration(str(tmp_path), {'internal_name': 'WindsaberCat'}, gen_dbc=True, display_id=80040)
    assert 'dbc' in result
    assert (tmp_path / result['dbc']).exists()


def test_find_helpers(tmp_path):
    assert find_entry_m2(str(tmp_path)) is None
    assert find_entry_skin(str(tmp_path)) is None
    _build_model_dir(tmp_path)
    assert os.path.basename(find_entry_m2(str(tmp_path))) == 'model.m2'
    assert os.path.basename(find_entry_skin(str(tmp_path))) == 'model00.skin'
