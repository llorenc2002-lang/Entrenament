"""Prepare an attached data volume, then run Serra without root privileges."""
import os
import sys
from pathlib import Path

data_dir = Path("/app/data")
data_dir.mkdir(parents=True, exist_ok=True)
os.chown(data_dir, 10001, 10001)
os.setgroups([])
os.setgid(10001)
os.setuid(10001)
os.execv(sys.executable, [sys.executable, "/app/local_training_app.py"])

