"""dbc_definitions.py — DBC column layouts driven by the WDBX Editor definitions.

Rather than hand-maintaining field layouts, the WDBC writer reads them from a bundled snapshot
of WDBX Editor's authoritative ``WotLK 3.3.5 (12340)`` definitions (``definitions/
dbc_wotlk_12340.json``). This keeps the column order/types from drifting out of sync with the
client and makes adding new DBC tables a data-only change.
"""

from __future__ import annotations

import json
import os

DEFINITIONS_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'definitions', 'dbc_wotlk_12340.json')

_TYPE_MAP = {'int': int, 'uint': int, 'float': float, 'string': str}


def load_definitions(path: str = DEFINITIONS_PATH) -> dict:
    """Load the bundled DBC definition document."""
    with open(path, 'r', encoding='utf-8') as handle:
        return json.load(handle)


def _table(table: str, definitions: dict | None) -> dict:
    definitions = definitions if definitions is not None else load_definitions()
    if table not in definitions:
        raise KeyError(f'no DBC definition for table {table!r}')
    return definitions[table]


def field_types(table: str, definitions: dict | None = None) -> list[type]:
    """Return the python types for every (array-expanded) column of ``table``."""
    columns: list[type] = []
    for field in _table(table, definitions)['fields']:
        py_type = _TYPE_MAP[field['type']]
        columns += [py_type] * field.get('array', 1)
    return columns


def field_names(table: str, definitions: dict | None = None) -> list[str]:
    """Return the (array-expanded) column names of ``table`` (e.g. TextureVariation_1..3)."""
    names: list[str] = []
    for field in _table(table, definitions)['fields']:
        count = field.get('array', 1)
        if count > 1:
            names += [f"{field['name']}_{i + 1}" for i in range(count)]
        else:
            names.append(field['name'])
    return names
