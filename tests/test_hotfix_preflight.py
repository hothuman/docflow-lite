from docflow.service import hotfix_check, stage8_check


def test_clean_portable_missing_fixtures_has_no_side_effects(tmp_path, monkeypatch, capsys):
    monkeypatch.setattr(stage8_check, 'samples_root', lambda: tmp_path / 'absent')
    output = tmp_path / 'fresh-qa'
    assert hotfix_check.main(['--output', str(output)]) == 2
    assert list(tmp_path.iterdir()) == []
    assert '--fixtures PATH' in capsys.readouterr().err


def test_incomplete_explicit_fixtures_are_rejected_before_qa_starts(tmp_path, capsys):
    fixtures = tmp_path / 'partial'
    fixtures.mkdir()
    (fixtures / 'journal-qa.xlsx').write_bytes(b'')
    output = tmp_path / 'fresh-qa'
    assert hotfix_check.main(['--output', str(output), '--fixtures', str(fixtures)]) == 2
    assert not output.exists()
    assert 'journal-qa.xlsx' in capsys.readouterr().err
