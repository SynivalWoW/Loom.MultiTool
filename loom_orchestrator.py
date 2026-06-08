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
import loom_converter
import loom_dbc_generator
import texture_linker
from core_parser import M2File


def find_entry_m2(target_dir: str) -> str | None:
    """The model's entry file: the first ``.m2`` in the folder."""
    matches = sorted(glob.glob(os.path.join(target_dir, '*.m2')))
    return matches[0] if matches else None


def find_manifest(target_dir: str, entry_basename: str | None = None) -> str | None:
    """The wow.export ``*.manifest.json`` for the model (prefers one matching the entry name)."""
    matches = sorted(glob.glob(os.path.join(target_dir, '*.manifest.json')))
    if not matches:
        return None
    if entry_basename:
        stem = os.path.splitext(entry_basename)[0].lower()
        for path in matches:
            if os.path.basename(path).lower().startswith(stem):
                return path
    return matches[0]


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
    convert: bool = False,
    converter_path: str | None = None,
    fix_combiners: bool = True,
    link_assets: bool = True,
    align_skins: bool = True,
    gen_dbc: bool = False,
    strip_emitters: bool = False,
    clear_combiner: bool = False,
    link_textures: bool = True,
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

    with M2File(m2_path) as model:
        md21 = model.is_md21

    # Capture the Legion TXID texture FileDataIDs + manifest BEFORE conversion drops the TXID chunk,
    # so the hard-coded texture filenames can be re-embedded into the downgraded MD20 afterwards.
    txid_fileids: list[int] = []
    manifest_map: dict = {}
    if link_textures and md21:
        txid_fileids = texture_linker.read_txid_fileids(m2_path)
        manifest_path = find_manifest(target_dir, os.path.basename(m2_path))
        if manifest_path:
            manifest_map = texture_linker.manifest_texture_map(manifest_path)

    # Optional MD21->MD20 conversion (the converter does the chunk strip + offset rebasing).
    if convert and md21:
        conversion = loom_converter.convert_m2(m2_path, converter_path or loom_converter.DEFAULT_CONVERTER)
        result['converted'] = conversion.get('converted')
        m2_path = find_entry_m2(target_dir) or m2_path  # the converter may lower-case/rename it
        with M2File(m2_path) as model:
            md21 = model.is_md21

    result['entry'] = os.path.basename(m2_path)

    # Guard: the MD20 repairs would corrupt a still-Legion MD21 (chunked) file.
    if md21:
        result['status'] = 'error'
        result['is_md21'] = True
        result['error'] = 'model is still MD21 (Legion); run MD21->MD20 conversion first (pass --convert)'
        return result
    result['is_md21'] = False

    if link_assets:
        if align_skins:
            asset_linker.align_skins_to_m2(m2_path, target_dir)  # name skins <m2base>0N so WotLK finds them
        else:
            asset_linker.link_skins(target_dir)
        asset_linker.set_nviews_to_skin_count(m2_path, target_dir)  # nViews == count of .skin files
        asset_linker.link_anims(target_dir)
        asset_linker.fix_nname(m2_path, internal_name)

    # Re-embed the hard-coded texture filenames the MD21->MD20 converter dropped (TXID chunk), and
    # report which slots are replaceable (-> CreatureDisplayInfo.TextureVariation) for the DBC layer.
    if link_textures and txid_fileids and manifest_map:
        wired = texture_linker.wire_textures(m2_path, txid_fileids, manifest_map, f'Creature\\{internal_name}')
        result['textures_wired'] = len(wired['embedded'])
        result['texture_variation_slots'] = sorted(wired['texture_variations'])

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
    result['skins'] = sorted(os.path.basename(p) for p in glob.glob(os.path.join(target_dir, '*.skin')))
    result['combiner_array'] = combiner.get('combiner_array', [])
    result['combiner_action'] = combiner.get('action')
    result['emitter_safe'] = emitters['emitter_safe']
    result['particles'] = emitters['particles']
    result['ribbons'] = emitters['ribbons']
    result['vertex_count'] = vertices['vertex_count']
    result['vertex_safe'] = vertices['vertex_safe']
    result['vertex_loadable'] = vertices['vertex_loadable']
    result['vertex_status'] = vertices['vertex_status']
    result['missing_textures'] = assets['missing_textures']
    result['anim_count'] = assets['anim_count']
    result['display_id'] = resolved_display_id
    # Deploy gate: the model must actually load (<= 65535 verts) and have no missing textures.
    # `vertex_safe` stays a separate caution flag (over the conservative budget but still loadable).
    result['valid'] = vertices['vertex_loadable'] and not assets['missing_textures']

    if gen_dbc:
        chain_mapping = dict(mapping)
        chain_mapping.setdefault('entry', result.get('entry'))
        chain = loom_dbc_generator.generate_display_chain(target_dir, chain_mapping, resolved_display_id)
        result['dbc'] = chain['creature_display_info']
        result['dbc_chain'] = chain

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
    converter_path = None
    if '--converter' in rest:
        converter_path = rest[rest.index('--converter') + 1]
    result = run_orchestration(
        target_dir,
        mapping,
        convert='--convert' in rest,
        converter_path=converter_path,
        gen_dbc='--gen-dbc' in rest,
        clear_combiner='--clear-combiner' in rest,
        strip_emitters='--strip-emitters' in rest,
        display_id=display_id,
    )
    print(json.dumps(result))
    return 0 if result.get('status') == 'ok' else 1


if __name__ == '__main__':  # pragma: no cover
    raise SystemExit(_main(sys.argv))
