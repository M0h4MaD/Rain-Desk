"""tools/package.py

الغرض: أمر واحد يبني نسخة التوزيع: أيقونة، ثم PyInstaller، ثم ملفات التراخيص، ثم ZIP وبصمة SHA-256.
المسؤوليات: توليد assets/raindesk.ico إن غاب، وتشغيل pyinstaller raindesk.spec، ونسخ ملفات
    التراخيص من حزم Python المثبّتة إلى dist/RainDesk/licenses/، وضغط المجلد، وحساب البصمة.
    أداة وقت التطوير فقط: لا يستوردها التطبيق.
الاعتماديات: المكتبة القياسية وPyInstaller وPillow (للأيقونة) كما في requirements-dev.txt.
النمط التصميمي: Pipeline من دوال صغيرة نقية قدر الإمكان (collect_licenses وmake_zip قابلتان للاختبار).
ملاحظات: نصوص LGPLv3/GPLv3 لا تأتي مع عجلات PySide6؛ لذلك يطبع السكربت تحذيرًا إن لم يجدها
    ويُكمل. نسخة بلا صوت: --no-sound (تعيّن RAINDESK_NO_SOUND=1 للـ spec).
مثال: python tools/package.py            # بناء كامل
       python tools/package.py --skip-build   # التراخيص وZIP فقط على dist الموجود
"""

from __future__ import annotations

import argparse
import hashlib
import importlib.metadata as metadata
import os
import shutil
import subprocess
import sys
import zipfile
from collections.abc import Sequence
from pathlib import Path
from typing import Final

_ROOT: Final[Path] = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(_ROOT))

from raindesk.core.constants import APP_NAME, APP_VERSION  # noqa: E402

LICENSE_PACKAGES: Final[tuple[str, ...]] = ("numpy", "PySide6", "shiboken6", "pyinstaller")
_LICENSE_PREFIXES: Final[tuple[str, ...]] = ("LICENSE", "LICENCE", "COPYING", "NOTICE")
_PSF_NAME: Final[str] = "PSF-LICENSE.txt"
_NOTICES_NAME: Final[str] = "THIRD_PARTY_NOTICES.md"
_EXIT_OK: Final[int] = 0
_EXIT_ERROR: Final[int] = 1


def collect_licenses(
    out_dir: Path,
    packages: Sequence[str] = LICENSE_PACKAGES,
    python_prefix: Path | None = None,
    notices: Path = _ROOT / _NOTICES_NAME,
) -> list[Path]:
    """ينسخ ملفات التراخيص إلى out_dir ويعيد قائمة ما نُسخ فعلًا (ما لم يوجد يُتخطّى).

    يبحث في ملفات توزيعة كل حزمة (dist-info) عن أسماء تبدأ بـ LICENSE/COPYING/NOTICE، وينسخ
    رخصة Python (PSF) من بادئة المفسّر، ونص THIRD_PARTY_NOTICES.md.
    """
    copied: list[Path] = []
    out_dir.mkdir(parents=True, exist_ok=True)
    for package in packages:
        try:
            dist = metadata.distribution(package)
        except metadata.PackageNotFoundError:
            continue
        for entry in dist.files or []:
            if not entry.name.upper().startswith(_LICENSE_PREFIXES):
                continue
            source = Path(str(dist.locate_file(entry)))
            if not source.is_file():
                continue
            target = out_dir / package / source.name
            if target.exists():  # أسماء متشابهة داخل الحزمة: نحتفظ بالأولى فقط
                target = out_dir / package / f"{entry.parent.name}-{source.name}"
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(source, target)
            copied.append(target)
    prefix = python_prefix or Path(sys.base_prefix)
    for candidate in (prefix / "LICENSE.txt", prefix / "LICENSE"):
        if candidate.is_file():
            shutil.copyfile(candidate, out_dir / _PSF_NAME)
            copied.append(out_dir / _PSF_NAME)
            break
    if notices.is_file():
        shutil.copyfile(notices, out_dir / _NOTICES_NAME)
        copied.append(out_dir / _NOTICES_NAME)
    return copied


def has_lgpl_text(licenses_dir: Path) -> bool:
    """True إن وُجد داخل مجلد التراخيص ملف يبدو نص LGPL (شرط توزيع Qt)."""
    for path in licenses_dir.rglob("*"):
        if path.is_file() and "lgpl" in path.name.lower():
            return True
    return False


def make_zip(dist_dir: Path, zip_path: Path) -> str:
    """يضغط محتوى dist_dir (المجلد نفسه جذر الأرشيف) ويعيد بصمة SHA-256 للأرشيف."""
    zip_path.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as archive:
        for path in sorted(dist_dir.rglob("*")):
            if path.is_file():
                archive.write(path, Path(dist_dir.name) / path.relative_to(dist_dir))
    digest = hashlib.sha256()
    with zip_path.open("rb") as handle:
        for block in iter(lambda: handle.read(1 << 20), b""):
            digest.update(block)
    return digest.hexdigest()


def _run(command: list[str], env: dict[str, str] | None = None) -> None:
    print("+", " ".join(command))
    subprocess.run(command, cwd=_ROOT, env=env, check=True)


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Build the RainDesk distribution.")
    parser.add_argument("--skip-build", action="store_true", help="reuse the existing dist folder")
    parser.add_argument("--no-sound", action="store_true", help="build without QtMultimedia")
    parser.add_argument("--dist-dir", type=Path, default=_ROOT / "dist")
    parser.add_argument("--work-dir", type=Path, default=_ROOT / "build")
    args = parser.parse_args(argv)

    app_dir = args.dist_dir / APP_NAME
    try:
        if not args.skip_build:
            if not (_ROOT / "assets" / "raindesk.ico").exists():
                _run([sys.executable, "tools/make_icon.py"])
            env = dict(os.environ)
            if args.no_sound:
                env["RAINDESK_NO_SOUND"] = "1"
            _run(
                [
                    sys.executable,
                    "-m",
                    "PyInstaller",
                    "raindesk.spec",
                    "--noconfirm",
                    "--clean",
                    "--distpath",
                    str(args.dist_dir),
                    "--workpath",
                    str(args.work_dir),
                ],
                env,
            )
        if not app_dir.is_dir():
            print(f"missing build output: {app_dir}")
            return _EXIT_ERROR
        copied = collect_licenses(app_dir / "licenses")
        print(f"license files copied: {len(copied)}")
        if not has_lgpl_text(app_dir / "licenses"):
            print(
                "WARNING: no LGPL text found; add lgpl-3.0.txt / gpl-3.0.txt (see THIRD_PARTY_NOTICES.md)"
            )
        suffix = "-nosound" if args.no_sound else ""
        zip_path = args.dist_dir / f"{APP_NAME}-{APP_VERSION}-win64{suffix}.zip"
        print(f"{zip_path.name}  SHA256 {make_zip(app_dir, zip_path)}")
    except subprocess.CalledProcessError as exc:
        print(f"build step failed: {exc}")
        return _EXIT_ERROR
    return _EXIT_OK


if __name__ == "__main__":
    raise SystemExit(main())
