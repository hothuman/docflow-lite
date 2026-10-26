"""Diagnostic argument failures preserve existing evidence and do not crash the GUI exe."""
from docflow.service.compatibility_check import main


def test_upgrade_refuses_existing_output_without_unhandled_exception(tmp_path):
    output=tmp_path/'Existing evidence';output.mkdir()
    sentinel=output/'keep.txt';sentinel.write_text('previous evidence')
    assert main(['--archive',str(tmp_path/'missing.zip'),'--output',str(output)])==2
    assert sentinel.read_text()=='previous evidence'
    assert sorted(p.name for p in output.iterdir())==['keep.txt']
