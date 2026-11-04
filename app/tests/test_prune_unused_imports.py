from app.utils.imports import prune_unused_imports


def test_drops_unused_names_and_keeps_used_ones():
    src = "from typing import List, Optional\nimport os\n\nx: List[int] = []\n"
    assert prune_unused_imports(src) == "from typing import List\n\nx: List[int] = []\n"


def test_removes_a_fully_unused_statement():
    assert prune_unused_imports("import os\nimport sys\n\nprint(sys.argv)\n") == "import sys\n\nprint(sys.argv)\n"


def test_keeps_names_used_in_string_annotations():
    src = 'from datetime import datetime\n\ndef f(x: "datetime") -> None:\n    pass\n'
    assert prune_unused_imports(src) == src


def test_keeps_dotted_import_root_and_relative_imports():
    src = "import os.path\nfrom .email import notify\n\nos.getcwd()\nnotify()\n"
    assert prune_unused_imports(src) == src


def test_handles_multiline_and_aliases():
    src = "from a import (\n    b,\n    c as d,\n    e,\n)\n\nprint(d)\n"
    assert prune_unused_imports(src) == "from a import c as d\n\nprint(d)\n"


def test_leaves_future_and_star_imports_alone():
    src = "from __future__ import annotations\nfrom m import *\n"
    assert prune_unused_imports(src) == src


def test_unparseable_source_is_returned_unchanged():
    assert prune_unused_imports("def (:\n") == "def (:\n"


def test_a_name_mentioned_only_in_a_docstring_is_not_a_use():
    src = 'from m import notify\n\n\ndef f():\n    """Reports what notify() returns."""\n'
    assert "import" not in prune_unused_imports(src)
