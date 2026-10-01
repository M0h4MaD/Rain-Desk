"""raindesk/i18n/strings_en.py

الغرض: نصوص الواجهة بالإنجليزية (المرجع الاحتياطي عند غياب مفتاح في لغة أخرى).
القواعد: مفاتيح منقّطة بالشكل 'المنطقة.الاسم'؛ نفس المفاتيح ونفس {placeholders} في strings_ar.py
    (يتحقق منها tests/test_i18n.py)؛ لا تستعمل الأقواس المعقوصة إلا للمتغيرات.
    اصطلاح التلميحات: لكل مفتاح 'setting.X.label' مفتاح 'setting.X.tip' للتلميح (tooltip).
"""

from __future__ import annotations

from typing import Final

STRINGS: Final[dict[str, str]] = {
    # --- عام ---
    "app.name": "RainDesk",
    "lang.auto": "Automatic (system language)",
    "window.title": "RainDesk Settings",
    # --- رسائل ---
    "msg.settings_corrupt": (
        "The settings file was damaged, so defaults were loaded. "
        "A backup was saved as {name}."
    ),
    "msg.first_run_title": "Welcome to RainDesk",
    "msg.first_run_body": (
        "RainDesk keeps running in the system tray. Click its icon to open the "
        "settings."
    ),
    "msg.tray_unavailable": (
        "The system tray is not available, so closing this window will quit RainDesk."
    ),
    # --- التنقل ---
    "nav.general": "General",
    "nav.rain": "Rain and Wind",
    # --- أزرار الواجهة ---
    "ui.randomize": "Randomize",
    "ui.reset": "Reset to defaults",
    "ui.saved": "Saved",
    "ui.reset_confirm.title": "Reset to defaults",
    "ui.reset_confirm.body": "All settings will return to their default values. Continue?",
    "ui.confirm": "Reset",
    "ui.cancel": "Cancel",
    # --- شريط النظام ---
    "tray.open_settings": "Open settings",
    "tray.enable": "Show rain",
    "tray.randomize": "Randomize",
    "tray.presets": "Presets",
    "tray.quit": "Quit",
    "tray.tooltip_off": "RainDesk (off)",
    # --- أسماء الإعدادات المسبقة والسمات ---
    "preset.custom": "Custom",
    "preset.drizzle": "Drizzle",
    "preset.light": "Light rain",
    "preset.moderate": "Moderate rain",
    "preset.heavy": "Heavy rain",
    "preset.storm": "Storm",
    "theme.system": "System",
    "theme.light": "Light",
    "theme.dark": "Dark",
    # --- أداة اللون ---
    "color.pick_title": "Choose a color",
    "color.tip": "Click to choose a color",
    # --- الصفحة العامة ---
    "card.behavior.title": "Behavior",
    "card.behavior.desc": "Control when the rain is shown and how RainDesk starts.",
    "setting.enabled.label": "Show rain",
    "setting.enabled.tip": "Turn the rain overlay on or off without quitting RainDesk.",
    "setting.launch_at_login.label": "Start with Windows",
    "setting.launch_at_login.tip": "Start RainDesk automatically when you sign in to Windows.",
    "setting.start_hidden_in_tray.label": "Start hidden in the tray",
    "setting.start_hidden_in_tray.tip": (
        "When off, the settings window opens every time RainDesk starts."
    ),
    "card.appearance.title": "Appearance",
    "card.appearance.desc": "Language and color theme of this window.",
    "setting.language.label": "Language",
    "setting.language.tip": (
        "Switches the interface language and its reading direction immediately."
    ),
    "setting.theme.label": "Theme",
    "setting.theme.tip": "Follow Windows, or force a light or dark window.",
    # --- صفحة المطر والرياح ---
    "card.preset.title": "Presets",
    "card.preset.desc": "Start from a ready-made weather, then fine-tune it below.",
    "setting.preset.label": "Weather preset",
    "setting.preset.tip": (
        "Choosing a preset sets the main rain and wind values. Moving a slider makes it "
        "Custom."
    ),
    "note.auto_weather": "Automatic weather is on, so these controls are managed for you.",
    "card.drops.title": "Drops",
    "card.drops.desc": "How the rain looks.",
    "setting.intensity.label": "Intensity",
    "setting.intensity.tip": "How many drops fall. The density adapts to your screen size.",
    "setting.speed.label": "Speed",
    "setting.speed.tip": "How fast the drops fall.",
    "setting.drop_length.label": "Drop length",
    "setting.drop_length.tip": "Length of each streak. Faster drops always look longer.",
    "setting.drop_thickness.label": "Thickness",
    "setting.drop_thickness.tip": "Line width of the drops.",
    "setting.drop_opacity.label": "Opacity",
    "setting.drop_opacity.tip": "How visible the drops are. Lower values are more transparent.",
    "setting.drop_color.label": "Color",
    "setting.drop_color.tip": "Base color of the drops.",
    "setting.parallax_strength.label": "Depth effect",
    "setting.parallax_strength.tip": "How much farther drops are smaller, slower and fainter.",
    "card.wind.title": "Wind",
    "card.wind.desc": "Direction and gustiness of the wind.",
    "setting.wind_angle_deg.label": "Wind angle",
    "setting.wind_angle_deg.tip": (
        "Tilt of the falling rain. Negative leans left, positive leans right."
    ),
    "setting.wind_gusts.label": "Gusts",
    "setting.wind_gusts.tip": "How strongly the wind angle varies over time.",
    "setting.gust_period_s.label": "Gust period",
    "setting.gust_period_s.tip": "Typical time between gusts, in seconds.",
}