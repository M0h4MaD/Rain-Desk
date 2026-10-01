"""raindesk/__main__.py: يتيح التشغيل بالأمر 'python -m raindesk' بنفس سلوك main.py."""

from __future__ import annotations

from raindesk.app.bootstrap import main

if __name__ == "__main__":
    raise SystemExit(main())