from __future__ import annotations

import shutil
from pathlib import Path


def main() -> None:
    project_root = Path(__file__).resolve().parent.parent
    source = project_root / "web"
    destination = project_root / "public"

    if not source.is_dir():
        raise FileNotFoundError(f"Frontend source directory not found: {source}")

    shutil.rmtree(destination, ignore_errors=True)
    shutil.copytree(source, destination)
    print(f"Prepared {destination} from {source}")


if __name__ == "__main__":
    main()
