"""raindesk/engine/mascot_tuning.py

الغرض: مقابض ضبط شخصية Drip في مكان واحد: مدد السلوكات وأوزان اختيارها وأزمنة التبريد وسرعات
    المطاردة والمسح والتمسيح. تعديل رقم هنا يغيّر طباع Drip دون لمس المنطق.
المسؤوليات: ثوابت فقط (لا دوال ولا حالة)، كلها Final وبوحدات موثقة في التعليق.
الاعتماديات: المكتبة القياسية فقط.
النمط التصميمي: Configuration Module (ثوابت مسماة بدل الأرقام السحرية).
ملاحظات: مجموع أوزان BEHAVIOURS = 1.0 (يُطبَّع تلقائيًا في random.choices على أي حال). أمثلة:
    ارفع الوزن "dance" ليرقص أكثر، أو قلّل COOLDOWN_CURIOUS_S ليسلّم عليك أكثر.
مثال: from raindesk.engine import mascot_tuning as tune; tune.BEHAVIOURS
"""

from __future__ import annotations

from typing import Final

DURATIONS: Final[dict[str, tuple[float, float]]] = {  # s: مدد السلوكات المؤقتة
    "idle": (1.5, 4.0),
    "look_up": (1.5, 3.0),
    "shake": (0.6, 1.0),
    "dance": (3.0, 5.0),
    "sleep": (4.0, 8.0),
    "wave": (1.6, 2.4),
    "spin": (0.8, 0.8),
    "shiver": (1.2, 2.0),
}
WALK_DISTANCE_PX: Final[tuple[float, float]] = (80.0, 400.0)
BEHAVIOURS: Final[tuple[tuple[str, float], ...]] = (  # السلوك العشوائي التالي ووزنه
    ("walk", 0.22),
    ("idle", 0.14),
    ("look_up", 0.12),
    ("jump", 0.12),
    ("shake", 0.08),
    ("dance", 0.08),
    ("sleep", 0.07),
    ("wave", 0.05),
    ("spin", 0.05),
    ("hops", 0.07),
)
SHIVER_RAIN_FROM: Final[float] = 0.6  # شدة مطر يبدأ عندها الارتجاف العشوائي
SHIVER_MAX_WEIGHT: Final[float] = 0.12
HOP_VX_PX_S: Final[float] = 60.0  # px/s: سرعة أفقية صغيرة في القفزة الكبيرة
STARTLE_VX_PX_S: Final[float] = 130.0  # px/s: يقفز مبتعدًا عن مصدر الفزع
HOP_CROUCH_S: Final[float] = 0.07  # s: تهيؤ النطة الصغيرة
FROLIC_HOPS: Final[int] = 2  # عدد نطات الفرح بعد التمسيح أو الوصول للمؤشر
CURIOUS_SPEED_FACTOR: Final[float] = 0.8  # يقترب أبطأ من المشي العادي
CURIOUS_MAX_S: Final[float] = 6.0
WAVE_DISTANCE_PX: Final[float] = 70.0  # px: يلوّح حين يصل لهذا القرب من المؤشر
PLAY_WINDOW_S: Final[float] = 8.0  # s: بعد التلويح يقبل أي دعوة لعب
CHASE_SPEED_PX_S: Final[tuple[float, float]] = (190.0, 250.0)
CHASE_MAX_S: Final[float] = 8.0
CHASE_CATCH_PX: Final[float] = 40.0  # px: "أمسك" المؤشر
CHASE_CATCH_S: Final[float] = 0.4  # s: بقاؤه قريبًا قبل نطات الفرح
CHASE_CHANCE: Final[float] = 0.5  # احتمال قبول دعوة اللعب خارج نافذة اللعب
COOLDOWN_CHASE_S: Final[float] = 12.0
COOLDOWN_DECLINED_S: Final[float] = 4.0
COOLDOWN_CURIOUS_S: Final[float] = 25.0
COOLDOWN_STARTLE_S: Final[float] = 8.0
COOLDOWN_LIGHTNING_S: Final[float] = 3.0
PET_MIN_S: Final[float] = 2.0  # s: أقل مدة للتمسيح
PET_HOLD_S: Final[float] = 1.2  # s: يمدّد المسح المستمر التمسيح بهذا القدر
PET_MAX_S: Final[float] = 8.0
PET_KEEP_SPEED_PX_S: Final[float] = 25.0  # px/s: يعدّ المؤشر ما زال يمسّح
BOB_PX: Final[float] = 2.5  # px: ارتداد الخطوة عند scale = 1
