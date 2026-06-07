"""loom_converter.py — Linux-aware wrapper around the bundled MD21->MD20 MultiConverter.

The bundled ``MultiConverter_Console.exe`` is a .NET/Mono assembly. On Windows it runs natively;
on Linux it runs under ``mono``. BUT its ``Converter.Run`` lower-cases every path before calling
``File.Exists`` — which is case-insensitive on Windows but case-SENSITIVE on Linux, so the model
files must be lower-cased on disk first or the converter crashes in ``RemoveLegionChunks``.

This wrapper handles both the ``mono`` invocation and the lower-casing workaround transparently,
so the MD21->MD20 step can run head-less on Linux/CI.
"""

from __future__ import annotations

import glob
import os
import platform
import subprocess

DEFAULT_CONVERTER = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'MultiConverter_Console.exe')


def needs_mono() -> bool:
    """True on non-Windows hosts, where the .NET converter runs under mono."""
    return platform.system() != 'Windows'


def lowercase_dir(model_dir: str) -> dict:
    """Lower-case every filename in ``model_dir`` (the converter's case-sensitivity workaround)."""
    mapping: dict = {}
    for path in glob.glob(os.path.join(model_dir, '*')):
        base = os.path.basename(path)
        lowered = base.lower()
        if base != lowered:
            os.replace(path, os.path.join(model_dir, lowered))
            mapping[base] = lowered
    return mapping


def build_command(m2_path: str, converter: str = DEFAULT_CONVERTER, mono: str = 'mono') -> list[str]:
    """Build the converter command line (prefixed with ``mono`` off-Windows)."""
    if needs_mono():
        return [mono, converter, m2_path]
    return [converter, m2_path]


def convert_m2(
    m2_path: str,
    converter: str = DEFAULT_CONVERTER,
    mono: str = 'mono',
    runner=subprocess.run,
    timeout: int = 300,
    creationflags: int = 0,
) -> dict:
    """Run the MD21->MD20 conversion on a single .m2 and report the outcome.

    Lower-cases the model folder first (off-Windows), runs the converter, then re-reads the magic
    to confirm the downgrade — so callers never silently proceed on a failed conversion. mono can
    hang *after* printing 'Done.', so a timeout is treated as a soft outcome and success is decided
    by the on-disk magic. ``creationflags`` is forwarded to the runner (e.g. CREATE_NO_WINDOW on
    Windows). ``runner`` is injectable for testing.
    """
    model_dir = os.path.dirname(m2_path) or '.'
    if needs_mono():
        lowercase_dir(model_dir)
        m2_path = os.path.join(model_dir, os.path.basename(m2_path).lower())

    try:
        result = runner(
            build_command(m2_path, converter, mono),
            capture_output=True,
            text=True,
            timeout=timeout,
            creationflags=creationflags,
        )
        returncode = getattr(result, 'returncode', None)
    except subprocess.TimeoutExpired:
        returncode = 'timeout'

    with open(m2_path, 'rb') as handle:
        magic = handle.read(4)

    return {
        'm2_path': m2_path,
        'converted': magic == b'MD20',
        'magic': magic.decode('ascii', 'replace'),
        'returncode': returncode,
    }
