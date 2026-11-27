"""Verify side-by-side settings during the 1.0.1 to 2.0 transition."""

from pathlib import Path
from types import SimpleNamespace

from PySide6.QtCore import QSettings
import pytest

from docflow.service import repository
from docflow.ui import diagnostics, settings


@pytest.mark.parametrize('override', [False, True])
def test_stable_major_and_preview_do_not_inherit_auto_resume(tmp_path, monkeypatch, override):
    from docflow.ui.service.workspace import ServiceWorkspace

    if override:
        monkeypatch.setenv('DOCFLOW_SETTINGS_DIR', str(tmp_path / 'shared'))
    else:
        monkeypatch.delenv('DOCFLOW_SETTINGS_DIR')
        monkeypatch.setattr(settings, 'QStandardPaths', SimpleNamespace(
            StandardLocation=SimpleNamespace(AppConfigLocation='config'),
            writableLocation=lambda location: str(tmp_path / location),
        ))
    opened = []
    monkeypatch.setattr(ServiceWorkspace, 'open_project', lambda self, path, **kwargs: opened.append(path))
    states = {}
    for version, project in (('1.0.1', 'original'), ('2.0.0rc1', 'preview-copy'), ('2.0.0', 'stable-copy')):
        monkeypatch.setattr(settings, '__version__', version)
        workspace = ServiceWorkspace()
        assert opened == []
        workspace.close()
        values = settings.preferences()
        values.setValue(settings.LAST_PROJECT_KEY, project)
        values.setValue(settings.RESUME_PROJECT_KEY, True)
        values.sync()
        states[version] = Path(values.fileName())
    assert len(set(states.values())) == 3
    for version, project in (('2.0.0', 'stable-copy'), ('2.0.0rc2', 'preview-copy'), ('1.0.1', 'original')):
        monkeypatch.setattr(settings, '__version__', version)
        workspace = ServiceWorkspace()
        assert opened.pop() == project
        workspace.close()


def test_preview_uses_separate_defaults(tmp_path, monkeypatch):
    monkeypatch.delenv("DOCFLOW_SETTINGS_DIR")
    for name in ("LOCALAPPDATA", "XDG_DATA_HOME", "XDG_STATE_HOME"):
        monkeypatch.setenv(name, str(tmp_path / "local"))
    monkeypatch.setattr(settings, "QStandardPaths", SimpleNamespace(
        StandardLocation=SimpleNamespace(AppConfigLocation="config"),
        writableLocation=lambda location: str(tmp_path / location),
    ))

    def select(version):
        for module in (settings, diagnostics, repository):
            monkeypatch.setattr(module, "__version__", version, raising=False)

    select("1.0.1")
    stable = settings.preferences()
    stable.setValue(settings.LAST_PROJECT_KEY, "stable-project")
    stable.setValue(settings.RESUME_PROJECT_KEY, True)
    stable.sync()
    stable_profile = Path(stable.fileName())
    original = stable_profile.read_bytes()
    stable_log = diagnostics.diagnostic_path()
    stable_default_project = repository.default_root()

    select("2.0.0rc1")
    preview = settings.preferences()
    assert Path(preview.fileName()) != stable_profile
    assert not preview.contains(settings.LAST_PROJECT_KEY)
    preview.setValue(settings.LAST_PROJECT_KEY, "review-copy")
    preview.sync()
    assert preview.value(settings.LAST_PROJECT_KEY) == "review-copy"
    assert diagnostics.diagnostic_path() != stable_log
    assert repository.default_root() != stable_default_project
    assert stable_profile.read_bytes() == original


def test_preview_never_reads_legacy_widths(tmp_path, monkeypatch):
    monkeypatch.setattr(settings, "__version__", "2.0.0rc1", raising=False)
    monkeypatch.setenv("DOCFLOW_SETTINGS_DIR", str(tmp_path / "explicit-qa"))

    def ini_only(*args):
        assert len(args) == 2 and args[1] == QSettings.Format.IniFormat
        return QSettings(*args)

    ini_only.Format = QSettings.Format
    ini_only.Status = QSettings.Status
    monkeypatch.setattr(settings, "QSettings", ini_only)
    assert settings.load_widths("repairs") == {}
    assert settings.save_widths("repairs", {0: 150})
    assert settings.load_widths("repairs") == {0: 150}
