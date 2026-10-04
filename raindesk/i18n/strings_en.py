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
        "Choosing a preset sets the main rain and wind values. Moving a slider makes "
        "it Custom."
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
    # --- التنقل (الصفحات الجديدة) ---
    "nav.effects": "Effects",
    "nav.mascot": "Mascot",
    "nav.display": "Display and Performance",
    "nav.advanced": "Advanced",
    "nav.about": "About",
    # --- صفحة المؤثرات ---
    "card.splashes.title": "Splashes",
    "card.splashes.desc": "Ripples and spray where the drops land.",
    "setting.splashes_enabled.label": "Show splashes",
    "setting.splashes_enabled.tip": "Draw small ripples and spray when drops hit the ground.",
    "setting.splash_amount.label": "Splash amount",
    "setting.splash_amount.tip": "How many drops create a splash.",
    "setting.splash_zone.label": "Landing zone",
    "setting.splash_zone.tip": (
        "Bottom edge: drops land at the bottom of the screen. "
        "Depth planes: nearer drops land lower on the screen."
    ),
    "splash_zone.bottom_edge": "Bottom edge",
    "splash_zone.depth_plane": "Depth planes",
    "card.streams.title": "Edge streams",
    "card.streams.desc": "Water running down the left and right edges of the screen.",
    "setting.edge_streams_enabled.label": "Show edge streams",
    "setting.edge_streams_enabled.tip": "Draw thin streams of water along both screen edges.",
    "setting.edge_streams_count.label": "Streams per edge",
    "setting.edge_streams_count.tip": "How many streams run down each edge.",
    "setting.edge_streams_opacity.label": "Stream opacity",
    "setting.edge_streams_opacity.tip": "How visible the streams are.",
    "card.mood.title": "Mood tint",
    "card.mood.desc": "A soft color wash over the whole screen.",
    "setting.mood_enabled.label": "Show mood tint",
    "setting.mood_enabled.tip": "Tint the screen to give the scene a gloomy or calm feel.",
    "setting.mood_color.label": "Tint color",
    "setting.mood_color.tip": "Color of the tint.",
    "setting.mood_opacity.label": "Tint strength",
    "setting.mood_opacity.tip": "How strong the tint is. Keep it low to stay readable.",
    "card.lightning.title": "Lightning",
    "card.lightning.desc": "Occasional flashes during heavy weather.",
    "setting.lightning_enabled.label": "Show lightning",
    "setting.lightning_enabled.tip": "Brief bright flashes. Off by default.",
    "setting.lightning_frequency.label": "Flash frequency",
    "setting.lightning_frequency.tip": "How often lightning flashes.",
    "note.lightning_warning": (
        "Warning: lightning produces bright flashes. "
        "Do not enable it if you are sensitive to flashing light."
    ),
    "note.lightning_animations_off": (
        "Windows animations are turned off, so lightning is unavailable."
    ),
    "card.weather.title": "Automatic weather",
    "card.weather.desc": "Let the weather drift between drizzle and storm by itself.",
    "setting.auto_weather.label": "Automatic weather",
    "setting.auto_weather.tip": (
        "The weather changes on its own and the rain and wind controls are managed for you."
    ),
    "setting.auto_weather_variability.label": "Variability",
    "setting.auto_weather_variability.tip": (
        "Low keeps the weather steady; high changes it more often and more widely."
    ),
    # --- صفحة الشخصية ---
    "card.mascot.title": "Mascot",
    "card.mascot.desc": "Drip is a small raindrop who walks across your screen now and then.",
    "setting.mascot_enabled.label": "Show Drip",
    "setting.mascot_enabled.tip": "Let Drip appear. When off, it costs nothing.",
    "setting.mascot_frequency.label": "Appearance frequency",
    "setting.mascot_frequency.tip": "How often Drip shows up.",
    "setting.mascot_scale.label": "Size",
    "setting.mascot_scale.tip": "Size of Drip on screen.",
    # --- صفحة العرض والأداء ---
    "card.screens.title": "Screens",
    "card.screens.desc": "Choose where the rain falls.",
    "setting.screens_mode.label": "Show rain on",
    "setting.screens_mode.tip": "All screens, only the primary one, or screens you pick below.",
    "screens_mode.all": "All screens",
    "screens_mode.primary": "Primary screen only",
    "screens_mode.selected": "Selected screens",
    "setting.selected_screens.label": "Choose screens",
    "setting.selected_screens.tip": "Tick the screens that should show rain.",
    "display.primary_badge": "Primary",
    "setting.cover_taskbar.label": "Cover the taskbar",
    "setting.cover_taskbar.tip": "Off keeps the rain above the taskbar; on covers the full screen.",
    "card.performance.title": "Performance",
    "card.performance.desc": "Trade smoothness for battery and processor time.",
    "setting.quality.label": "Quality",
    "setting.quality.tip": "A profile that sets the frame rate and smoothing together.",
    "quality.low": "Low (saves power)",
    "quality.balanced": "Balanced",
    "quality.high": "High (smoothest)",
    "setting.fps_cap.label": "Frame rate limit",
    "setting.fps_cap.tip": "Maximum frames per second. Lower values use less processor time.",
    "setting.antialiasing.label": "Smooth edges",
    "setting.antialiasing.tip": (
        "Anti-aliasing makes drops look smoother but costs some performance."
    ),
    "card.pause.title": "Pausing and capture",
    "card.pause.desc": "When RainDesk should step aside.",
    "setting.pause_on_fullscreen.label": "Pause during full-screen apps",
    "setting.pause_on_fullscreen.tip": "Hide the rain while a game or video plays full screen.",
    "setting.pause_on_battery_saver.label": "Pause in battery saver",
    "setting.pause_on_battery_saver.tip": "Hide the rain while Windows battery saver is on.",
    "setting.exclude_from_capture.label": "Hide from screenshots (experimental)",
    "setting.exclude_from_capture.tip": (
        "Experimental: keeps the rain out of screenshots and screen recordings. "
        "Needs Windows 10 version 2004 or newer."
    ),
    # --- صفحة المتقدم ---
    "card.engine.title": "Engine",
    "card.engine.desc": "Fine controls for performance and troubleshooting.",
    "setting.adaptive_quality.label": "Adaptive quality",
    "setting.adaptive_quality.tip": "Lowers the drop count automatically if frames get slow.",
    "setting.depth_layers.label": "Depth layers",
    "setting.depth_layers.tip": "Number of depth levels. More levels look richer but cost more.",
    "setting.topmost_watchdog.label": "Keep rain on top",
    "setting.topmost_watchdog.tip": "Re-asserts the overlay above other windows every few seconds.",
    "setting.debug_hud.label": "Show debug HUD",
    "setting.debug_hud.tip": "Shows frame time and drop count in a corner of the screen.",
    "setting.log_level.label": "Log level",
    "setting.log_level.tip": "How much detail is written to the log file.",
    "setting.rng_seed.label": "Random seed",
    "setting.rng_seed.tip": (
        "-1 picks a new random seed on every launch. A fixed number makes runs reproducible. "
        "Takes effect at the next launch."
    ),
    "card.data.title": "Settings file and logs",
    "card.data.desc": "Back up your settings, move them to another computer or open the logs.",
    "button.import": "Import settings...",
    "button.export": "Export settings...",
    "button.open_logs": "Open log folder",
    "dialog.import_title": "Import settings",
    "dialog.export_title": "Export settings",
    "dialog.json_filter": "JSON files (*.json)",
    "msg.import_ok": "Settings imported.",
    "msg.import_failed": "Could not import this file.",
    "msg.export_ok": "Settings exported.",
    "msg.export_failed": "Could not export the settings.",
    "msg.open_logs_failed": "Could not open the log folder.",
    # --- صفحة حول ---
    "card.about.title": "About RainDesk",
    "about.tagline": "Soft rain on your Windows desktop.",
    "about.version": "Version {version}",
    "card.licenses.title": "Open-source licenses",
    "card.licenses.desc": "RainDesk is built on free software.",
    "license.pyside6": (
        "PySide6 (Qt for Python): LGPLv3. Used through dynamic linking, "
        "so the Qt libraries stay replaceable."
    ),
    "license.numpy": "NumPy: BSD 3-Clause license.",
    "license.pyinstaller": (
        "PyInstaller: GPLv2 with a special exception that allows packaging programs "
        "under any license."
    ),
    "license.python": "Python: PSF License.",
    "card.privacy.title": "Privacy",
    "privacy.body": (
        "No network and no telemetry. RainDesk never captures your screen and never reads "
        "your keyboard, mouse or microphone. Settings and logs stay on this computer."
    ),
    "privacy.registry": (
        "The only system change is an optional startup entry for your user account."
    ),
}
