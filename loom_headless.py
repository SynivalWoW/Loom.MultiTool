"""loom_headless.py — CLI entrypoint for the retroport binary pipeline (spec §7).

Lets the whole repair pipeline run without the dearpygui GUI, for CI/CD batch deployment::

    python loom_headless.py --headless --input "To Convert/Druid/Windsaber_Cat_Form" \\
        --fix-combiners --link-assets --gen-dbc --id-map Loom_ID_Map.json

Emits the §7 validation summary (nViews, global_flags, combiner array, emitter safety) as JSON
on stdout and exits non-zero on failure.
"""

from __future__ import annotations

import argparse
import json
import os
import sys

import glob

from loom_converter import convert_m2
from loom_id_map import load_id_map, find_mapping
from loom_orchestrator import run_orchestration, find_entry_m2
from core_parser import M2File


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description='Loom headless retroport binary pipeline')
    parser.add_argument('--headless', action='store_true', help='accepted for spec/CLI parity')
    parser.add_argument('--input', required=True, help='To Convert/<Category>/<ModelName> folder')
    parser.add_argument('--convert', action='store_true', help='run the MD21->MD20 converter first if the model is still Legion')
    parser.add_argument('--converter', help='path to MultiConverter_Console.exe (default: bundled)')
    parser.add_argument('--fix-combiners', action='store_true', help='rebuild textureCombinerCombos')
    parser.add_argument('--link-assets', action='store_true', help='patch nViews/nName and link skins/anims')
    parser.add_argument('--gen-dbc', action='store_true', help='emit a CreatureDisplayInfo.dbc')
    parser.add_argument('--strip-emitters', action='store_true', help='zero particle/ribbon emitters')
    parser.add_argument('--clear-combiner', action='store_true', help='clear the 0x8 flag instead of rebuilding combos')
    parser.add_argument('--max-vertices', type=int, default=21845, help='WotLK-safe vertex ceiling (default 21845)')
    parser.add_argument('--id-map', help='path to Loom_ID_Map.json')
    parser.add_argument('--internal-name', help='override internal model name')
    parser.add_argument('--display-id', type=int, help='minted DisplayID for DBC generation')
    return parser


def resolve_mapping(args: argparse.Namespace) -> dict:
    """Build the mapping dict from --id-map (by target folder) or --internal-name."""
    folder = os.path.basename(os.path.normpath(args.input))
    if args.id_map:
        id_map = load_id_map(args.id_map)
        mapping = find_mapping(id_map, internal_name=args.internal_name, target_folder=folder)
        if mapping is not None:
            return mapping
    return {
        'internal_name': args.internal_name or folder,
        'target_folder': folder,
    }


def run(argv: list[str]) -> int:
    args = build_parser().parse_args(argv)
    if not os.path.isdir(args.input):
        print(json.dumps({'status': 'error', 'error': f'input not found: {args.input}'}))
        return 1

    # Optional MD21->MD20 conversion before the WotLK repairs.
    if args.convert:
        entry = find_entry_m2(args.input)
        if entry is not None:
            with M2File(entry) as model:
                still_md21 = model.is_md21
            if still_md21:
                converter = args.converter or None
                conv = convert_m2(entry, converter) if converter else convert_m2(entry)
                if not conv['converted']:
                    print(json.dumps({'status': 'error', 'error': 'MD21->MD20 conversion failed', 'detail': conv}))
                    return 1

    mapping = resolve_mapping(args)
    result = run_orchestration(
        args.input,
        mapping,
        fix_combiners=args.fix_combiners,
        link_assets=args.link_assets,
        gen_dbc=args.gen_dbc,
        strip_emitters=args.strip_emitters,
        clear_combiner=args.clear_combiner,
        max_vertices=args.max_vertices,
        display_id=args.display_id,
    )
    print(json.dumps(result, indent=2))
    return 0 if result.get('status') == 'ok' else 1


if __name__ == '__main__':  # pragma: no cover
    raise SystemExit(run(sys.argv[1:]))
