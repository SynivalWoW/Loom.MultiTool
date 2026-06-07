import json
import os

import pytest

from loom_id_map import load_id_map, find_mapping

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def test_load_repo_id_map():
    id_map = load_id_map(os.path.join(REPO_ROOT, 'Loom_ID_Map.json'))
    assert id_map['version'] == '1.0.0'
    assert len(id_map['mappings']) == 1


def test_find_mapping_by_name_and_folder():
    id_map = load_id_map(os.path.join(REPO_ROOT, 'Loom_ID_Map.json'))
    by_name = find_mapping(id_map, internal_name='Windsaber_Cat_Form')
    assert by_name is not None
    by_folder = find_mapping(id_map, target_folder='druidcatharanir')
    assert by_folder is not None
    assert find_mapping(id_map, internal_name='nope') is None


def test_load_rejects_missing_mappings(tmp_path):
    path = tmp_path / 'bad.json'
    path.write_text(json.dumps({'version': '1.0.0'}))
    with pytest.raises(ValueError):
        load_id_map(str(path))


def test_load_rejects_incomplete_entry(tmp_path):
    path = tmp_path / 'bad.json'
    path.write_text(json.dumps({'mappings': [{'retail_id': 1}]}))
    with pytest.raises(ValueError):
        load_id_map(str(path))
