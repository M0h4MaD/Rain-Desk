"""raindesk/ui/widgets/labeled_slider.py

الغرض: منزلق برقم حي: اسم الإعداد وشريط وقيمة بوحدتها.
المسؤوليات: تحويل المجال العشري إلى خطوات صحيحة، وتحديد الإصدار (throttle) بـ 30 ms،
    وإعادة الضبط بالنقر المزدوج، وتلميحات وأسماء وصول مترجمة.
الاعتماديات: PySide6 وraindesk.i18n.translator.
النمط التصميمي: Adapter بين QSlider الصحيح والقيم العشرية، مع Throttle بالمؤقّت.
ملاحظات: الأرقام غربية (0-9) في اللغتين (قرار موثّق). اتجاه المنزلق في RTL يتبع Qt (يُعكس
    فيكون الحد الأدنى على اليمين)؛ وهو سلوك موحّد في كل المنزلقات. الأسهم وPageUp/PageDown تعمل
    تلقائيًا في QSlider. اصطلاح التلميح: مفتاح 'X.label' له 'X.tip'.
مثال: LabeledSlider('intensity', 'setting.intensity.label', 0, 1, 0.01, 0.5, '', 2, translator)
"""

from __future__ import annotations

from typing import Final

from PySide6.QtCore import QEvent, QObject, Qt, QTimer, Signal
from PySide6.QtWidgets import QHBoxLayout, QLabel, QSlider, QWidget

from raindesk.i18n.translator import Translator

_THROTTLE_MS: Final[int] = 30  # ms: أقل فاصل بين إصدارين متتاليين
_LABEL_MIN_WIDTH_PX: Final[int] = 160
_VALUE_MIN_WIDTH_PX: Final[int] = 72
_SPACING_PX: Final[int] = 12
_PAGE_STEP_FRACTION: Final[int] = 10  # PageUp/Down يحرّك عُشر المجال
_ROUND_DIGITS: Final[int] = 6  # يزيل ضجيج الفاصلة العائمة (0.1 + 0.2) من القيم المخزّنة
_LABEL_SUFFIX: Final[str] = ".label"
_TIP_SUFFIX: Final[str] = ".tip"


class LabeledSlider(QWidget):
    """منزلق بقيمة عشرية؛ value_changed(float) يصدر من تفاعل المستخدم فقط ما لم يُطلب غير ذلك."""

    value_changed = Signal(float)

    def __init__(
        self,
        key: str,
        label_key: str,
        minimum: float,
        maximum: float,
        step: float,
        default: float,
        unit: str,
        decimals: int,
        translator: Translator,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        if maximum <= minimum or step <= 0:
            raise ValueError("invalid slider range")
        self._key = key
        self._label_key = label_key
        self._minimum = minimum
        self._maximum = maximum
        self._step = step
        self._default = default
        self._unit = unit
        self._decimals = decimals
        self._translator = translator
        self._steps = max(1, round((maximum - minimum) / step))
        self._pending: float | None = None

        self._label = QLabel()
        self._label.setMinimumWidth(_LABEL_MIN_WIDTH_PX)
        self._slider = QSlider(Qt.Orientation.Horizontal)
        self._slider.setRange(0, self._steps)
        self._slider.setSingleStep(1)
        self._slider.setPageStep(max(1, self._steps // _PAGE_STEP_FRACTION))
        self._slider.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self._slider.installEventFilter(self)  # لالتقاط النقر المزدوج
        self._value_label = QLabel()
        self._value_label.setMinimumWidth(_VALUE_MIN_WIDTH_PX)
        self._value_label.setAlignment(Qt.AlignmentFlag.AlignCenter)

        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(_SPACING_PX)
        layout.addWidget(self._label)
        layout.addWidget(self._slider, 1)
        layout.addWidget(self._value_label)

        self._throttle = QTimer(self)
        self._throttle.setSingleShot(True)
        self._throttle.setInterval(_THROTTLE_MS)
        self._throttle.timeout.connect(self._on_throttle_timeout)
        self._slider.valueChanged.connect(self._on_slider_changed)

        self.set_value(default, emit=False)
        self.retranslate()

    # ------------------------------------------------------------------ التحويل
    def _raw_from_value(self, value: float) -> int:
        raw = round((value - self._minimum) / self._step)
        return min(max(raw, 0), self._steps)

    def _value_from_raw(self, raw: int) -> float:
        return round(min(self._minimum + raw * self._step, self._maximum), _ROUND_DIGITS)

    def _format(self, value: float) -> str:
        return f"{value:.{self._decimals}f}{self._unit}"

    # ------------------------------------------------------------------ الواجهة العامة
    def value(self) -> float:
        """القيمة الحالية (مُقرَّبة إلى شبكة الخطوات)."""
        return self._value_from_raw(self._slider.value())

    def set_value(self, value: float, emit: bool = False) -> None:
        """يضبط القيمة (تُقصّ وتُقرَّب إلى الشبكة)؛ emit=True يصدر value_changed فورًا."""
        raw = self._raw_from_value(value)
        self._slider.blockSignals(True)
        self._slider.setValue(raw)
        self._slider.blockSignals(False)
        snapped = self._value_from_raw(raw)
        self._value_label.setText(self._format(snapped))
        if emit:
            self._pending = None
            self.value_changed.emit(snapped)

    def retranslate(self) -> None:
        """يحدّث الاسم والتلميح واسم الوصول (accessibility) حسب اللغة الحالية."""
        text = self._translator.tr(self._label_key)
        self._label.setText(text)
        self._slider.setAccessibleName(text)
        tip_key = self._label_key.removesuffix(_LABEL_SUFFIX) + _TIP_SUFFIX
        tip = self._translator.tr(tip_key)
        self.setToolTip("" if tip == tip_key else tip)

    # ------------------------------------------------------------------ الإصدار المحدَّد
    def _on_slider_changed(self, raw: int) -> None:
        value = self._value_from_raw(raw)
        self._value_label.setText(self._format(value))  # الرقم الظاهر فوري دائمًا
        self._pending = value
        if not self._throttle.isActive():
            self._flush()  # الحافة الأولى تُصدَر فورًا ثم تُجمَّع التغييرات اللاحقة
            self._throttle.start()

    def _flush(self) -> None:
        if self._pending is not None:
            value, self._pending = self._pending, None
            self.value_changed.emit(value)

    def _on_throttle_timeout(self) -> None:
        if self._pending is not None:
            self._flush()
            self._throttle.start()

    # ------------------------------------------------------------------ إعادة الضبط
    def eventFilter(self, watched: QObject, event: QEvent) -> bool:  # noqa: N802
        if watched is self._slider and event.type() == QEvent.Type.MouseButtonDblClick:
            self.set_value(self._default, emit=True)
            return True
        return super().eventFilter(watched, event)