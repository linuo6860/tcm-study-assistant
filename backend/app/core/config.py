import os
from pathlib import Path


class Settings:
    app_name = "TCM Exam Study Assistant"
    api_prefix = "/api"

    base_dir = Path(__file__).resolve().parents[1]
    data_dir = base_dir / "data"
    storage_dir = Path(os.getenv("TCM_STORAGE_DIR", str(data_dir))).expanduser()
    textbook_json_path = Path(
        os.getenv(
            "TEXTBOOK_JSON_PATH",
            str(data_dir / "textbooks" / "sample_tcm_textbook.json"),
        )
    ).expanduser()
    upload_dir = Path(os.getenv("TCM_UPLOAD_DIR", str(storage_dir / "uploads"))).expanduser()
    sqlite_path = Path(os.getenv("SQLITE_PATH", str(storage_dir / "tcm_assistant.sqlite3"))).expanduser()

    cors_origins = [
        origin.strip()
        for origin in os.getenv(
            "CORS_ORIGINS",
            "http://localhost:5173,http://127.0.0.1:5173",
        ).split(",")
        if origin.strip()
    ]

    def ensure_directories(self) -> None:
        self.storage_dir.mkdir(parents=True, exist_ok=True)
        self.upload_dir.mkdir(parents=True, exist_ok=True)


settings = Settings()
