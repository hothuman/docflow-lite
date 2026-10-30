"""PyInstaller entrypoint. Also works from the unpacked source tree."""
import sys
from pathlib import Path

if not getattr(sys, "frozen", False):
    sys.path.insert(0, str(Path(__file__).resolve().parent / "src"))


def main():
    if len(sys.argv)>1 and sys.argv[1]=='--stage3-self-test':
        from docflow.service.stage3_check import main as stage3_check
        return stage3_check(sys.argv[2:])
    if len(sys.argv)>1 and sys.argv[1]=='--stage2-self-test':
        from docflow.service.stage2_check import main as stage2_check
        return stage2_check(sys.argv[2:])
    if len(sys.argv)>1 and sys.argv[1]=='--project-loading-self-test':
        from docflow.service.project_loading_check import main as project_check
        return project_check(sys.argv[2:])
    if len(sys.argv)>1 and sys.argv[1]=='--stage1-self-test':
        from docflow.service.stage1_check import main as stage1_check
        return stage1_check(sys.argv[2:])
    if len(sys.argv) > 1 and sys.argv[1] == "--release-self-test":
        from docflow.release_check import main as check
        return check(sys.argv[2:])
    if len(sys.argv)>1 and sys.argv[1]=='--service-self-test':
        from docflow.service.self_test import main as service_check
        return service_check(sys.argv[2:])
    if len(sys.argv)>1 and sys.argv[1]=='--upgrade-self-test':
        from docflow.service.compatibility_check import main as upgrade_check
        return upgrade_check(sys.argv[2:])
    from docflow.gui import main as gui_main
    return gui_main()


if __name__ == "__main__":
    from multiprocessing import freeze_support
    freeze_support()
    raise SystemExit(main())

