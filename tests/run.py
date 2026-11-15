"""Run every test_* function without pytest: python3 tests/run.py"""
import importlib.util
import os
import sys
import traceback

here = os.path.dirname(os.path.abspath(__file__))
failed = passed = 0
for name in sorted(os.listdir(here)):
    if not (name.startswith("test_") and name.endswith(".py")):
        continue
    spec = importlib.util.spec_from_file_location(name[:-3], os.path.join(here, name))
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    for fn in [getattr(mod, f) for f in dir(mod) if f.startswith("test_")]:
        try:
            fn()
            passed += 1
        except Exception:
            failed += 1
            print("FAIL", name, fn.__name__)
            traceback.print_exc()
print("{} passed, {} failed".format(passed, failed))
sys.exit(1 if failed else 0)
