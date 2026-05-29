"""
Performance benchmark for welcome template rendering.
Measures: Run Time, Execution Time, Performance Time
NO changes to existing code. Read-only benchmark.
"""

import sys
import time
import tempfile
import os
from pathlib import Path

# ── Fix module path so app.py can find src/generate_posts ─────────────────────
PROJECT_ROOT = Path(__file__).parent
sys.path.insert(0, str(PROJECT_ROOT))
sys.path.insert(0, str(PROJECT_ROOT / "src"))

# ── Mock streamlit BEFORE importing app.py ─────────────────────────────────────
from unittest.mock import MagicMock

streamlit_mock = MagicMock()
# Ensure st.tabs returns a context-manager-compatible object
class _FakeTab:
    def __enter__(self): return self
    def __exit__(self, *a): pass
    def __iter__(self): return iter([])
streamlit_mock.tabs.return_value = (_FakeTab(), _FakeTab(), _FakeTab())
streamlit_mock.columns.return_value = (_FakeTab(), _FakeTab())
streamlit_mock.expander.return_value = _FakeTab()
streamlit_mock.set_page_config = MagicMock()
streamlit_mock.markdown = MagicMock()
streamlit_mock.file_uploader = MagicMock(return_value=None)
streamlit_mock.text_input = MagicMock(return_value="")
streamlit_mock.slider = MagicMock(return_value=0)
streamlit_mock.button = MagicMock(return_value=False)
streamlit_mock.image = MagicMock()
streamlit_mock.spinner.return_value = _FakeTab()
streamlit_mock.session_state = {}
# cache_resource must be a real pass-through decorator so cached functions
# return actual Image objects (not MagicMock stubs) — otherwise alpha_composite fails.
def _passthrough_cache(fn):
    _store = {}
    def wrapper(*args, **kwargs):
        key = (args, tuple(sorted(kwargs.items())))
        if key not in _store:
            _store[key] = fn(*args, **kwargs)
        return _store[key]
    return wrapper
streamlit_mock.cache_resource = _passthrough_cache
sys.modules["streamlit"] = streamlit_mock
sys.modules["st"] = streamlit_mock

# ── Safety: after app.py is imported, replace save_config with a no-op ────────
# This prevents the benchmark from ever writing mock values back to config.json.
# (app.py's module-level code runs save_config when a "Save" button returns
#  truthy, and a plain MagicMock is truthy — so we must neutralise it.)
def _noop_save(*args, **kwargs):
    pass

# ── Record script start time (Run Time reference) ──────────────────────────────
SCRIPT_START = time.perf_counter()

# ── Import timing ──────────────────────────────────────────────────────────────
print("=" * 65)
print("  WELCOME TEMPLATE PERFORMANCE BENCHMARK")
print("=" * 65)

t0 = time.perf_counter()
from PIL import Image
import json
import io
t_pil = time.perf_counter()
print(f"\n[Import] PIL loaded            : {(t_pil - t0)*1000:>8.1f} ms")

t1 = time.perf_counter()
import app as app_module
t2 = time.perf_counter()
IMPORT_TIME = (t2 - t1) * 1000
print(f"[Import] app.py (full startup) : {IMPORT_TIME:>8.1f} ms")

# Patch out save_config so benchmark runs NEVER write to config.json
app_module.save_config = _noop_save

render_welcome_preview = app_module.render_welcome_preview

# ── Config load timing ─────────────────────────────────────────────────────────
t3 = time.perf_counter()
with open(PROJECT_ROOT / "config.json", "r", encoding="utf-8-sig") as f:
    config = json.load(f)
t4 = time.perf_counter()
CONFIG_LOAD_TIME = (t4 - t3) * 1000
print(f"[Config] config.json loaded    : {CONFIG_LOAD_TIME:>8.1f} ms")

# ── Create a dummy test photo (512x512 solid colour JPEG in memory) ────────────
def make_dummy_photo_file() -> str:
    """Write a 512x512 dummy person photo to a temp file, return its path."""
    img = Image.new("RGB", (512, 512), color=(180, 140, 100))
    tmp = tempfile.NamedTemporaryFile(suffix=".jpg", delete=False)
    img.save(tmp.name, "JPEG")
    tmp.close()
    return tmp.name

dummy_photo = make_dummy_photo_file()

# ── Build people lists for each template ──────────────────────────────────────
TEMPLATE_COUNTS = {
    "welcome_1":  1,
    "welcome_2":  2,
    "welcome_3":  3,
    "welcome_4":  4,
    "welcome_5":  5,
    "welcome_6":  6,
    "welcome_7":  7,
    "welcome_8":  8,
    "welcome_9":  9,
    "welcome_10": 10,
}

SAMPLE_NAMES = [
    "Aarav Shah", "Priya Patel", "Rohan Mehta", "Neha Gupta",
    "Arjun Singh", "Kavya Nair", "Vivek Kumar", "Sneha Joshi",
    "Rahul Verma", "Ananya Reddy",
]
SAMPLE_DES = [
    "Software Engineer", "Product Manager", "Data Analyst",
    "HR Executive", "Marketing Lead", "UX Designer",
    "DevOps Engineer", "QA Tester", "Business Analyst", "Team Lead",
]

def make_people(n: int) -> list:
    return [
        (dummy_photo, SAMPLE_NAMES[i % len(SAMPLE_NAMES)],
         SAMPLE_DES[i % len(SAMPLE_DES)],
         1.0, 0, 0, 0.15)
        for i in range(n)
    ]

# ── Benchmark each template ────────────────────────────────────────────────────
print()
print(f"{'Template':<14} {'n':>2}  {'1st render':>10}  {'2nd render':>10}  {'Result':>16}")
print(f"{'':14} {'':2}  {'(cold)':>10}  {'(cached)':>10}")
print("-" * 60)

results = {}
total_render_start = time.perf_counter()

for key, n in TEMPLATE_COUNTS.items():
    if key not in config.get("templates", {}):
        print(f"{key:<14} {n:>2}  {'SKIP (no config)':>28}")
        continue

    people = make_people(n)

    # PASS 1 — cold cache (first render, overlay computed + cached)
    t_render_start = time.perf_counter()
    try:
        result_img = render_welcome_preview(people, n, config)
        ok = f"{result_img.width}x{result_img.height}"
    except Exception as e:
        ok = f"ERROR: {e}"
    t_render_end = time.perf_counter()
    render_ms = (t_render_end - t_render_start) * 1000

    # PASS 2 — warm cache (overlay already in memory, typical user interaction)
    t_warm_start = time.perf_counter()
    try:
        result_img2 = render_welcome_preview(people, n, config)
    except Exception:
        pass
    t_warm_end = time.perf_counter()
    warm_ms = (t_warm_end - t_warm_start) * 1000

    results[key] = {"n": n, "render_ms": render_ms, "warm_ms": warm_ms, "result": ok}
    print(f"{key:<14} {n:>2}  {render_ms:>9.0f}ms  {warm_ms:>9.0f}ms  {ok:>16}")

total_render_end = time.perf_counter()
TOTAL_RENDER_TIME = (total_render_end - total_render_start) * 1000

# ── Summary ────────────────────────────────────────────────────────────────────
SCRIPT_END = time.perf_counter()
RUN_TIME        = (SCRIPT_END   - SCRIPT_START) * 1000   # wall-clock from script launch
EXECUTION_TIME  = IMPORT_TIME + CONFIG_LOAD_TIME + TOTAL_RENDER_TIME  # functional phases
PERFORMANCE_TIME = TOTAL_RENDER_TIME                       # pure rendering work

print()
print("=" * 65)
print("  PERFORMANCE SUMMARY")
print("=" * 65)
print(f"  Run Time         (total wall-clock)     : {RUN_TIME:>10.1f} ms  ({RUN_TIME/1000:.2f} s)")
print(f"  Execution Time   (import+config+render) : {EXECUTION_TIME:>10.1f} ms  ({EXECUTION_TIME/1000:.2f} s)")
print(f"  Performance Time (render only)          : {PERFORMANCE_TIME:>10.1f} ms  ({PERFORMANCE_TIME/1000:.2f} s)")
print()
print("  Breakdown:")
print(f"    • Library import (app.py)  : {IMPORT_TIME:>10.1f} ms")
print(f"    • Config load              : {CONFIG_LOAD_TIME:>8.1f} ms")
print(f"    • All 10 template renders  : {TOTAL_RENDER_TIME:>8.1f} ms")
if results:
    avg_cold = sum(v["render_ms"] for v in results.values()) / len(results)
    avg_warm = sum(v["warm_ms"] for v in results.values()) / len(results)
    slowest = max(results.items(), key=lambda kv: kv[1]["render_ms"])
    fastest = min(results.items(), key=lambda kv: kv[1]["render_ms"])
    print(f"      – Avg 1st render (cold)  : {avg_cold:>8.1f} ms")
    print(f"      – Avg 2nd+ render (warm) : {avg_warm:>8.1f} ms")
    print(f"      – Slowest cold ({slowest[0]:<10}): {slowest[1]['render_ms']:>8.1f} ms")
    print(f"      – Fastest cold ({fastest[0]:<10}): {fastest[1]['render_ms']:>8.1f} ms")
print("=" * 65)

# ── Cleanup temp file ──────────────────────────────────────────────────────────
os.unlink(dummy_photo)
