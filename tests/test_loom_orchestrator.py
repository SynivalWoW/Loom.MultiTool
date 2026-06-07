import os

from loom_orchestrator import run_orchestration, find_entry_m2, find_entry_skin
from tests._fixtures import make_m2, make_skin, write_file


def _build_model_dir(tmp_path):
    write_file(str(tmp_path / 'model.m2'), make_m2(global_flags=0x08, combiner_values=[1, 4], n_name=0, n_views=1))
    write_file(str(tmp_path / 'model00.skin'), make_skin(submesh_bone_count=70, batches=[(2, 2)]))


def test_run_orchestration_full(tmp_path):
    _build_model_dir(tmp_path)
    mapping = {'internal_name': 'WindsaberCat', 'target_folder': 'druidcat', 'retail_id': 999}

    result = run_orchestration(str(tmp_path), mapping)

    assert result['status'] == 'ok'
    assert result['entry'] == 'model.m2'
    assert result['nViews'] == 4
    assert result['combiner_array'] == [0, 1, 2, 3]
    assert result['combiner_action'] == 'repaired'
    assert 'emitter_safe' in result
    assert result['display_id'] == 999


def test_run_orchestration_no_m2(tmp_path):
    result = run_orchestration(str(tmp_path), {'internal_name': 'x'})
    assert result['status'] == 'error'
    assert 'no .m2' in result['error']


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
