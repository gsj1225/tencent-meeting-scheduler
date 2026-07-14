#!/usr/bin/env python3
"""使用 SQLite 在线备份 API 创建一致性备份，并清理过期文件。"""
import os
import sqlite3
from datetime import datetime, timedelta
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent
DB_PATH = Path(os.getenv("SCHEDULE_DB_PATH", BASE_DIR / "schedule_data.db"))
BACKUP_DIR = Path(os.getenv("SCHEDULE_BACKUP_DIR", BASE_DIR / "backups"))
RETENTION_DAYS = int(os.getenv("SCHEDULE_BACKUP_RETENTION_DAYS", "30"))

BACKUP_DIR.mkdir(parents=True, exist_ok=True)
target = BACKUP_DIR / ("schedule-" + datetime.now().strftime("%Y%m%d-%H%M%S") + ".db")
with sqlite3.connect(DB_PATH) as source, sqlite3.connect(target) as destination:
    source.backup(destination)

cutoff = datetime.now() - timedelta(days=RETENTION_DAYS)
for old_file in BACKUP_DIR.glob("schedule-*.db"):
    if datetime.fromtimestamp(old_file.stat().st_mtime) < cutoff:
        old_file.unlink()

print(target)
