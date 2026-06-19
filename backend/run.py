"""Entry point: uv run run.py"""

import sys
from pathlib import Path

# Make sure pursuit_api is importable without an editable install
sys.path.insert(0, str(Path(__file__).parent / "src"))

import uvicorn

if __name__ == "__main__":
    from config import settings

    uvicorn.run(
        "main:app",
        host="0.0.0.0",  # noqa: S104
        port=8000,
        reload=settings.app_env == "development",
    )
