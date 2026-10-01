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
        "اختيار إعداد مسبق يضبط قيم المطر والرياح الأساسية. "
        "تحريك أي منزلق يحوّله إلى مخصص."
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
}