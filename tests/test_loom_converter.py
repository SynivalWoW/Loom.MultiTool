import os
import platform
import subprocess

from loom_converter import needs_mono, lowercase_dir, build_command, convert_m2


def test_needs_mono_matches_platform():
    assert needs_mono() == (platform.system() != 'Windows')


def test_lowercase_dir(tmp_path):
    (tmp_path / 'FooBar.M2').write_bytes(b'x')
    (tmp_path / 'already.skin').write_bytes(b'x')
    mapping = lowercase_dir(str(tmp_path))
    assert mapping == {'FooBar.M2': 'foobar.m2'}
    assert (tmp_path / 'foobar.m2').exists()
    assert (tmp_path / 'already.skin').exists()


def test_build_command_mono(monkeypatch):
    monkeypatch.setattr('loom_converter.platform.system', lambda: 'Linux')
    assert build_command('/x/m.m2', '/c/conv.exe', 'mono') == ['mono', '/c/conv.exe', '/x/m.m2']


def test_build_command_windows(monkeypatch):
    monkeypatch.setattr('loom_converter.platform.system', lambda: 'Windows')
    assert build_command('/x/m.m2', '/c/conv.exe') == ['/c/conv.exe', '/x/m.m2']


def test_convert_m2_lowercases_and_verifies(tmp_path, monkeypatch):
    monkeypatch.setattr('loom_converter.platform.system', lambda: 'Linux')
    m2 = tmp_path / 'Model.m2'
    m2.write_bytes(b'MD21' + b'\x00' * 60)

    captured = {}

    def fake_runner(cmd, **kwargs):
        captured['cmd'] = cmd
        with open(cmd[-1], 'wb') as handle:  # simulate the converter writing MD20
            handle.write(b'MD20' + b'\x00' * 60)

        class Result:
            returncode = 0

        return Result()

    result = convert_m2(str(m2), '/c/conv.exe', 'mono', runner=fake_runner)

    assert result['converted'] is True
    assert result['magic'] == 'MD20'
    assert os.path.basename(result['m2_path']) == 'model.m2'  # lower-cased on disk
    assert captured['cmd'][0] == 'mono'


def test_convert_m2_timeout_falls_back_to_magic(tmp_path, monkeypatch):
    monkeypatch.setattr('loom_converter.platform.system', lambda: 'Linux')
    m2 = tmp_path / 'model.m2'
    m2.write_bytes(b'MD20' + b'\x00' * 60)  # already-converted on disk

    def fake_runner(cmd, **kwargs):
        raise subprocess.TimeoutExpired(cmd, 1)

    result = convert_m2(str(m2), '/c/conv.exe', 'mono', runner=fake_runner)
    assert result['returncode'] == 'timeout'
    assert result['converted'] is True  # decided by on-disk magic
