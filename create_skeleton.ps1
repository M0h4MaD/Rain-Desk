# ينشئ كل المجلدات والملفات الفارغة. لا يمسّ أي ملف موجود.
$ErrorActionPreference = 'Stop'
$root = $PSScriptRoot   # مجلد المشروع = مكان هذا السكربت

$files = @(
    'main.py', 'pyproject.toml', 'requirements.txt', 'requirements-dev.txt',
    'README.md', 'THIRD_PARTY_NOTICES.md', '.gitignore', 'raindesk.spec', 'version_info.txt',
    'docs/architecture.md',
    'tools/make_icon.py', 'tools/bench_engine.py', 'tools/audio_demo.py',
    'installer/raindesk.iss',
    'tests/conftest.py', 'tests/test_math_utils.py', 'tests/test_color_utils.py',
    'tests/test_config_schema.py', 'tests/test_settings_store.py', 'tests/test_rain_field.py',
    'tests/test_splash_system.py', 'tests/test_weather_fsm.py', 'tests/test_adaptive_quality.py',
    'tests/test_mascot.py', 'tests/test_rain_audio.py', 'tests/test_i18n.py',
    'tests/test_theme_contrast.py', 'tests/test_win32_api.py', 'tests/test_autostart.py',
    'raindesk/__init__.py', 'raindesk/__main__.py',
    'raindesk/core/__init__.py', 'raindesk/core/constants.py', 'raindesk/core/paths.py',
    'raindesk/core/color_utils.py', 'raindesk/core/logging_setup.py',
    'raindesk/core/single_instance.py',
    'raindesk/config/__init__.py', 'raindesk/config/schema.py', 'raindesk/config/store.py',
    'raindesk/engine/__init__.py', 'raindesk/engine/math_utils.py', 'raindesk/engine/params.py',
    'raindesk/engine/rain_field.py', 'raindesk/engine/splash_system.py',
    'raindesk/engine/edge_streams.py', 'raindesk/engine/weather_fsm.py',
    'raindesk/engine/mascot.py', 'raindesk/engine/adaptive_quality.py',
    'raindesk/engine/rain_audio.py',
    'raindesk/platform_win/__init__.py', 'raindesk/platform_win/win32_api.py',
    'raindesk/platform_win/autostart.py', 'raindesk/platform_win/system_watcher.py',
    'raindesk/i18n/__init__.py', 'raindesk/i18n/translator.py',
    'raindesk/i18n/strings_en.py', 'raindesk/i18n/strings_ar.py',
    'raindesk/ui/__init__.py', 'raindesk/ui/frame_clock.py', 'raindesk/ui/overlay_window.py',
    'raindesk/ui/overlay_manager.py', 'raindesk/ui/tray.py', 'raindesk/ui/theme.py',
    'raindesk/ui/settings_window.py',
    'raindesk/ui/painters/__init__.py', 'raindesk/ui/painters/rain_painter.py',
    'raindesk/ui/painters/effects_painter.py', 'raindesk/ui/painters/mascot_painter.py',
    'raindesk/ui/painters/hud_painter.py',
    'raindesk/ui/widgets/__init__.py', 'raindesk/ui/widgets/labeled_slider.py',
    'raindesk/ui/widgets/toggle_switch.py', 'raindesk/ui/widgets/color_button.py',
    'raindesk/ui/widgets/section_card.py', 'raindesk/ui/widgets/screen_picker.py',
    'raindesk/ui/audio/__init__.py', 'raindesk/ui/audio/audio_player.py',
    'raindesk/ui/pages/__init__.py', 'raindesk/ui/pages/base_page.py',
    'raindesk/ui/pages/general_page.py', 'raindesk/ui/pages/rain_page.py',
    'raindesk/ui/pages/effects_page.py', 'raindesk/ui/pages/mascot_page.py',
    'raindesk/ui/pages/display_page.py', 'raindesk/ui/pages/advanced_page.py',
    'raindesk/ui/pages/about_page.py',
    'raindesk/app/__init__.py', 'raindesk/app/controller.py', 'raindesk/app/bootstrap.py'
)

$created = 0
foreach ($rel in $files) {
    $path = Join-Path $root ($rel -replace '/', '\')
    $dir  = Split-Path -Path $path -Parent
    if (-not (Test-Path -LiteralPath $dir)) {
        New-Item -ItemType Directory -Path $dir | Out-Null   # ينشئ المجلدات الأم تلقائيًا
    }
    if (-not (Test-Path -LiteralPath $path)) {
        New-Item -ItemType File -Path $path | Out-Null
        $created++
    }
}
New-Item -ItemType Directory -Path (Join-Path $root 'assets') -Force | Out-Null
Write-Host "Done. Created $created new file(s). Total in list: $($files.Count)"