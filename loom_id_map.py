"""loom_id_map.py — loader/validator for Loom_ID_Map.json (spec §6.A).

The ID map is the bridge between an extracted retail asset and its retroport target: it pins
each ``retail_id`` to an ``internal_name`` / ``target_folder`` plus texture-slot and repair
``requirements``. The orchestrator resolves entries by ``internal_name`` or ``target_folder``.
"""

from __future__ import annotations

import json

REQUIRED_ENTRY_KEYS = ('retail_id', 'internal_name', 'target_folder')


def load_id_map(path: str) -> dict:
    """Load and shape-validate a Loom_ID_Map.json document."""
    with open(path, 'r', encoding='utf-8') as handle:
        data = json.load(handle)

    mappings = data.get('mappings')
    if not isinstance(mappings, list):
        raise ValueError('Loom_ID_Map.json must contain a "mappings" list')

    for entry in mappings:
        missing = [key for key in REQUIRED_ENTRY_KEYS if key not in entry]
        if missing:
            raise ValueError(f'mapping entry missing keys {missing}: {entry!r}')

    return data


def find_mapping(id_map: dict, internal_name: str | None = None, target_folder: str | None = None) -> dict | None:
    """Resolve a single mapping entry by internal name or target folder."""
    for entry in id_map.get('mappings', []):
        if internal_name is not None and entry.get('internal_name') == internal_name:
            return entry
        if target_folder is not None and entry.get('target_folder') == target_folder:
            return entry
    return None
