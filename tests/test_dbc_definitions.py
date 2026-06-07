import dataclasses

from dbc_definitions import load_definitions, field_types, field_names
from loom_dbc_generator import types_of
from dbc_records.creature_display_info import CreatureDisplayInfoRecord
from dbc_records.creature_model_data import CreatureModelDataRecord


def test_load_definitions_build():
    defs = load_definitions()
    assert defs['build'] == 12340
    assert 'CreatureDisplayInfo' in defs and 'CreatureModelData' in defs


def test_field_types_expand_arrays():
    cols = field_types('CreatureDisplayInfo')
    assert len(cols) == 16  # 13 scalars + TextureVariation[3]
    assert cols[6] is str and cols[7] is str and cols[8] is str  # TextureVariation x3


def test_field_names_expand_arrays():
    names = field_names('CreatureDisplayInfo')
    assert names[0] == 'ID'
    assert names[6:9] == ['TextureVariation_1', 'TextureVariation_2', 'TextureVariation_3']


def test_definitions_match_dataclasses():
    # the bundled WDBX definitions must stay in lock-step with the dbc_records dataclasses
    assert field_types('CreatureDisplayInfo') == types_of(CreatureDisplayInfoRecord)
    assert field_types('CreatureModelData') == types_of(CreatureModelDataRecord)


def test_unknown_table_raises():
    try:
        field_types('DoesNotExist')
        assert False, 'expected KeyError'
    except KeyError:
        pass
