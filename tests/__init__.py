"""
Download Manager Test Suite
Birim testlerin kullanıcının gerçek tasks.json dosyasını kirletmesini önlemek amacıyla
test oturumu boyunca izole geçici bir dosya yolu tanımlar.
"""

import os
import tempfile

_test_tasks_dir = tempfile.TemporaryDirectory()
os.environ["DOWNLOAD_MANAGER_TASKS_FILE"] = os.path.join(_test_tasks_dir.name, "tasks.json")
