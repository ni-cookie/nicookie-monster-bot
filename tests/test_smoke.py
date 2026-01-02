import pytest
from src.config import TIMEZONE

def test_timezone_config():
    """Проверяем, что таймзона задана корректно"""
    assert TIMEZONE == "Europe/Kyiv"

def test_basic_math():
    """Проверка на адекватность CI раннера"""
    assert 2 + 2 == 4