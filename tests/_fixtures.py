"""Synthetic .m2 / .skin binary builders for the retroport test-suite.

These produce *just enough* of a valid WotLK MD20 header and file-based SKIN to exercise the
binary repair modules without shipping any real (copyrighted) Blizzard asset.
"""

import struct

# Header scratch space large enough to hold every field the modules touch (up to 0x134 + 4).
_M2_HEADER = 0x140


def make_m2(
    global_flags: int = 0,
    n_name: int = 0,
    ofs_name: int = 0,
    n_views: int = 1,
    n_vertices: int = 0,
    n_particle: int = 0,
    n_ribbon: int = 0,
    n_texture_combiner: int = 0,
    combiner_values=None,
    textures=None,
) -> bytes:
    """Build a minimal MD20 .m2 byte string with the requested header values."""
    buf = bytearray(_M2_HEADER)
    buf[0:4] = b'MD20'
    struct.pack_into('<I', buf, 8, n_name)
    struct.pack_into('<I', buf, 12, ofs_name)
    struct.pack_into('<I', buf, 16, global_flags)
    struct.pack_into('<I', buf, 60, n_vertices)
    struct.pack_into('<I', buf, 68, n_views)
    struct.pack_into('<I', buf, 288, n_ribbon)
    struct.pack_into('<I', buf, 296, n_particle)

    if textures:
        tex_block_ofs = len(buf)
        buf += bytearray(16 * len(textures))  # reserve the texture records
        for i, name in enumerate(textures):
            name_bytes = name.encode('ascii') + b'\x00'
            name_ofs = len(buf)
            buf += name_bytes
            struct.pack_into('<I', buf, tex_block_ofs + i * 16 + 8, len(name_bytes))  # M2Array count
            struct.pack_into('<I', buf, tex_block_ofs + i * 16 + 12, name_ofs)        # M2Array offset
        struct.pack_into('<I', buf, 80, len(textures))   # nTextures
        struct.pack_into('<I', buf, 84, tex_block_ofs)   # ofsTextures

    if combiner_values is not None:
        ofs = len(buf)
        struct.pack_into('<I', buf, 304, len(combiner_values))
        struct.pack_into('<I', buf, 308, ofs)
        for value in combiner_values:
            buf += struct.pack('<H', value)
    else:
        struct.pack_into('<I', buf, 304, n_texture_combiner)

    return bytes(buf)


def make_skin(submesh_bone_count: int = 10, batches=None) -> bytes:
    """Build a minimal file-based SKIN with one submesh and the given render batches.

    ``batches`` is a list of ``(texture_combo_index, texture_count)`` tuples.
    """
    batches = batches or []
    header = bytearray(64)
    header[0:4] = b'SKIN'

    ofs_submeshes = 64
    struct.pack_into('<I', header, 28, 1)              # nSubmeshes
    struct.pack_into('<I', header, 32, ofs_submeshes)  # ofsSubmeshes

    submesh = bytearray(48)
    struct.pack_into('<H', submesh, 12, submesh_bone_count)  # submesh bone count at +0x0C

    ofs_units = ofs_submeshes + 48
    struct.pack_into('<I', header, 36, len(batches))   # nTextureUnits
    struct.pack_into('<I', header, 40, ofs_units)      # ofsTextureUnits

    units = bytearray()
    for combo_index, tex_count in batches:
        unit = bytearray(24)
        struct.pack_into('<H', unit, 16, tex_count)    # textureCount
        struct.pack_into('<H', unit, 18, combo_index)  # textureComboIndex
        units += unit

    return bytes(header + submesh + units)


def write_file(path: str, data: bytes) -> str:
    with open(path, 'wb') as handle:
        handle.write(data)
    return path
