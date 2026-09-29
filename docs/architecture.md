# RainDesk: المعمارية

## 1) شجرة المشروع

```text
RainDesk/
  main.py  pyproject.toml  requirements.txt  requirements-dev.txt
  README.md  THIRD_PARTY_NOTICES.md  .gitignore  raindesk.spec  version_info.txt
  assets/       (raindesk.ico يُولَّد لاحقًا)
  docs/         architecture.md
  tools/        make_icon.py  bench_engine.py  audio_demo.py
  installer/    raindesk.iss
  tests/        conftest.py  test_{math_utils,color_utils,config_schema,settings_store,
                rain_field,splash_system,weather_fsm,adaptive_quality,mascot,rain_audio,
                i18n,theme_contrast,win32_api,autostart}.py
  raindesk/
    __init__.py  __main__.py
    core/          constants  paths  color_utils  logging_setup  single_instance
    config/        schema  store
    engine/        math_utils  params  rain_field  splash_system  edge_streams
                   weather_fsm  mascot  adaptive_quality  rain_audio
    platform_win/  win32_api  autostart  system_watcher
    i18n/          translator  strings_en  strings_ar
    ui/            frame_clock  overlay_window  overlay_manager  tray  theme  settings_window
      painters/    rain_painter  effects_painter  mascot_painter  hud_painter
      widgets/     labeled_slider  toggle_switch  color_button  section_card  screen_picker
      audio/       audio_player
      pages/       base_page  general_page  rain_page  effects_page  mascot_page
                   display_page  advanced_page  about_page
    app/           controller  bootstrap
```

## 2) قواعد الطبقات (فحص التبعيات)

| الطبقة | تستورد من | ملاحظة |
|---|---|---|
| core | لا شيء | `single_instance` يستخدم QtCore وQtNetwork فقط |
| config | core | `schema.py` بلا PySide6، و`store.py` يستخدم QtCore |
| engine | core، و`config.schema` فقط | NumPy والمكتبة القياسية فقط، بلا PySide6 |
| platform_win | core | `win32_api` و`autostart` بلا PySide6، و`system_watcher` يستخدم QtCore |
| i18n | core | |
| ui | config, engine, platform_win, i18n, core | QtMultimedia داخل `ui/audio` فقط وباستيراد كسول |
| app | كل الطبقات | جذر التركيب (Composition Root) |

النتيجة: الترتيب الطوبولوجي `core → {config, platform_win, i18n} → engine → ui → app`. لا توجد دورات، ولا يوجد سهم من طبقة أدنى إلى أعلى. هذا فحص تصميمي لأن الكود لم يُكتب بعد.

## 3) المخططات

### 3.1 مكوّنات الطبقات

```mermaid
flowchart TD
    app["app: AppController, bootstrap"]
    ui["ui: overlay, painters, tray, settings, audio"]
    engine["engine: rain, splash, weather, mascot, audio synth"]
    config["config: schema, store"]
    platform_win["platform_win: win32_api, autostart, watcher"]
    i18n["i18n: translator, strings"]
    core["core: constants, paths, colors, logging, single_instance"]
    app --> ui
    app --> engine
    app --> config
    app --> platform_win
    app --> i18n
    app --> core
    ui --> engine
    ui --> config
    ui --> platform_win
    ui --> i18n
    ui --> core
    engine -->|schema only| config
    engine --> core
    config --> core
    platform_win --> core
    i18n --> core
```

### 3.2 تسلسل بدء التطبيق

```mermaid
sequenceDiagram
    participant M as main
    participant G as SingleInstanceGuard
    participant S as SettingsStore
    participant T as Translator + Theme
    participant W as SystemWatcher
    participant O as OverlayManager
    participant Y as TrayController
    M->>M: parse argv, configure_logging, QApplication
    M->>G: acquire()
    alt not primary
        M->>G: notify_primary()
        M-->>M: exit 0
    else primary
        M->>S: load()
        M->>T: apply language and theme
        M->>W: start()
        M->>O: rebuild()
        M->>Y: show()
        opt first run
            M->>M: show settings window and tray message
        end
    end
```

### 3.3 من تحريك المنزلق إلى التحديث الحي

```mermaid
sequenceDiagram
    participant U as LabeledSlider
    participant P as Page
    participant S as SettingsStore
    participant C as AppController
    participant M as OverlayManager
    participant Z as ParamSmoother
    U->>P: valueChanged(v)
    P->>S: set(key, v)
    S->>S: validate, clamp, debounced save
    S-->>C: changed(key)
    C->>M: apply settings snapshot as target
    loop every tick
        M->>Z: step(dt)
        Z-->>M: smoothed EngineParams
    end
    S->>S: save_now after 400 ms, atomic
```

### 3.4 آلة حالات الطقس (Markov)

```mermaid
stateDiagram-v2
    drizzle --> light: 0.65
    drizzle --> moderate: 0.30
    drizzle --> heavy: 0.05
    light --> drizzle: 0.30
    light --> moderate: 0.50
    light --> heavy: 0.20
    moderate --> drizzle: 0.10
    moderate --> light: 0.30
    moderate --> heavy: 0.45
    moderate --> storm: 0.15
    heavy --> light: 0.15
    heavy --> moderate: 0.50
    heavy --> storm: 0.35
    storm --> moderate: 0.55
    storm --> heavy: 0.45
```

### 3.5 آلة حالات الشخصية Drip

```mermaid
stateDiagram-v2
    [*] --> HIDDEN
    state pick <<choice>>
    HIDDEN --> ENTERING: timer Exp mean 45 to 240 s, min gap 20 s
    ENTERING --> pick: reached the stage
    pick --> WALKING: 0.35
    pick --> IDLE: 0.25
    pick --> LOOK_UP: 0.15
    pick --> CROUCHING: 0.15
    pick --> SHAKING: 0.10
    pick --> EXITING: visible time 12 to 35 s elapsed
    WALKING --> pick: done
    IDLE --> pick: done
    LOOK_UP --> pick: done
    SHAKING --> pick: done
    CROUCHING --> JUMPING: after 0.12 s
    JUMPING --> LANDING: ground hit
    LANDING --> pick: squash done
    EXITING --> HIDDEN: off screen
```

### 3.6 حلقة الإطار (كل tick)

```mermaid
flowchart TD
    A["FrameClock: dt = min(delta, DT_MAX_S), emit tick"] --> B["OverlayManager: weather.step, build target params"]
    B --> C["smoother.step, gust_signal, mascot.step"]
    C --> D{"for each overlay"}
    D --> E["OverlayWindow.advance: field.step, splash, edge_streams"]
    E --> F["update, then paintEvent"]
    F --> G["paint order: tint, streams, rain layers, splashes, lightning, mascot, HUD"]
    G --> H["AdaptiveQuality.record, push scale"]
    H --> I["emit simulation_updated(params, gust)"]
    I --> A
```

### 3.7 خط توليد الصوت

```mermaid
flowchart LR
    L1["bed_mid loop: irfft, N-periodic"] --> G1["gain g_mid"]
    L2["bed_high loop"] --> G2["gain g_high"]
    L3["wind loop"] --> G4["gain g_wind, gust"]
    D["droplet bank + Poisson events"] --> G3["gain g_droplets, pan"]
    G1 --> MIX["sum of layers"]
    G2 --> MIX
    G3 --> MIX
    G4 --> MIX
    MIX --> MG["master gain ramp: volume^2 x fade"]
    MG --> SC["soft clip: 0.98 tanh(1.2 x)"]
    SC --> Q["float32 to int16 interleaved"]
    Q --> SINK["QAudioSink push mode, 20 ms timer"]
```

## 4) قرارات التصميم

| # | القرار | البدائل | السبب | النتيجة |
|---|---|---|---|---|
| DD-01 | Python + PySide6 | Electron، C# WPF، Tkinter، pygame | يناسب مهارات الطالب وأقل كلفة أدوات، وQt يوفّر نافذة شفافة وواجهة إعدادات غنية | حزمة أكبر من تطبيق أصلي |
| DD-02 | نافذة overlay لكل شاشة | نافذة عملاقة واحدة | DPI صحيح لكل شاشة وتصفية لكل شاشة | إدارة عدة نوافذ في `OverlayManager` |
| DD-03 | رسم QPainter (raster) | OpenGL | توافق أفضل مع النوافذ الشفافة، والمعالج يكفي لهذا العدد من الجسيمات | لا تسريع GPU |
| DD-04 | NumPy بتخطيط SoA | قائمة كائنات قطرات | تحديث متجه بلا حلقات بايثون وذاكرة متجاورة | كود أقل بداهة |
| DD-05 | تقسيم العمق إلى N طبقات أقلام | قلم مستقل لكل قطرة | تقليل تبديل `QPen` | العمق متقطع وليس متصلًا |
| DD-06 | نموذج التعرّض (طول الخط = السرعة × زمن التعرض) | رسم القطرات نقاطًا | يحاكي تمويه الحركة | يحتاج ثوابت مضبوطة |
| DD-07 | تنعيم أسّي للإعدادات | قفز مباشر، أو tween منفصل | `alpha = 1 - exp(-dt/tau)` يعطي انتقالًا ناعمًا بلا كود إضافي | تأخر طفيف في الاستجابة |
| DD-08 | قواميس بايثون للترجمة | ملفات `.ts/.qm` أو JSON | تجنّب مشاكل تجميع ملفات البيانات | الترجمة تُكتب يدويًا |
| DD-09 | PyInstaller بنمط onedir | onefile | إقلاع أسرع ومسارات موارد أبسط | مجلد كامل بدل ملف واحد |
| DD-10 | نمط Mediator (`AppController` و`OverlayManager`) | ربط إشارات مباشر بين الودجات | فصل الواجهة عن المنطق | كلاس وسيط مركزي |
| DD-11 | `SHQueryUserNotificationState` | تخمين من مستطيل النافذة | واجهة نظام رسمية لحالة ملء الشاشة | يُختبر يدويًا مع تطبيقات مختلفة |
| DD-12 | صوت مولَّد برمجيًا | تسجيلات جاهزة | لا ترخيص ولا حجم إضافي وتحكم لحظي بالشدة والرياح | أقل واقعية من تسجيل حقيقي |
| DD-13 | حلقات ضجيج بطيف مُشكَّل وأطوار عشوائية + irfft | ترشيح IIR لضجيج أبيض | دورية بالبناء دون تلاشٍ متقاطع، ومتجهة بالكامل بلا SciPy | ذاكرة الحلقات نحو 8.5 MB |
| DD-14 | `QAudioSink` بنمط push مع مؤقت 20 ms | نمط pull بصنف `QIODevice` | تحكم أوضح بالتخزين المؤقت والتعافي من underrun | يعتمد على دقة المؤقت |