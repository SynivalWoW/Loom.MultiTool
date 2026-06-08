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


def test_extended_tables_present():
    defs = load_definitions()
    for table in ('SpellShapeshiftForm', 'CharSections', 'CreatureDisplayInfoExtra', 'ChrRaces'):
        assert table in defs


def test_loc_expands_to_16_strings_plus_flags():
    types = field_types('SpellShapeshiftForm')
    names = field_names('SpellShapeshiftForm')
    assert len(types) == 35  # 18 scalar/array columns + 17 for the loc field
    loc_strings = [n for n in names if n.startswith('Name_Lang_') and n != 'Name_Lang_flags']
    assert len(loc_strings) == 16
    assert 'Name_Lang_flags' in names
    assert types[names.index('Name_Lang_flags')] is int


def test_unknown_table_raises():
    try:
        field_types('DoesNotExist')
        assert False, 'expected KeyError'
    except KeyError:
        pass
