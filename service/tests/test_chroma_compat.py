from unittest.mock import Mock

import pytest
from app.services import chroma_compat


@pytest.fixture
def loader(monkeypatch):
    chroma_compat.load_chroma_bindings.cache_clear()
    monkeypatch.setattr(chroma_compat.sys, "platform", "linux")
    monkeypatch.setattr(chroma_compat.platform, "machine", lambda: "x86_64")
    get_affinity = Mock(return_value={2, 4})
    set_affinity = Mock()
    monkeypatch.setattr(
        chroma_compat.os, "sched_getaffinity", get_affinity, raising=False
    )
    monkeypatch.setattr(
        chroma_compat.os, "sched_setaffinity", set_affinity, raising=False
    )
    yield get_affinity, set_affinity
    chroma_compat.load_chroma_bindings.cache_clear()


@pytest.mark.parametrize("fails", [False, True])
def test_import_restores_thread_affinity_even_on_failure(loader, monkeypatch, fails):
    _, set_affinity = loader

    def import_bindings(name):
        assert name == "chromadb_rust_bindings"
        set_affinity.assert_called_once_with(0, {2})
        if fails:
            raise ImportError("native library unavailable")

    monkeypatch.setattr(chroma_compat, "import_module", import_bindings)
    if fails:
        with pytest.raises(ImportError, match="native library unavailable"):
            chroma_compat.load_chroma_bindings()
    else:
        chroma_compat.load_chroma_bindings()
        chroma_compat.load_chroma_bindings()
    assert set_affinity.call_args_list == [((0, {2}),), ((0, {2, 4}),)]


@pytest.mark.parametrize(
    "system, machine", [("darwin", "x86_64"), ("linux", "aarch64")]
)
def test_other_platforms_import_without_changing_affinity(
    loader, monkeypatch, system, machine
):
    get_affinity, set_affinity = loader
    monkeypatch.setattr(chroma_compat.sys, "platform", system)
    monkeypatch.setattr(chroma_compat.platform, "machine", lambda: machine)
    import_bindings = Mock()
    monkeypatch.setattr(chroma_compat, "import_module", import_bindings)
    chroma_compat.load_chroma_bindings()
    import_bindings.assert_called_once_with("chromadb_rust_bindings")
    get_affinity.assert_not_called()
    set_affinity.assert_not_called()


def test_restricted_container_keeps_normal_import_behavior(loader, monkeypatch):
    _, set_affinity = loader
    set_affinity.side_effect = PermissionError(1, "not permitted")
    import_bindings = Mock()
    monkeypatch.setattr(chroma_compat, "import_module", import_bindings)
    chroma_compat.load_chroma_bindings()
    import_bindings.assert_called_once_with("chromadb_rust_bindings")
    set_affinity.assert_called_once_with(0, {2})
