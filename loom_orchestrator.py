"""loom_orchestrator.py — binary pipeline bridge (spec §6.B).

Drives the head-less repair pipeline over a single ``To Convert/<Category>/<ModelName>/``
folder produced by Loom.Export: it links the assets, fixes the textureCombinerCombos OOB,
evaluates emitter safety, optionally emits a CreatureDisplayInfo.dbc, and returns a JSON
metadata payload that the Keira3 DBAL consumes to draft realm-aware SQL.

SQL deployment itself is intentionally *not* done here — the orchestrator is realm-agnostic;
the DBAL decides Live vs PTR. Importable (``run_orchestration``) and CLI-runnable.
"""

from __future__ import annotations

import glob
import json
import os
import sys

import asset_linker
import combiner_repair
import loom_dbc_generator
from core_parser import M2File


def find_entry_m2(target_dir: str) -> str | None:
    """The model's entry file: the first ``.m2`` in the folder."""
    matches = sorted(glob.glob(os.path.join(target_dir, '*.m2')))
    return matches[0] if matches else None


def find_entry_skin(target_dir: str) -> str | None:
    """The skin used to size the combiner array (prefers ``*00.skin``)."""
    matches = sorted(glob.glob(os.path.join(target_dir, '*00.skin')))
    if not matches:
        matches = sorted(glob.glob(os.path.join(target_dir, '*.skin')))
    return matches[0] if matches else None


def run_orchestration(
    target_dir: str,
    mapping: dict,
    *,
    fix_combiners: bool = True,
    link_assets: bool = True,
    gen_dbc: bool = False,
    strip_emitters: bool = False,
    clear_combiner: bool = False,
    max_vertices: int = 21845,
    display_id: int | None = None,
) -> dict:
    """Run the repair pipeline over ``target_dir`` and return a JSON-serialisable summary."""
    internal_name = mapping.get('internal_name') or os.path.basename(os.path.normpath(target_dir))
    target_folder = mapping.get('target_folder') or os.path.basename(os.path.normpath(target_dir))

    result: dict = {
        'internal_name': internal_name,
        'target_folder': target_folder,
        'status': 'ok',
    }

    m2_path = find_entry_m2(target_dir)
    if m2_path is None:
        result['status'] = 'error'
        result['error'] = 'no .m2 file found in target folder'
        return result

    result['entry'] = os.path.basename(m2_path)

    # Guard: the MD20 repairs would corrupt a still-Legion MD21 (chunked) file. The MD21->MD20
    # strip + M2Array offset rebasing must happen in the converter first.
    with M2File(m2_path) as model:
        if model.is_md21:
            result['status'] = 'error'
            result['is_md21'] = True
            result['error'] = 'model is still MD21 (Legion); run MD21->MD20 conversion first'
            return result
    result['is_md21'] = False

    if link_assets:
        asset_linker.link_skins(target_dir)
        asset_linker.set_nviews_to_skin_count(m2_path, target_dir)  # nViews == count of .skin files
        asset_linker.link_anims(target_dir)
        asset_linker.fix_nname(m2_path, internal_name)

    skin_path = find_entry_skin(target_dir)
    emitters = asset_linker.evaluate_emitters(m2_path, strip=strip_emitters)

    combiner = {'action': 'skipped', 'combiner_array': []}
    if fix_combiners:
        combiner = combiner_repair.repair_combiner(m2_path, skin_path, clear=clear_combiner)

    vertices = asset_linker.validate_vertices(m2_path, max_vertices=max_vertices)
    assets = asset_linker.check_missing_assets(m2_path, target_dir)

    with M2File(m2_path) as model:
        result['nViews'] = model.n_views
        result['global_flags'] = model.global_flags

    resolved_display_id = display_id if display_id is not None else mapping.get('retail_id', 0)

    result['skin_count'] = asset_linker.count_skin_profiles(target_dir)
    result['combiner_array'] = combiner.get('combiner_array', [])
    result['combiner_action'] = combiner.get('action')
    result['emitter_safe'] = emitters['emitter_safe']
    result['particles'] = emitters['particles']
    result['ribbons'] = emitters['ribbons']
    result['vertex_count'] = vertices['vertex_count']
    result['vertex_safe'] = vertices['vertex_safe']
    result['missing_textures'] = assets['missing_textures']
    result['anim_count'] = assets['anim_count']
    result['display_id'] = resolved_display_id
    # Overall gate: only deploy when the binary validation metrics pass (spec §7).
    result['valid'] = vertices['vertex_safe'] and not assets['missing_textures']

    if gen_dbc:
        dbc_path = os.path.join(target_dir, f'{internal_name}_CreatureDisplayInfo.dbc')
        loom_dbc_generator.generate_creature_display_info(dbc_path, mapping, resolved_display_id)
        result['dbc'] = os.path.basename(dbc_path)

    return result


def _main(argv: list[str]) -> int:  # pragma: no cover - thin CLI wrapper
    if len(argv) < 3:
        print('usage: python loom_orchestrator.py <target_dir> <mapping_json> '
              '[--gen-dbc] [--display-id N] [--clear-combiner] [--strip-emitters]')
        return 2
    target_dir = argv[1]
    mapping = json.loads(argv[2])
    rest = argv[3:]
    display_id = None
    if '--display-id' in rest:
        display_id = int(rest[rest.index('--display-id') + 1])
    result = run_orchestration(
        target_dir,
        mapping,
        gen_dbc='--gen-dbc' in rest,
        clear_combiner='--clear-combiner' in rest,
        strip_emitters='--strip-emitters' in rest,
        display_id=display_id,
    )
    print(json.dumps(result))
    return 0 if result.get('status') == 'ok' else 1


if __name__ == '__main__':  # pragma: no cover
    raise SystemExit(_main(sys.argv))
