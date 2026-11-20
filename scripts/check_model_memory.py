#!/usr/bin/env python3
"""Check whether an Ollama model size fits the laptop's available memory."""

from __future__ import annotations

import os
import re
import shutil
import subprocess
import sys
from pathlib import Path


GIB = 1024 ** 3


def read_available_memory_bytes() -> tuple[int, int]:
    if not Path("/proc/meminfo").exists():
        raise RuntimeError("This check requires Linux /proc/meminfo")

    values: dict[str, int] = {}
    for line in Path("/proc/meminfo").read_text(encoding="utf-8").splitlines():
        if ":" not in line:
            continue
        key, raw = line.split(":", 1)
        match = re.search(r"(\d+)\s*kB", raw)
        if match:
            values[key] = int(match.group(1)) * 1024

    total = values.get("MemTotal", 0)
    available = values.get("MemAvailable", values.get("MemFree", 0))
    if not total or not available:
        raise RuntimeError("Could not determine system memory")
    return total, available


def parse_ollama_size(value: str) -> int | None:
    match = re.fullmatch(r"\s*([\d.]+)\s*(B|KB|MB|GB|TB)\s*", value.strip(), re.I)
    if not match:
        return None
    amount = float(match.group(1))
    unit = match.group(2).upper()
    factor = {
        "B": 1,
        "KB": 1024,
        "MB": 1024 ** 2,
        "GB": 1024 ** 3,
        "TB": 1024 ** 4,
    }[unit]
    return int(amount * factor)


def format_bytes(value: int) -> str:
    if value >= GIB:
        return f"{value / GIB:.1f} GiB"
    return f"{value / (1024 ** 2):.1f} MiB"


def main() -> int:
    model = sys.argv[1] if len(sys.argv) > 1 else os.getenv("OLLAMA_MODEL", "qwen3:4b")

    if not shutil.which("ollama"):
        print("FAIL: Ollama is not installed or not in PATH.")
        print("Run 'make install-ollama' on the Linux Mint laptop.")
        return 2

    try:
        total, available = read_available_memory_bytes()
    except RuntimeError as exc:
        print(f"FAIL: {exc}")
        return 2

    try:
        result = subprocess.run(
            ["ollama", "list"],
            check=True,
            capture_output=True,
            text=True,
            timeout=15,
        )
    except subprocess.TimeoutExpired:
        print("FAIL: 'ollama list' timed out.")
        return 2
    except subprocess.CalledProcessError as exc:
        detail = exc.stderr.strip() or "Ollama is unavailable"
        print(f"FAIL: {detail}")
        return 2

    model_row = None
    size_column_index = None
    lines = result.stdout.strip().splitlines()
    if lines:
        header = lines[0].lower().split()
        for index, column in enumerate(header):
            if column == "size":
                size_column_index = index
                break
    for line in lines[1:] if len(lines) > 1 else lines:
        columns = line.split()
        if not columns:
            continue
        if columns[0] == model or columns[0].startswith(model + ":"):
            model_row = columns
            break

    print(f"Model requested: {model}")
    print(f"Physical RAM: {format_bytes(total)}")
    print(f"Currently available: {format_bytes(available)}")

    if model_row is None:
        print("NOT INSTALLED: Pull the model before memory can be measured:")
        print(f"  ollama pull {model}")
        return 1

    if size_column_index is None:
        size_column_index = 2
    if size_column_index + 1 < len(model_row):
        size_text = f"{model_row[size_column_index]} {model_row[size_column_index + 1]}"
    else:
        size_text = model_row[size_column_index] if size_column_index < len(model_row) else ""
    if not size_text:
        print("UNKNOWN: Ollama did not provide a parseable model size.")
        print("  ollama list")
        return 1
    model_size = parse_ollama_size(size_text)
    if model_size is None:
        print(f"UNKNOWN: Could not parse Ollama size '{size_text}'.")
        print("  ollama list")
        return 1

    # Ollama also needs runtime/KV-cache workspace. 25% adds a conservative
    # estimate for the process and context beyond the serialized model size.
    estimated_runtime = int(model_size * 1.25)

    print(f"Ollama model size: {format_bytes(model_size)}")
    print(f"Conservative runtime estimate: {format_bytes(estimated_runtime)}")

    if estimated_runtime > available:
        print("RESULT: Likely TOO LARGE for the memory currently available.")
        print("Recommended fallback:")
        print("  ollama pull qwen3:1.7b")
        print("  Set OLLAMA_MODEL=qwen3:1.7b in .env")
        print("  Run this check again")
        return 1

    if estimated_runtime > available * 0.60:
        print("RESULT: It may fit, but memory pressure is likely.")
        print("Use qwen3:1.7b if free RAM stays low or inference is slow.")
        return 0

    print("RESULT: Model has enough available memory under this estimate.")
    print("It can still be constrained by other running processes.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
