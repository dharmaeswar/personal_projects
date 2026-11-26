"""Tests for the C++17 ingest core (skipped when no C++ compiler)."""

import os
import shutil
import subprocess
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pytest

from replay.ingest import generate_ticks, write_ticks_csv

CPP = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                   "cpp", "ingest_core.cpp")


@pytest.mark.skipif(shutil.which("g++") is None, reason="g++ not available")
def test_cpp_ingest_core_counts_ticks(tmp_path):
    ticks = generate_ticks("ES", 1_000_000, 200, seed=13)
    ticks += generate_ticks("NQ", 1_000_000, 100, seed=14)
    csv_path = str(tmp_path / "ticks.csv")
    write_ticks_csv(csv_path, ticks)
    binary = str(tmp_path / "ingest_core")
    build = subprocess.run(["g++", "-std=c++17", "-O2", CPP, "-o", binary],
                           capture_output=True, text=True)
    assert build.returncode == 0, build.stderr
    run = subprocess.run([binary, csv_path], capture_output=True, text=True)
    assert run.returncode == 0, run.stderr
    assert "rows=300 bad=0" in run.stdout
    assert "ES ticks=200" in run.stdout
    assert "NQ ticks=100" in run.stdout


@pytest.mark.skipif(shutil.which("g++") is None, reason="g++ not available")
def test_cpp_ingest_core_rejects_bad_rows(tmp_path):
    csv_path = str(tmp_path / "bad.csv")
    with open(csv_path, "w") as fh:
        fh.write("ts_ns,symbol,side,price,size\n")
        fh.write("1,ES,T,100.0,5\n")
        fh.write("2,ES,T,-1.0,5\n")
    binary = str(tmp_path / "ingest_core")
    subprocess.run(["g++", "-std=c++17", "-O2", CPP, "-o", binary],
                   check=True, capture_output=True)
    run = subprocess.run([binary, csv_path], capture_output=True, text=True)
    assert run.returncode == 1
    assert "rows=1 bad=1" in run.stdout
