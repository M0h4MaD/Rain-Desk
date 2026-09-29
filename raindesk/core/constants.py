"""raindesk/core/constants.py

الغرض: مصدر واحد لكل الثوابت المسماة (لا أرقام سحرية في بقية الملفات).
المسؤوليات: ثوابت التطبيق والمحاكاة والأداء والصوت، مع الوحدة والمبرر لكل ثابت.
الاعتماديات: المكتبة القياسية فقط ('typing.Final').
النمط التصميمي: Constants Module (وحدة ثوابت بلا حالة ولا سلوك).
ملاحظات: الإحداثيات بوحدة logical pixels، والأزمنة بالثواني إلا ما ينتهي بـ '_MS'.
مثال: from raindesk.core.constants import DT_MAX_S
"""

from __future__ import annotations

from typing import Final

# ---------------------------------------------------------------------------
# هوية التطبيق
# ---------------------------------------------------------------------------
APP_NAME: Final[str] = "RainDesk"  # الاسم الظاهر واسم مجلدات البيانات
APP_VERSION: Final[str] = "1.0.0"  # إصدار دلالي (SemVer)
IPC_SERVER_NAME: Final[str] = "RainDesk.SingleInstance.v1"  # اسم QLocalServer لمنع تعدد النسخ

# مفتاح التشغيل التلقائي؛ يُكتب تحت HKEY_CURRENT_USER فقط (بلا صلاحيات مدير).
RUN_KEY_PATH: Final[str] = r"Software\Microsoft\Windows\CurrentVersion\Run"
RUN_VALUE_NAME: Final[str] = "RainDesk"  # اسم القيمة داخل مفتاح Run
SETTINGS_FILENAME: Final[str] = "settings.json"  # ملف الإعدادات داخل %APPDATA%/RainDesk

# ---------------------------------------------------------------------------
# الزمن والتنعيم
# ---------------------------------------------------------------------------
# سقف dt بالثواني (يعادل حدًا أدنى 20 fps): يمنع قفز القطرات بعد السكون أو التوقف عند
# debugger أو سحب نافذة. مقبول هنا لأن الديناميكيا غير قاسية ولا نحتاج حتمية بين الأجهزة.
DT_MAX_S: Final[float] = 0.05
# ثابت الزمن tau بالثواني في alpha = 1 - exp(-dt / tau)؛ بعد 3*tau (0.75 s) نقطع نحو 95%.
SMOOTHING_TAU_S: Final[float] = 0.25

# ---------------------------------------------------------------------------
# نموذج القطرة (خطوط المطر)
# ---------------------------------------------------------------------------
BASE_FALL_SPEED_PX_S: Final[float] = 1400.0  # px/s: سرعة السقوط عند speed=1 لأقرب طبقة
# زمن التعريض (exposure) بالثواني: طول الخط = السرعة * الزمن (1400 * 0.030 = 42 px)،
# على غرار تمويه الحركة في الكاميرا: الأسرع يترك خطًا أطول تلقائيًا.
EXPOSURE_TIME_S: Final[float] = 0.030
BASE_LINE_WIDTH_PX: Final[float] = 1.4  # px: سُمك القلم لأقرب طبقة عند thickness=1

# معاملات الإخفاء بالعمق z (0 بعيد .. 1 قريب): f(z) = lerp(1 - p*A, 1, z) حيث p = parallax.
DEPTH_SPEED_ATTENUATION: Final[float] = 0.55  # A للسرعة: أقصى نقص نسبي للبعيد
DEPTH_THICKNESS_ATTENUATION: Final[float] = 0.60  # A للسُمك
DEPTH_ALPHA_ATTENUATION: Final[float] = 0.70  # A للشفافية
# z = u ** DEPTH_BIAS_EXPONENT مع u منتظم في [0, 1]: أُس أكبر من 1 يكثّف القطرات البعيدة.
DEPTH_BIAS_EXPONENT: Final[float] = 1.6

# ---------------------------------------------------------------------------
# الكثافة والرياح
# ---------------------------------------------------------------------------
# سعة مصفوفات SoA لكل شاشة. شاشة 4K (8.29 MP) بأقصى كثافة: 8.29 * 600 = نحو 4977 قطرة.
MAX_DROPS_PER_SCREEN: Final[int] = 5000
DROPS_PER_MEGAPIXEL_MIN: Final[float] = 30.0  # قطرة لكل MP عند intensity=0
DROPS_PER_MEGAPIXEL_MAX: Final[float] = 600.0  # قطرة لكل MP عند intensity=1
# density(i) = D_MIN + (D_MAX - D_MIN) * i ** 1.5: منحنى محدب يعطي دقة أكبر عند الشدة المنخفضة.
INTENSITY_CURVE_EXPONENT: Final[float] = 1.5

MAX_WIND_ANGLE_DEG: Final[float] = 75.0  # درجة: أقصى ميل فعلي (يمنع tan من الانفجار قرب 90)
GUST_MAX_DEG: Final[float] = 25.0  # درجة: أقصى انحراف من العصف عند wind_gusts=1
SPAWN_MARGIN_TOP_FRACTION: Final[float] = 0.25  # نسبة من الارتفاع H: هامش الولادة فوق الشاشة
DROP_JITTER: Final[float] = 0.06  # عامل سرعة عشوائي ثابت لكل قطرة في [1 - 0.06, 1 + 0.06]

# ---------------------------------------------------------------------------
# الرذاذ والفيزياء
# ---------------------------------------------------------------------------
SPLASH_POOL_CAPACITY: Final[int] = 600  # سعة ring buffer للرذاذ (يُستبدل الأقدم عند الامتلاء)
GRAVITY_PX_S2: Final[float] = 1800.0  # px/s^2: جاذبية شاشة للرذاذ وقفزات Drip

# ---------------------------------------------------------------------------
# المؤقتات
# ---------------------------------------------------------------------------
SETTINGS_SAVE_DEBOUNCE_MS: Final[int] = 400  # ms: دمج تغييرات المنزلق في كتابة واحدة
SYSTEM_WATCH_INTERVAL_MS: Final[int] = 2000  # ms: دورية فحص ملء الشاشة وقفل الجلسة
TOPMOST_WATCHDOG_INTERVAL_MS: Final[int] = 10000  # ms: إعادة تثبيت النافذة فوق الأخرى

# ---------------------------------------------------------------------------
# الجودة التكيفية (فجوة العتبات + اختلاف العدّادات = hysteresis يمنع التذبذب)
# ---------------------------------------------------------------------------
ADAPTIVE_DOWN_FRAMES: Final[int] = 60  # إطار متتالٍ قبل التخفيض (نحو ثانية عند 60 fps)
ADAPTIVE_UP_FRAMES: Final[int] = 300  # إطار متتالٍ قبل الاستعادة (نحو 5 ثوانٍ): أبطأ عمدًا
ADAPTIVE_MIN_SCALE: Final[float] = 0.5  # أدنى معامل لعدد القطرات

# ---------------------------------------------------------------------------
# الصوت
# ---------------------------------------------------------------------------
AUDIO_SAMPLE_RATE: Final[int] = 44100  # Hz: الافتراضي (يُستبدل بمعدل الجهاز عند رفضه)
# طول حلقة الضجيج بالثواني. الذاكرة: 8 * 44100 * 2 قناة * 4 بايت = 2.8 MB للحلقة (8.5 MB لثلاث).
AUDIO_LOOP_SECONDS: Final[float] = 8.0
AUDIO_BLOCK_MS: Final[int] = 20  # ms: طول كتلة التوليد ودورية المؤقت
AUDIO_BUFFER_MS: Final[int] = 100  # ms: حجم مخزن QAudioSink (5 كتل تحميك من underrun)
AUDIO_FADE_MS: Final[int] = 250  # ms: مدة fade-in/out (منحدر خطي لا خطوة، لتفادي النقر)
AUDIO_IDLE_RELEASE_S: Final[float] = 2.0  # ثانية صمت قبل تحرير جهاز الصوت
AUDIO_DROPLET_BANK_SIZE: Final[int] = 64  # عدد نبضات القطرات المولّدة مسبقًا
AUDIO_MAX_DROPLETS_PER_S: Final[float] = 220.0  # أقصى معدل وصول Poisson عند intensity=1