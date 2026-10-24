import pytest

from utils import file_search


@pytest.fixture
def tree(tmp_path, monkeypatch):
    (tmp_path / "docs").mkdir()
    (tmp_path / "docs" / "Report.txt").write_text("x")
    (tmp_path / "docs" / "report_old.txt").write_text("x")
    (tmp_path / "node_modules" / "pkg").mkdir(parents=True)
    (tmp_path / "node_modules" / "pkg" / "Report.txt").write_text("x")
    (tmp_path / ".git").mkdir()
    (tmp_path / ".git" / "Report.txt").write_text("x")
    monkeypatch.setattr(file_search, "search_roots", lambda: [tmp_path])
    return tmp_path


def test_exact_match_case_insensitive(tree):
    hits = file_search.search("REPORT.TXT", want="file")
    assert hits[0].endswith("Report.txt")


def test_skips_junk_folders(tree):
    assert all("node_modules" not in h and ".git" not in h for h in file_search.search("report", want="file"))


def test_partial_and_exact_flags(tree):
    assert len(file_search.search("report", want="file")) == 2
    assert file_search.search("report", want="file", exact=True) == []


def test_folder_search(tree):
    assert file_search.search("docs", want="folder", exact=True)


def test_limit_and_empty_query(tree):
    assert len(file_search.search("report", want="file", limit=1)) == 1
    assert file_search.search("  ") == []


def test_respects_time_budget(tree, monkeypatch):
    monkeypatch.setattr(file_search, "MAX_SECONDS", -1)
    assert file_search.search("zzz", want="file") == []


def test_depth_limit(tree, monkeypatch):
    deep = tree
    for i in range(10):
        deep = deep / f"d{i}"
    deep.mkdir(parents=True)
    (deep / "deepfile.txt").write_text("x")
    assert file_search.search("deepfile.txt", want="file") == []


def test_real_roots_are_existing_directories():
    import importlib
    importlib.reload(file_search)
    assert all(r.is_dir() for r in file_search.search_roots())
