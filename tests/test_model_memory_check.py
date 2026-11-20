import importlib.util
from pathlib import Path
import pytest


def load_check_module():
    path = Path("scripts/check_model_memory.py")
    spec = importlib.util.spec_from_file_location("model_memory_check", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_model_size_parser_supports_gib_and_mib():
    module = load_check_module()
    assert module.parse_ollama_size("2.5 GB") == 2.5 * 1024**3
    assert module.parse_ollama_size("1.4 GB") == pytest.approx(1.4 * 1024**3)
    assert module.parse_ollama_size("512 MB") == pytest.approx(512 * 1024**2)
