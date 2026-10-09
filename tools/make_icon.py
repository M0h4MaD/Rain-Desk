"""tools/make_icon.py

الغرض: يولّد assets/raindesk.ico (أيقونة التطبيق ومجلد البناء) من رسم Drip نفسه بلا أي ملف صور.
المسؤوليات: رسم Drip بـ Qt على لوحة شفافة لكل حجم (16 حتى 256) باستعمال نفس مرسِم الشخصية
    في التطبيق (mascot_painter) فتتطابق هوية الأيقونة مع الشخصية، ثم تجميع الأحجام في ملف
    ICO واحد بواسطة Pillow. أداة وقت التطوير فقط: لا يستورده التطبيق ولا يُشحن Pillow معه.
الاعتماديات: PySide6 (منصة offscreen فلا تظهر نافذة) وPillow وraindesk.engine/ui.painters.
النمط التصميمي: Script ذو دالة نقية build_icon قابلة للاختبار (تعيد المسار والأحجام).
ملاحظات: كل حجم يُرسم بدقته الأصلية (لا تصغير من 256) فتبقى الأيقونات الصغيرة حادة؛ Pillow
    يضع الإطارات المرسومة كما هي إن طابق حجمها حجمًا مطلوبًا (append_images). الأيقونة تظهر
    في مستكشف الملفات وشريط المهام ونافذة Alt+Tab (التطبيق نفسه يرسم أيقونة الصينية بالكود).
مثال: python tools/make_icon.py            # يكتب assets/raindesk.ico
       python tools/make_icon.py --check   # يتحقق من الملف الحالي ويطبع أحجامه
"""

from __future__ import annotations

import argparse
import os
import random
import sys
from collections.abc import Sequence
from pathlib import Path
from typing import Final

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")  # قبل استيراد Qt: بلا نافذة ولا DPI
_ROOT: Final[Path] = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(_ROOT))

from PIL import Image  # noqa: E402
from PySide6.QtGui import QColor, QGuiApplication, QImage, QPainter  # noqa: E402

from raindesk.engine.mascot import Expression, Mascot, MascotState  # noqa: E402
from raindesk.ui.painters.mascot_painter import paint_mascot  # noqa: E402

ICON_SIZES: Final[tuple[int, ...]] = (16, 24, 32, 48, 64, 128, 256)  # أحجام Windows المعتادة
DEFAULT_OUTPUT: Final[Path] = _ROOT / "assets" / "raindesk.ico"
_BODY_FRACTION: Final[float] = 0.80  # ارتفاع الجسم نسبة إلى حجم الأيقونة
_GROUND_FRACTION: Final[float] = 0.92  # موضع القدمين (يترك مكانًا للظل)
_SMILE_OPEN: Final[float] = 0.25  # فم مبتسم قليلًا
_EXIT_OK: Final[int] = 0
_EXIT_ERROR: Final[int] = 1


def render_frame(size: int) -> QImage:
    """يرسم Drip واقفًا مبتسمًا على لوحة شفافة بحجم size x size بكسل (RGBA غير مسبق الضرب)."""
    mascot = Mascot(random.Random(1))
    mascot.configure(True, 0.0, 1.0)
    ground = size * _GROUND_FRACTION
    mascot.set_stage(0.0, float(size), ground)
    mascot.state, mascot.x, mascot.y = MascotState.IDLE, size / 2.0, ground
    mascot.expression, mascot.mouth_open = Expression.HAPPY, _SMILE_OPEN
    image = QImage(size, size, QImage.Format.Format_ARGB32_Premultiplied)
    image.fill(QColor(0, 0, 0, 0))
    painter = QPainter(image)
    try:
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        paint_mascot(painter, mascot, size * _BODY_FRACTION)
    finally:
        painter.end()
    return image.convertToFormat(QImage.Format.Format_RGBA8888)


def _to_pillow(image: QImage) -> Image.Image:
    width, height = image.width(), image.height()
    return Image.frombytes("RGBA", (width, height), bytes(image.constBits())[: width * height * 4])


def build_icon(
    output: Path = DEFAULT_OUTPUT, sizes: Sequence[int] = ICON_SIZES
) -> tuple[Path, list[int]]:
    """يبني ملف ICO متعدد الأحجام ويعيد (المسار، الأحجام المكتوبة فعلًا).

    Raises:
        ValueError: إن لم تُعطَ أحجام أو تجاوز أحدها 256 (حد صيغة ICO).
    """
    ordered = sorted(set(sizes))
    if not ordered or ordered[-1] > 256 or ordered[0] < 1:
        raise ValueError("icon sizes must be between 1 and 256")
    app = QGuiApplication.instance() or QGuiApplication([sys.argv[0] if sys.argv else "make_icon"])
    frames = {size: _to_pillow(render_frame(size)) for size in ordered}
    largest = frames[ordered[-1]]  # Pillow يشترط أن يكون الإطار الأول هو الأكبر
    output.parent.mkdir(parents=True, exist_ok=True)
    largest.save(
        output,
        format="ICO",
        sizes=[(size, size) for size in ordered],
        append_images=[frames[size] for size in ordered[:-1]],
    )
    del app
    return output, read_sizes(output)


def read_sizes(path: Path) -> list[int]:
    """أحجام الإطارات (العرض) الموجودة فعلًا في ملف ICO."""
    with Image.open(path) as icon:
        return sorted({width for width, _ in icon.info.get("sizes", set())})


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Generate assets/raindesk.ico from Drip.")
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--check", action="store_true", help="only verify an existing icon")
    args = parser.parse_args(argv)
    if args.check:
        if not args.output.exists():
            print(f"missing: {args.output}")
            return _EXIT_ERROR
        sizes = read_sizes(args.output)
    else:
        _, sizes = build_icon(args.output)
    print(f"{args.output}: sizes {sizes}")
    return _EXIT_OK if sizes == list(ICON_SIZES) else _EXIT_ERROR


if __name__ == "__main__":
    raise SystemExit(main())
