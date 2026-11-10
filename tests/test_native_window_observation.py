"""Startup observation contracts; no Win32/Qt dependency in these simulations."""
import importlib.util
from pathlib import Path
import pytest

spec=importlib.util.spec_from_file_location('bundle_window_observation',Path(__file__).resolve().parents[1]/'scripts/verify_windows_bundle.py')
module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)


class Time:
    value=0.
    def clock(self):return self.value
    def sleep(self,seconds):self.value+=seconds


def test_native_window_recreated_during_startup_uses_settled_identity():
    t=Time();old=(101,'DocFlow Lite QA');new=(202,'DocFlow Lite QA')
    target,history=module.stable_main_window(lambda:(old,) if t.value<.25 else (new,),lambda:True,t.clock,t.sleep)
    assert target==new and t.value>=.75
    assert history[0]['windows']==(old,) and history[-1]['windows']==(new,)


def test_native_transient_missing_window_does_not_count_as_stable():
    t=Time();target,history=module.stable_main_window(lambda:() if t.value<.3 else ((9,'DocFlow Lite QA'),),lambda:True,t.clock,t.sleep)
    assert target[0]==9 and t.value>=.8 and history[0]['windows']==()


@pytest.mark.parametrize('windows',[(),((1,'DocFlow Lite A'),(2,'DocFlow Lite B'))])
def test_native_missing_or_ambiguous_main_window_fails(windows):
    t=Time()
    with pytest.raises(AssertionError,match='stable main window'):
        module.stable_main_window(lambda:windows,lambda:True,t.clock,t.sleep,timeout=1)


def test_native_process_exit_is_not_a_successful_start():
    t=Time()
    with pytest.raises(AssertionError,match='exited early'):
        module.stable_main_window(lambda:((1,'DocFlow Lite QA'),),lambda:t.value<.2,t.clock,t.sleep)
