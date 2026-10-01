"""main.py: نقطة دخول التطبيق (وأيضًا نقطة دخول PyInstaller)."""

from __future__ import annotations

from raindesk.app.bootstrap import main

if __name__ == "__main__":
    raise SystemExit(main())