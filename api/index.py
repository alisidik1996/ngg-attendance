import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from core.app import create_app  # noqa: E402

app = create_app(serve_static=False, docs_enabled=False)
