import sys

_original_stdout = sys.stdout


def pytest_runtest_teardown(item, nextitem):
    if sys.stdout is not _original_stdout:
        sys.stdout = _original_stdout
