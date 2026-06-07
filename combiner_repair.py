"""combiner_repair.py — rebuilds the textureCombinerCombos array (Error #132 §2.A).

Legacy Retail->WotLK converters set ``global_flags & 0x08`` (advertising that a
``textureCombinerCombos`` array trails the header) but emit a truncated/invalid stub such as
``[1, 4]``. When a .skin render batch then references a combo slot beyond that stub, the
3.3.5a client reads adjacent model memory as a pointer -> massive OOB read -> instant crash.

The fix inspects the .skin render batches, finds the highest combo slot any batch can touch,
and rebuilds ``textureCombinerCombos`` as a *complete identity sequence* ``[0, 1, 2, ... N]``
so every batch reference stays in bounds.
"""

from __future__ import annotations

import struct
import sys

from core_parser import M2File, SkinFile, FLAG_USE_TEXTURE_COMBINER_COMBOS
from utils.offsets import M2Offsets


def find_max_combo_index(skin: SkinFile) -> int:
    """Return the highest textureCombinerCombos slot referenced by the skin (-1 if none)."""
    return skin.max_combo_slot()


def repair_combiner(m2_path: str, skin_path: str | None = None, force: bool = False) -> dict:
    """Rebuild ``textureCombinerCombos`` to a safe identity sequence when needed.

    Args:
        m2_path: path to the converted (MD20) .m2 file, opened read/write.
        skin_path: path to a .skin file used to size the array; optional.
        force: rebuild even when the current array already looks large enough.

    Returns:
        A summary dict: ``action`` (``repaired`` | ``skipped``), ``global_flags``,
        ``combiner_len``, ``combiner_array`` and ``max_combo_index``.
    """
    needed_len = 0
    if skin_path is not None:
        needed_len = find_max_combo_index(SkinFile(skin_path)) + 1

    with M2File(m2_path) as m2:
        flags = m2.global_flags
        has_flag = bool(flags & FLAG_USE_TEXTURE_COMBINER_COMBOS)
        current_len = m2.read_field(M2Offsets.nTextureCombiner) if has_flag else 0

        target_len = max(needed_len, current_len)
        # Repair is required when the advertised array is too small for the batches,
        # when batches need combos but the flag is missing, or when forced.
        needs_repair = force or (needed_len > current_len) or (needed_len > 0 and not has_flag)

        if force and target_len == 0:
            target_len = max(current_len, 1)

        if not needs_repair or target_len == 0:
            return {
                'action': 'skipped',
                'global_flags': flags,
                'combiner_len': current_len,
                'combiner_array': list(range(current_len)),
                'max_combo_index': needed_len - 1,
            }

        identity = list(range(target_len))
        payload = struct.pack('<%dH' % target_len, *identity)
        new_ofs = m2.append_array(payload)

        m2.write_field(M2Offsets.nTextureCombiner, target_len)
        m2.write_field(M2Offsets.ofsTextureCombiner, new_ofs)

        new_flags = flags | FLAG_USE_TEXTURE_COMBINER_COMBOS
        m2.write_field(M2Offsets.globalFlags, new_flags)

        return {
            'action': 'repaired',
            'global_flags': new_flags,
            'combiner_len': target_len,
            'combiner_array': identity,
            'max_combo_index': needed_len - 1,
            'ofs': new_ofs,
        }


def _main(argv: list[str]) -> int:  # pragma: no cover - thin CLI wrapper
    if len(argv) < 2:
        print('usage: python combiner_repair.py <model.m2> [model.skin] [--force]')
        return 2
    m2_path = argv[1]
    skin_path = None
    force = '--force' in argv
    for arg in argv[2:]:
        if arg != '--force':
            skin_path = arg
    result = repair_combiner(m2_path, skin_path, force=force)
    print(result)
    return 0


if __name__ == '__main__':  # pragma: no cover
    raise SystemExit(_main(sys.argv))
