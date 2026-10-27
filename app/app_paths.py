"""Project paths are independent of the terminal working directory."""
from pathlib import Path

APP_DIR = Path(__file__).resolve().parent
PROJECT_DIR = APP_DIR.parent
INPUT_DIR = PROJECT_DIR / 'input'
MAPPED_DIR = PROJECT_DIR / 'mapped'
OUTPUT_DIR = PROJECT_DIR / 'outputs'


def project_path(value):
    path = Path(value)
    return path if path.is_absolute() else PROJECT_DIR / path
