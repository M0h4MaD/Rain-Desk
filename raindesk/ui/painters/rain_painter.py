"""raindesk/ui/painters/rain_painter.py

الغرض: رسم خطوط المطر على QPainter بدفعات: قلم واحد وطلب drawLines واحد لكل طبقة عمق.
المسؤوليات: اشتقاق سُمك وشفافية كل طبقة من عمقها الأوسط، وتحويل مصفوفات NumPy إلى QLineF.
الاعتماديات: PySide6 (QtCore وQtGui) وraindesk.engine وraindesk.core.constants.
النمط التصميمي: Batching (تقليل تبديل حالة الرسم). انظر قرار التصميم DD-05.
ملاحظات: مقدّم التلميح Antialiasing يضبطه المستدعي (OverlayWindow) حسب الإعدادات.
مثال: paint_rain(painter, field, params)
"""

from __future__ import annotations

from typing import Final

from PySide6.QtCore import QLineF, Qt
from PySide6.QtGui import QColor, QPainter, QPen

from raindesk.core.constants import (
    BASE_LINE_WIDTH_PX,
    DEPTH_ALPHA_ATTENUATION,
    DEPTH_THICKNESS_ATTENUATION,
)
from raindesk.engine.math_utils import clamp, lerp
from raindesk.engine.params import EngineParams
from raindesk.engine.rain_field import RainField

_MIN_PEN_WIDTH_PX: Final[float] = 0.3  # px: أقل سُمك مرئي (يمنع اختفاء الخطوط عند thickness صغير)


def paint_rain(painter: QPainter, field: RainField, params: EngineParams) -> None:
    """يرسم كل طبقات المطر من البعيد إلى القريب.

    لكل طبقة k من L طبقة: z_mid = (k + 0.5) / L، والسُمك = BASE * thickness * f_thick(z_mid)،
    والشفافية = opacity * f_alpha(z_mid)، حيث f(z) = lerp(1 - p * A, 1, z) وp = parallax.
    نختار قلمًا واحدًا لكل طبقة بدل قلم لكل قطرة، فنخفّض تبديلات الحالة إلى L بدل N
    (على حساب تكميم العمق إلى L درجات؛ انظر DD-05). التعقيد O(N) لبناء QLineF.
    """
    layers = field.layer_lines(params.depth_layers)
    layer_count = len(layers)
    red, green, blue = params.color_rgb
    color = QColor(red, green, blue)
    for index, lines in enumerate(layers):
        if lines.shape[0] == 0:
            continue
        z_mid = (index + 0.5) / layer_count
        width = (
            BASE_LINE_WIDTH_PX
            * params.drop_thickness
            * lerp(1.0 - params.parallax * DEPTH_THICKNESS_ATTENUATION, 1.0, z_mid)
        )
        alpha = params.drop_opacity * lerp(
            1.0 - params.parallax * DEPTH_ALPHA_ATTENUATION, 1.0, z_mid
        )
        color.setAlphaF(clamp(alpha, 0.0, 1.0))
        painter.setPen(
            QPen(
                color,
                max(width, _MIN_PEN_WIDTH_PX),
                Qt.PenStyle.SolidLine,
                Qt.PenCapStyle.RoundCap,  # أطراف مستديرة تعطي مظهر قطرة لا مستطيل
            )
        )
        # tolist() يحوّل المصفوفة دفعة واحدة إلى أعداد بايثون، وهو أسرع من فهرسة NumPy لكل عنصر.
        painter.drawLines([QLineF(x1, y1, x2, y2) for x1, y1, x2, y2 in lines.tolist()])