import json
from pathlib import Path

from app.main import app


def main() -> None:
    target = Path(__file__).resolve().parents[1] / "openapi.m8.json"
    target.write_text(
        json.dumps(app.openapi(), indent=2, ensure_ascii=True) + "\n",
        encoding="utf-8",
    )


if __name__ == "__main__":
    main()
