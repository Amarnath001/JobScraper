"""
Seed companies from data/company_targets.csv (delegates to import_company_targets.py).

  python scripts/seed_companies.py
  docker compose exec app python scripts/seed_companies.py
"""

from __future__ import annotations

import os
import subprocess
import sys


def main() -> None:
    root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    script = os.path.join(root, "scripts", "import_company_targets.py")
    raise SystemExit(subprocess.call([sys.executable, script], env=os.environ.copy()))


if __name__ == "__main__":
    main()
