"""Application configuration and filesystem path definitions."""

from dataclasses import dataclass, field
import os
import sys
from pathlib import Path

# Workspace base root
if getattr(sys, 'frozen', False):
    # When running as standalone executable (.exe):
    # Prefer directory of executable; fallback to LocalAppData if directory is read-only
    exe_dir = Path(sys.executable).resolve().parent
    try:
        test_probe = exe_dir / ".write_probe"
        test_probe.touch()
        test_probe.unlink()
        BASE_DIR = exe_dir
    except Exception:
        BASE_DIR = Path(os.environ.get("LOCALAPPDATA", str(Path.home()))) / "ClientdeskAI"
else:
    BASE_DIR = Path(__file__).resolve().parent.parent.parent.parent

DATA_DIR = BASE_DIR / "data"
DATABASE_DIR = DATA_DIR / "database"
FILESTORE_DIR = DATA_DIR / "filestore"
BACKUP_DIR = DATA_DIR / "backups"
KNOWLEDGE_DIR = DATA_DIR / "knowledge"

for directory in (DATA_DIR, DATABASE_DIR, FILESTORE_DIR, BACKUP_DIR, KNOWLEDGE_DIR):
    directory.mkdir(parents=True, exist_ok=True)

@dataclass
class AppConfig:
    app_name: str = "Clientdesk AI"
    version: str = "1.1.0"
    deployment_mode: str = "SINGLE_PC"  # 'SINGLE_PC' or 'LAN_CLIENT'
    db_path: Path = DATABASE_DIR / "clientdesk.db"
    filestore_path: Path = FILESTORE_DIR
    backup_path: Path = BACKUP_DIR
    max_upload_size_mb: int = 25
    allowed_file_types: list[str] = field(
        default_factory=lambda: [".pdf", ".xlsx", ".xls", ".docx", ".doc", ".png", ".jpg", ".jpeg", ".csv", ".txt"]
    )
    session_timeout_minutes: int = 60
    max_login_attempts: int = 5
    lockout_duration_minutes: int = 15

CONFIG = AppConfig()
