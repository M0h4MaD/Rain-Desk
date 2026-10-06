"""raindesk/i18n/strings_ar.py

الغرض: نصوص الواجهة بالعربية (فصحى مبسّطة). المفاتيح والمتغيرات {placeholders} مطابقة
    تمامًا لـ strings_en.py. اسم المنتج RainDesk يبقى بالأحرف اللاتينية، والأرقام غربية (0-9).
"""

from __future__ import annotations

from typing import Final

STRINGS: Final[dict[str, str]] = {
    # --- عام ---
    "app.name": "RainDesk",
    "lang.auto": "تلقائي (لغة النظام)",
    "window.title": "إعدادات RainDesk",
    # --- رسائل ---
    "msg.settings_corrupt": (
        "ملف الإعدادات تالف، لذلك جرى تحميل الإعدادات الافتراضية. "
        "حُفظت نسخة منه باسم {name}."
    ),
    "msg.first_run_title": "مرحبًا بك في RainDesk",
    "msg.first_run_body": "يبقى RainDesk يعمل في شريط النظام. اضغط على أيقونته لفتح الإعدادات.",
    "msg.tray_unavailable": (
        "شريط النظام غير متاح، لذلك سيؤدي إغلاق هذه النافذة إلى إنهاء RainDesk."
    ),
    # --- التنقل ---
    "nav.general": "عام",
    "nav.rain": "المطر والرياح",
    # --- أزرار الواجهة ---
    "ui.randomize": "عشوائي",
    "ui.reset": "استعادة الإعدادات الافتراضية",
    "ui.saved": "تم الحفظ",
    "ui.reset_confirm.title": "استعادة الإعدادات الافتراضية",
    "ui.reset_confirm.body": "ستعود كل الإعدادات إلى قيمها الافتراضية. هل تريد المتابعة؟",
    "ui.confirm": "استعادة",
    "ui.cancel": "إلغاء",
    # --- شريط النظام ---
    "tray.open_settings": "فتح الإعدادات",
    "tray.enable": "إظهار المطر",
    "tray.randomize": "عشوائي",
    "tray.presets": "إعدادات مسبقة",
    "tray.quit": "خروج",
    "tray.tooltip_off": "RainDesk (متوقف)",
    # --- أسماء الإعدادات المسبقة والسمات ---
    "preset.custom": "مخصص",
    "preset.drizzle": "رذاذ",
    "preset.light": "مطر خفيف",
    "preset.moderate": "مطر متوسط",
    "preset.heavy": "مطر غزير",
    "preset.storm": "عاصفة",
    "theme.system": "النظام",
    "theme.light": "فاتح",
    "theme.dark": "داكن",
    # --- أداة اللون ---
    "color.pick_title": "اختر لونًا",
    "color.tip": "اضغط لاختيار لون",
    # --- الصفحة العامة ---
    "card.behavior.title": "السلوك",
    "card.behavior.desc": "تحكّم بوقت ظهور المطر وبطريقة بدء RainDesk.",
    "setting.enabled.label": "إظهار المطر",
    "setting.enabled.tip": "شغّل طبقة المطر أو أوقفها دون إغلاق RainDesk.",
    "setting.launch_at_login.label": "التشغيل مع ويندوز",
    "setting.launch_at_login.tip": "يبدأ RainDesk تلقائيًا عند تسجيل دخولك إلى ويندوز.",
    "setting.start_hidden_in_tray.label": "البدء مخفيًا في شريط النظام",
    "setting.start_hidden_in_tray.tip": (
        "عند إيقافه تُفتح نافذة الإعدادات في كل مرة يبدأ فيها RainDesk."
    ),
    "card.appearance.title": "المظهر",
    "card.appearance.desc": "لغة هذه النافذة وسمة ألوانها.",
    "setting.language.label": "اللغة",
    "setting.language.tip": "يبدّل لغة الواجهة واتجاه القراءة فورًا.",
    "setting.theme.label": "السمة",
    "setting.theme.tip": "اتبع سمة ويندوز، أو فرض نافذة فاتحة أو داكنة.",
    # --- صفحة المطر والرياح ---
    "card.preset.title": "الإعدادات المسبقة",
    "card.preset.desc": "ابدأ من طقس جاهز ثم اضبطه بدقة في الأسفل.",
    "setting.preset.label": "الطقس الجاهز",
    "setting.preset.tip": (
        "اختيار إعداد مسبق يضبط قيم المطر والرياح الأساسية. تحريك أي منزلق يحوّله إلى "
        "مخصص."
    ),
    "note.auto_weather": "الطقس التلقائي مفعّل، لذلك تُدار هذه العناصر تلقائيًا.",
    "card.drops.title": "القطرات",
    "card.drops.desc": "مظهر المطر.",
    "setting.intensity.label": "الشدة",
    "setting.intensity.tip": "عدد القطرات المتساقطة. تتكيف الكثافة مع حجم شاشتك.",
    "setting.speed.label": "السرعة",
    "setting.speed.tip": "سرعة سقوط القطرات.",
    "setting.drop_length.label": "طول القطرة",
    "setting.drop_length.tip": "طول كل خط. القطرات الأسرع تبدو أطول دائمًا.",
    "setting.drop_thickness.label": "السماكة",
    "setting.drop_thickness.tip": "عرض خط القطرة.",
    "setting.drop_opacity.label": "العتامة",
    "setting.drop_opacity.tip": "مدى وضوح القطرات. القيم الأقل تجعلها أكثر شفافية.",
    "setting.drop_color.label": "اللون",
    "setting.drop_color.tip": "اللون الأساسي للقطرات.",
    "setting.parallax_strength.label": "تأثير العمق",
    "setting.parallax_strength.tip": "مقدار صغر القطرات البعيدة وبطئها وخفوتها.",
    "card.wind.title": "الرياح",
    "card.wind.desc": "اتجاه الرياح وشدة هبّاتها.",
    "setting.wind_angle_deg.label": "زاوية الرياح",
    "setting.wind_angle_deg.tip": (
        "ميلان المطر المتساقط. القيمة السالبة تميل لليسار والموجبة لليمين."
    ),
    "setting.wind_gusts.label": "الهبّات",
    "setting.wind_gusts.tip": "مقدار تغيّر زاوية الرياح مع الزمن.",
    "setting.gust_period_s.label": "دورة الهبّات",
    "setting.gust_period_s.tip": "الزمن المعتاد بين هبّتين، بالثواني.",
    # --- التنقل (الصفحات الجديدة) ---
    "nav.effects": "المؤثرات",
    "nav.mascot": "الشخصية",
    "nav.display": "العرض والأداء",
    "nav.advanced": "متقدم",
    "nav.about": "حول",
    # --- صفحة المؤثرات ---
    "card.splashes.title": "الرذاذ",
    "card.splashes.desc": "تموّجات ورذاذ حيث تهبط القطرات.",
    "setting.splashes_enabled.label": "إظهار الرذاذ",
    "setting.splashes_enabled.tip": "يرسم تموّجات صغيرة ورذاذًا عند ارتطام القطرات بالأرض.",
    "setting.splash_amount.label": "كمية الرذاذ",
    "setting.splash_amount.tip": "عدد القطرات التي تُحدث رذاذًا.",
    "setting.splash_zone.label": "منطقة الهبوط",
    "setting.splash_zone.tip": (
        "حافة الشاشة السفلية: تهبط القطرات عند أسفل الشاشة. "
        "مستويات العمق: القطرات الأقرب تهبط في موضع أدنى."
    ),
    "splash_zone.bottom_edge": "حافة الشاشة السفلية",
    "splash_zone.depth_plane": "مستويات العمق",
    "card.streams.title": "جداول الحواف",
    "card.streams.desc": "ماء ينساب على الحافتين اليسرى واليمنى للشاشة.",
    "setting.edge_streams_enabled.label": "إظهار جداول الحواف",
    "setting.edge_streams_enabled.tip": "يرسم جداول ماء رفيعة على حافتي الشاشة.",
    "setting.edge_streams_count.label": "عدد الجداول لكل حافة",
    "setting.edge_streams_count.tip": "عدد الجداول المنسابة على كل حافة.",
    "setting.edge_streams_opacity.label": "عتامة الجداول",
    "setting.edge_streams_opacity.tip": "مدى وضوح الجداول.",
    "card.mood.title": "تظليل الأجواء",
    "card.mood.desc": "طبقة لونية ناعمة فوق الشاشة كلها.",
    "setting.mood_enabled.label": "إظهار تظليل الأجواء",
    "setting.mood_enabled.tip": "يظلّل الشاشة ليمنح المشهد إحساسًا كئيبًا أو هادئًا.",
    "setting.mood_color.label": "لون التظليل",
    "setting.mood_color.tip": "لون التظليل.",
    "setting.mood_opacity.label": "قوة التظليل",
    "setting.mood_opacity.tip": "مدى قوة التظليل. أبقِه منخفضًا ليبقى المحتوى مقروءًا.",
    "card.lightning.title": "البرق",
    "card.lightning.desc": "ومضات متفرقة في الطقس الغزير.",
    "setting.lightning_enabled.label": "إظهار البرق",
    "setting.lightning_enabled.tip": "ومضات ساطعة قصيرة. معطّل افتراضيًا.",
    "setting.lightning_frequency.label": "تكرار الومضات",
    "setting.lightning_frequency.tip": "عدد مرات ظهور البرق.",
    "note.lightning_warning": (
        "تحذير: البرق يُنتج ومضات ساطعة. لا تفعّله إن كنت حساسًا للضوء الوامض."
    ),
    "note.lightning_animations_off": "رسوم ويندوز المتحركة معطّلة، لذلك البرق غير متاح.",
    "card.weather.title": "الطقس التلقائي",
    "card.weather.desc": "دع الطقس يتبدل وحده بين الرذاذ والعاصفة.",
    "setting.auto_weather.label": "الطقس التلقائي",
    "setting.auto_weather.tip": "يتغير الطقس من تلقاء نفسه وتُدار عناصر المطر والرياح نيابةً عنك.",
    "setting.auto_weather_variability.label": "التنوّع",
    "setting.auto_weather_variability.tip": (
        "القيمة المنخفضة تُبقي الطقس مستقرًا، والعالية تغيّره أكثر وأوسع."
    ),
    # --- صفحة الشخصية ---
    "card.mascot.title": "الشخصية",
    "card.mascot.desc": "Drip قطرة صغيرة تعبر شاشتك بين حين وآخر.",
    "setting.mascot_enabled.label": "إظهار Drip",
    "setting.mascot_enabled.tip": "اسمح لـ Drip بالظهور. عند الإيقاف لا تكلّف شيئًا.",
    "setting.mascot_frequency.label": "تكرار الظهور",
    "setting.mascot_frequency.tip": "عدد مرات ظهور Drip.",
    "setting.mascot_scale.label": "الحجم",
    "setting.mascot_scale.tip": "حجم Drip على الشاشة.",
    # --- صفحة العرض والأداء ---
    "card.screens.title": "الشاشات",
    "card.screens.desc": "اختر أين يهطل المطر.",
    "setting.screens_mode.label": "إظهار المطر على",
    "setting.screens_mode.tip": "كل الشاشات، أو الأساسية فقط، أو شاشات تختارها في الأسفل.",
    "screens_mode.all": "كل الشاشات",
    "screens_mode.primary": "الشاشة الأساسية فقط",
    "screens_mode.selected": "شاشات أختارها",
    "setting.selected_screens.label": "اختر الشاشات",
    "setting.selected_screens.tip": "علّم الشاشات التي يجب أن يظهر عليها المطر.",
    "display.primary_badge": "أساسية",
    "setting.cover_taskbar.label": "تغطية شريط المهام",
    "setting.cover_taskbar.tip": (
        "عند الإيقاف يبقى المطر فوق شريط المهام، وعند التفعيل يغطي الشاشة كلها."
    ),
    "card.performance.title": "الأداء",
    "card.performance.desc": "وازن بين النعومة وبين البطارية ووقت المعالج.",
    "setting.quality.label": "الجودة",
    "setting.quality.tip": "ملف جاهز يضبط معدل الإطارات والتنعيم معًا.",
    "quality.low": "منخفضة (توفّر الطاقة)",
    "quality.balanced": "متوازنة",
    "quality.high": "عالية (الأنعم)",
    "setting.fps_cap.label": "حد معدل الإطارات",
    "setting.fps_cap.tip": "أقصى عدد إطارات في الثانية. القيم الأقل تستهلك وقت معالج أقل.",
    "setting.antialiasing.label": "تنعيم الحواف",
    "setting.antialiasing.tip": "يجعل القطرات أنعم مظهرًا لكنه يكلّف بعض الأداء.",
    "card.pause.title": "الإيقاف المؤقت واللقطات",
    "card.pause.desc": "متى ينسحب RainDesk من الواجهة.",
    "setting.pause_on_fullscreen.label": "الإيقاف أثناء التطبيقات بملء الشاشة",
    "setting.pause_on_fullscreen.tip": "يخفي المطر أثناء لعبة أو فيديو بملء الشاشة.",
    "setting.pause_on_battery_saver.label": "الإيقاف في وضع توفير البطارية",
    "setting.pause_on_battery_saver.tip": "يخفي المطر أثناء تفعيل توفير البطارية في ويندوز.",
    "setting.exclude_from_capture.label": "إخفاؤه من لقطات الشاشة (تجريبي)",
    "setting.exclude_from_capture.tip": (
        "تجريبي: يُبعد المطر عن لقطات الشاشة وتسجيلاتها. "
        "يتطلب Windows 10 الإصدار 2004 أو أحدث."
    ),
    # --- صفحة المتقدم ---
    "card.engine.title": "المحرك",
    "card.engine.desc": "ضبط دقيق للأداء ولاستكشاف الأعطال.",
    "setting.adaptive_quality.label": "الجودة التكيفية",
    "setting.adaptive_quality.tip": "يخفّض عدد القطرات تلقائيًا إذا تباطأت الإطارات.",
    "setting.depth_layers.label": "طبقات العمق",
    "setting.depth_layers.tip": "عدد مستويات العمق. المزيد أغنى مظهرًا لكنه أكلف.",
    "setting.topmost_watchdog.label": "إبقاء المطر في الأعلى",
    "setting.topmost_watchdog.tip": "يعيد تثبيت الطبقة فوق النوافذ الأخرى كل بضع ثوانٍ.",
    "setting.debug_hud.label": "إظهار لوحة التشخيص",
    "setting.debug_hud.tip": "يعرض زمن الإطار وعدد القطرات في زاوية الشاشة.",
    "setting.log_level.label": "مستوى السجل",
    "setting.log_level.tip": "مقدار التفاصيل المكتوبة في ملف السجل.",
    "setting.rng_seed.label": "بذرة العشوائية",
    "setting.rng_seed.tip": (
        "القيمة -1 تختار بذرة عشوائية جديدة عند كل تشغيل. الرقم الثابت يجعل التشغيلات "
        "قابلة للتكرار. يسري عند التشغيل التالي."
    ),
    "card.data.title": "ملف الإعدادات والسجلات",
    "card.data.desc": "انسخ إعداداتك احتياطيًا، أو انقلها إلى جهاز آخر، أو افتح السجلات.",
    "button.import": "استيراد الإعدادات...",
    "button.export": "تصدير الإعدادات...",
    "button.open_logs": "فتح مجلد السجلات",
    "dialog.import_title": "استيراد الإعدادات",
    "dialog.export_title": "تصدير الإعدادات",
    "dialog.json_filter": "ملفات JSON (*.json)",
    "msg.import_ok": "تم استيراد الإعدادات.",
    "msg.import_failed": "تعذّر استيراد هذا الملف.",
    "msg.export_ok": "تم تصدير الإعدادات.",
    "msg.export_failed": "تعذّر تصدير الإعدادات.",
    "msg.open_logs_failed": "تعذّر فتح مجلد السجلات.",
    # --- صفحة حول ---
    "card.about.title": "عن RainDesk",
    "about.tagline": "مطر ناعم على سطح مكتب ويندوز.",
    "about.version": "الإصدار {version}",
    "card.licenses.title": "تراخيص المصادر المفتوحة",
    "card.licenses.desc": "يعتمد RainDesk على برمجيات حرة.",
    "license.pyside6": (
        "PySide6 (Qt for Python): رخصة LGPLv3. تُستعمل بالربط الديناميكي، "
        "فتبقى مكتبات Qt قابلة للاستبدال."
    ),
    "license.numpy": "NumPy: رخصة BSD ثلاثية البنود.",
    "license.pyinstaller": (
        "PyInstaller: رخصة GPLv2 مع استثناء خاص يسمح بتغليف البرامج تحت أي رخصة."
    ),
    "license.python": "Python: رخصة PSF.",
    "card.privacy.title": "الخصوصية",
    "privacy.body": (
        "لا اتصال بالشبكة ولا قياسات استخدام. لا يلتقط RainDesk شاشتك أبدًا ولا يقرأ "
        "لوحة المفاتيح ولا الفأرة ولا الميكروفون. تبقى الإعدادات والسجلات على هذا الجهاز."
    ),
    "privacy.registry": "التغيير الوحيد في النظام هو إدخال تشغيل اختياري لحسابك.",
     # --- الصوت ---
    "card.sound.title": "صوت المطر",
    "card.sound.desc": "صوت مطر ناعم يولّده RainDesk لحظيًا دون أي ملفات صوتية.",
    "setting.sound_enabled.label": "تشغيل صوت المطر",
    "setting.sound_enabled.tip": (
        "يشغّل صوت مطر مولَّدًا عبر جهاز الصوت الافتراضي. معطّل افتراضيًا."
    ),
    "setting.sound_volume.label": "مستوى الصوت",
    "setting.sound_volume.tip": "علوّ صوت المطر. أبقِه منخفضًا ليبقى في الخلفية.",
    "setting.sound_follows_intensity.label": "يتبع شدة المطر",
    "setting.sound_follows_intensity.tip": "يعلو الصوت ويكثف كلما اشتد المطر.",
    "setting.sound_wind.label": "صوت الرياح",
    "setting.sound_wind.tip": "يضيف طبقة رياح ناعمة تتبع الرياح وهبّاتها.",
    "note.sound_unavailable": "الصوت غير متاح: لم يُعثر على جهاز إخراج صوتي.",
    "tray.sound": "صوت المطر",
}
