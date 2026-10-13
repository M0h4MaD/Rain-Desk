# خطوات قبل النشر (PowerShell، من جذر المشروع)

```powershell
# 1) احذف الملفين من git (يبقى settings.json على جهازك)
git rm --cached settings.json
git rm create_skeleton.ps1

# 2) أضف سطر settings.json إلى .gitignore (من GITIGNORE_ADD.txt)

# 3) استبدل README.md بالنسخة الجديدة، وضع LICENSE (اكتب اسمك فيه)
git add README.md LICENSE .gitignore
git commit -m "docs: update README (MIT license, download section), ignore local settings"
git push

# 4) ابنِ الحزمة (بيئة Python 3.12 نظيفة) وانسخ التراخيص إلى dist\RainDesk\licenses ثم:
python tools/package.py
Get-FileHash dist\RainDesk-1.0.0-win64.zip -Algorithm SHA256   # اسم الملف كما يطبعه package.py

# 5) وسم الإصدار (يطابق APP_VERSION = 1.0.0 في constants.py وversion_info.txt)
git tag -a v1.0.0 -m "RainDesk 1.0.0"
git push origin v1.0.0

# 6) أنشئ الـ Release وارفع الـ ZIP، والصق الهاش في RELEASE_NOTES.md قبل ذلك
gh release create v1.0.0 dist\RainDesk-1.0.0-win64.zip --title "RainDesk 1.0.0" --notes-file RELEASE_NOTES.md
```

بعدها من موقع GitHub:
- افتح README.md للتحرير، واسحب الفيديو مكان تعليق `<!-- Drag your demo video ... -->`.
- في الـ About (الترس أعلى يمين الصفحة): اكتب Description وأضف Topics:
  `rain`, `overlay`, `windows`, `pyside6`, `python`, `desktop-app`, `procedural-audio`.
