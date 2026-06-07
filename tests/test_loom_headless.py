import json
import os

from loom_headless import run, resolve_mapping, build_parser
from tests._fixtures import make_m2, make_skin, write_file


def _build_model_dir(tmp_path, name='druidcatharanir'):
    model_dir = tmp_path / name
    model_dir.mkdir()
    write_file(str(model_dir / 'model.m2'), make_m2(global_flags=0x08, combiner_values=[1, 4]))
    write_file(str(model_dir / 'model00.skin'), make_skin(submesh_bone_count=70, batches=[(2, 2)]))
    return model_dir


def test_run_success(tmp_path, capsys):
    model_dir = _build_model_dir(tmp_path)
    code = run(['--headless', '--input', str(model_dir), '--fix-combiners', '--link-assets'])
    assert code == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload['status'] == 'ok'
    assert payload['combiner_array'] == [0, 1, 2, 3]


def test_run_missing_input(tmp_path, capsys):
    code = run(['--input', str(tmp_path / 'nope')])
    assert code == 1
    payload = json.loads(capsys.readouterr().out)
    assert payload['status'] == 'error'


def test_resolve_mapping_from_id_map(tmp_path):
    model_dir = _build_model_dir(tmp_path, name='druidcatharanir')
    repo_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    args = build_parser().parse_args(
        ['--input', str(model_dir), '--id-map', os.path.join(repo_root, 'Loom_ID_Map.json')]
    )
    mapping = resolve_mapping(args)
    assert mapping['internal_name'] == 'Windsaber_Cat_Form'


def test_resolve_mapping_fallback(tmp_path):
    model_dir = _build_model_dir(tmp_path, name='customfolder')
    args = build_parser().parse_args(['--input', str(model_dir), '--internal-name', 'CustomModel'])
    mapping = resolve_mapping(args)
    assert mapping['internal_name'] == 'CustomModel'
    assert mapping['target_folder'] == 'customfolder'
