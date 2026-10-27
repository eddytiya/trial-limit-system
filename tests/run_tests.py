"""Run the application tests from any working directory."""
import sys
import unittest
from pathlib import Path

PROJECT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT / 'app'))
sys.path.insert(0, str(PROJECT / 'tests'))

if __name__ == '__main__':
    suite = unittest.defaultTestLoader.discover(str(PROJECT / 'tests'), pattern='test_*.py')
    result = unittest.TextTestRunner(verbosity=1).run(suite)
    raise SystemExit(0 if result.wasSuccessful() else 1)
