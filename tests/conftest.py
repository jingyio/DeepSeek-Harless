"""Tests create private temporary fixtures without needing existing run data."""
from pathlib import Path


def pytest_sessionstart(session):
    (Path(__file__).resolve().parents[1] / '.local').mkdir(exist_ok=True)
