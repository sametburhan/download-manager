"""
Download Manager Test Suite
Configures an isolated temporary file path for the duration of the test session
to prevent unit tests from polluting the user's actual tasks.json file.
"""

import os
import tempfile

_test_tasks_dir = tempfile.TemporaryDirectory()
os.environ["DOWNLOAD_MANAGER_TASKS_FILE"] = os.path.join(_test_tasks_dir.name, "tasks.json")
