"""asset_linker.py — nViews / nName / skin / anim wiring (Error #132 §2.B & §2.C).

Legacy m2i roundtrips strip the internal model name (``nName == 0``) and collapse the LOD
skin count (``nViews == 1``). This module bypasses any m2i recreation: it reads the real LOD
count from the .skin set, writes ``nViews`` at the canonical header offset, sequentially links
the .skin / .anim files, repairs a stripped name, and reports particle/ribbon emitter safety.

Pure-stdlib (``glob``/``os``/``struct``) so it runs head-less on Linux/CI.
"""

from __future__ import annotations

import glob
import os
import sys

from core_parser import M2File
from utils.binary import Binary
from utils.offsets import M2Offsets


def get_nviews_from_skin(skin_path: str) -> int:
    """Derive the LOD/skin-profile count from the heaviest submesh's bone count.

    Mirrors the heuristic already used by the GUI converter (``convert_autotexture.get_nViews``)
    but as a standalone, GUI-free function.
    """
    with open(skin_path, 'rb') as skin:
        ofs_submeshes = Binary.get_int_from_bytes(skin, 32)
        n_bones = Binary.get_int_from_bytes(skin, ofs_submeshes + 12, length=2)

    if n_bones > 64:
        return 4
    if n_bones > 53:
        return 3
    if n_bones > 21:
        return 2
    return 1


def patch_nviews(m2_path: str, model_dir: str | None = None) -> int:
    """Write the correct ``nViews`` at offset 0x44 (only raising, never lowering it).

    The canonical MD20 ``num_skin_profiles`` field is at 0x44 (``M2Offsets.nViews``); this
    fixes the ``nViews == 1`` collapse. Returns the nViews value derived from the skins, or 0
    when no skin is present.
    """
    model_dir = model_dir or os.path.dirname(m2_path)
    skins = sorted(glob.glob(os.path.join(model_dir, '*00.skin')))
    if not skins:
        skins = sorted(glob.glob(os.path.join(model_dir, '*.skin')))
    if not skins:
        return 0

    n_views = get_nviews_from_skin(skins[0])
    with M2File(m2_path) as m2:
        if m2.n_views < n_views:
            m2.write_field(M2Offsets.nViews, n_views)
    return n_views


def link_skins(model_dir: str) -> list[str]:
    """Strip the ``_lod`` infix so skins are named contiguously (``model00.skin`` ...).

    Consolidates the GUI's ``rename_lod`` / ``rename_skins`` behaviour. Returns the sorted
    final list of .skin basenames in the directory.
    """
    for path in sorted(glob.glob(os.path.join(model_dir, '*.skin'))):
        name = os.path.basename(path)
        if '_lod' not in name:
            continue
        new_name = name.replace('_lod', '')
        new_path = os.path.join(model_dir, new_name)
        if not os.path.exists(new_path):
            os.rename(path, new_path)

    return sorted(os.path.basename(p) for p in glob.glob(os.path.join(model_dir, '*.skin')))


def link_anims(model_dir: str) -> list[str]:
    """Return the sorted .anim sequence backing the model (so the converter can wire them)."""
    return sorted(os.path.basename(p) for p in glob.glob(os.path.join(model_dir, '*.anim')))


def fix_nname(m2_path: str, model_name: str) -> dict:
    """Restore a stripped internal model name (``nName == 0``).

    Appends the ASCII name (null-terminated) to the file and points ``nName`` / ``ofsName``
    (header 0x08 / 0x0C) at it. No-op when a name already exists.
    """
    with M2File(m2_path) as m2:
        if m2.n_name != 0:
            return {'action': 'skipped', 'n_name': m2.n_name}

        name_bytes = model_name.encode('ascii', 'replace') + b'\x00'
        ofs = m2.append_array(name_bytes)
        m2.write_field(M2Offsets.nName, len(name_bytes))
        m2.write_field(M2Offsets.ofsName, ofs)
        return {'action': 'repaired', 'n_name': len(name_bytes), 'ofs_name': ofs}


def evaluate_emitters(m2_path: str, strip: bool = False) -> dict:
    """Report particle/ribbon emitter counts and optionally strip them for stability (§2.C).

    Without the source render data we cannot losslessly downgrade Legion emitter structs, so
    the default is report-and-flag; pass ``strip=True`` to zero the emitter counts when the
    model would otherwise risk client instability.
    """
    with M2File(m2_path) as m2:
        particles = m2.n_particle_emitters
        ribbons = m2.n_ribbon_emitters
        stripped = False

        if strip and (particles > 0 or ribbons > 0):
            m2.write_field(M2Offsets.nParticleEmitters, 0)
            m2.write_field(M2Offsets.nRibbonEmitters, 0)
            stripped = True

        return {
            'particles': particles,
            'ribbons': ribbons,
            'emitter_safe': not (particles > 0 or ribbons > 0) or stripped,
            'stripped': stripped,
        }


def _main(argv: list[str]) -> int:  # pragma: no cover - thin CLI wrapper
    if len(argv) < 2:
        print('usage: python asset_linker.py <model.m2> [model_name]')
        return 2
    m2_path = argv[1]
    model_dir = os.path.dirname(m2_path)
    name = argv[2] if len(argv) > 2 else os.path.splitext(os.path.basename(m2_path))[0]
    print({
        'n_views': patch_nviews(m2_path, model_dir),
        'skins': link_skins(model_dir),
        'anims': link_anims(model_dir),
        'nname': fix_nname(m2_path, name),
        'emitters': evaluate_emitters(m2_path),
    })
    return 0


if __name__ == '__main__':  # pragma: no cover
    raise SystemExit(_main(sys.argv))
