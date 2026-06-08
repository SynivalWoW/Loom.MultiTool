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


def test_convert_m2_runs_through_lowercase_staging_even_with_uppercase_parent(tmp_path, monkeypatch):
    # The converter lower-cases the whole path; an upper-case PARENT must not break it on Linux.
    monkeypatch.setattr('loom_converter.platform.system', lambda: 'Linux')
    upper_dir = tmp_path / 'UpperCase Dir'
    upper_dir.mkdir()
    m2 = upper_dir / 'Model.m2'
    m2.write_bytes(b'MD21' + b'\x00' * 60)

    captured = {}

    def fake_runner(cmd, **kwargs):
        captured['cmd'] = cmd
        with open(cmd[-1], 'wb') as handle:  # write through the staging symlink -> real file
            handle.write(b'MD20' + b'\x00' * 60)

        class Result:
            returncode = 0

        return Result()

    result = convert_m2(str(m2), '/c/conv.exe', 'mono', runner=fake_runner)

    assert result['converted'] is True  # conversion landed in the real (upper-case) folder
    run_path = captured['cmd'][-1]
    assert run_path == run_path.lower()  # the path the converter sees is fully lower-case
    assert os.path.basename(run_path) == 'model.m2'
    assert not os.path.exists(os.path.dirname(os.path.dirname(run_path)))  # staging cleaned up


def test_convert_m2_retries_transient_failure(tmp_path, monkeypatch):
    monkeypatch.setattr('loom_converter.platform.system', lambda: 'Linux')
    m2 = tmp_path / 'model.m2'
    m2.write_bytes(b'MD21' + b'\x00' * 60)

    calls = {'n': 0}

    def fake_runner(cmd, **kwargs):
        calls['n'] += 1

        class Result:
            returncode = 1

        if calls['n'] >= 2:  # the second attempt succeeds
            with open(cmd[-1], 'wb') as handle:
                handle.write(b'MD20' + b'\x00' * 60)
            Result.returncode = 0
        return Result()

    result = convert_m2(str(m2), '/c/conv.exe', 'mono', runner=fake_runner)
    assert calls['n'] == 2  # retried once, then stopped on success
    assert result['converted'] is True


def test_convert_m2_gives_up_after_all_attempts(tmp_path, monkeypatch):
    monkeypatch.setattr('loom_converter.platform.system', lambda: 'Linux')
    m2 = tmp_path / 'model.m2'
    m2.write_bytes(b'MD21' + b'\x00' * 60)

    calls = {'n': 0}

    def fake_runner(cmd, **kwargs):
        calls['n'] += 1

        class Result:
            returncode = 1

        return Result()  # never writes MD20

    result = convert_m2(str(m2), '/c/conv.exe', 'mono', runner=fake_runner, attempts=2)
    assert calls['n'] == 2  # exhausted the attempts
    assert result['converted'] is False
    assert result['returncode'] == 1
