"""tests/test_packaging.py: اتساق ملفات التغليف (إصدار، spec، مثبّت) وأدوات البناء، بلا بناء فعلي."""

from __future__ import annotations

import re
import sys
import zipfile
from pathlib import Path

import pytest

from raindesk.core.constants import APP_NAME, APP_VERSION, RUN_VALUE_NAME

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))
import package  # noqa: E402


def _read(relative: str) -> str:
    return (ROOT / relative).read_text(encoding="utf-8")


def test_version_info_matches_app_version() -> None:
    text = _read("version_info.txt")
    four = ", ".join([*APP_VERSION.split("."), "0"])
    assert f"filevers=({four})" in text
    assert f"prodvers=({four})" in text
    assert f"StringStruct('FileVersion', '{APP_VERSION}.0')" in text
    assert f"StringStruct('ProductVersion', '{APP_VERSION}.0')" in text
    assert f"StringStruct('ProductName', '{APP_NAME}')" in text


def test_installer_version_matches_app_version() -> None:
    match = re.search(r'#define MyAppVersion "([^"]+)"', _read("installer/raindesk.iss"))
    assert match is not None and match.group(1) == APP_VERSION


def test_installer_autostart_matches_the_app_command() -> None:
    text = _read("installer/raindesk.iss")
    assert "PrivilegesRequired=lowest" in text  # بلا صلاحيات مسؤول
    assert '""{app}\\{#MyAppExe}"" --minimized' in text  # مقتبس ويبدأ مخفيًا
    assert f'#define MyAppName "{RUN_VALUE_NAME}"' in text  # اسم قيمة Run يطابق التطبيق
    assert "RegDeleteValue" in text  # الحذف يزيل القيمة أيًّا كان مصدرها


def test_spec_is_a_windowed_onedir_build_without_upx() -> None:
    text = _read("raindesk.spec")
    compile(text, "raindesk.spec", "exec")  # صياغة سليمة (بلا تشغيل PyInstaller)
    assert "console=False" in text
    assert "upx=False" in text and "upx=True" not in text
    assert "exclude_binaries=True" in text and "COLLECT(" in text  # onedir لا onefile
    assert 'icon="assets/raindesk.ico"' in text
    assert 'version="version_info.txt"' in text
    assert "RAINDESK_NO_SOUND" in text and "PySide6.QtMultimedia" in text


def test_spec_does_not_exclude_qt_modules_the_app_imports() -> None:
    spec = _read("raindesk.spec")
    excluded = set(re.findall(r'"(PySide6\.Qt\w+)"', spec.split("EXCLUDES =")[0]))
    imported: set[str] = set()
    for path in (ROOT / "raindesk").rglob("*.py"):
        imported.update(re.findall(r"from (PySide6\.Qt\w+) import", path.read_text("utf-8")))
    assert imported, "the scan should find the app's Qt imports"
    assert not (imported & excluded), imported & excluded


def test_entry_point_and_icon_exist() -> None:
    assert (ROOT / "main.py").is_file()
    assert (ROOT / "assets" / "raindesk.ico").is_file()


def test_collect_licenses_copies_matching_files(tmp_path: Path) -> None:
    prefix = tmp_path / "py"
    prefix.mkdir()
    (prefix / "LICENSE.txt").write_text("PSF", encoding="utf-8")
    notices = tmp_path / "NOTICES.md"
    notices.write_text("notices", encoding="utf-8")
    out = tmp_path / "licenses"
    copied = package.collect_licenses(out, ("numpy",), prefix, notices)
    names = {path.name for path in copied}
    assert {"PSF-LICENSE.txt", "THIRD_PARTY_NOTICES.md"} <= names
    assert any(path.parent.name == "numpy" for path in copied)  # رخصة NumPy وُجدت
    assert (out / "PSF-LICENSE.txt").read_text(encoding="utf-8") == "PSF"


def test_collect_licenses_skips_unknown_packages(tmp_path: Path) -> None:
    out = tmp_path / "licenses"
    copied = package.collect_licenses(out, ("no_such_package_xyz",), tmp_path, tmp_path / "x")
    assert copied == []


def test_has_lgpl_text(tmp_path: Path) -> None:
    assert not package.has_lgpl_text(tmp_path)
    (tmp_path / "sub").mkdir()
    (tmp_path / "sub" / "lgpl-3.0.txt").write_text("x", encoding="utf-8")
    assert package.has_lgpl_text(tmp_path)


def test_make_zip_roots_the_archive_in_the_folder_and_hashes_it(tmp_path: Path) -> None:
    app = tmp_path / "RainDesk"
    (app / "licenses").mkdir(parents=True)
    (app / "RainDesk.exe").write_bytes(b"exe")
    (app / "licenses" / "a.txt").write_text("a", encoding="utf-8")
    zip_path = tmp_path / "out" / "r.zip"
    digest = package.make_zip(app, zip_path)
    assert re.fullmatch(r"[0-9a-f]{64}", digest)
    with zipfile.ZipFile(zip_path) as archive:
        assert sorted(archive.namelist()) == ["RainDesk/RainDesk.exe", "RainDesk/licenses/a.txt"]


def test_icon_build_writes_every_size(tmp_path: Path) -> None:
    pytest.importorskip("PIL")
    import make_icon

    path, sizes = make_icon.build_icon(tmp_path / "t.ico", (16, 32, 256))
    assert path.is_file() and sizes == [16, 32, 256]


def test_icon_build_rejects_oversize(tmp_path: Path) -> None:
    pytest.importorskip("PIL")
    import make_icon

    with pytest.raises(ValueError):
        make_icon.build_icon(tmp_path / "t.ico", (512,))
    with pytest.raises(ValueError):
        make_icon.build_icon(tmp_path / "t.ico", ())
