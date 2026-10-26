"""PyInstaller entrypoint. Also works from the unpacked source tree."""
import sys
from pathlib import Path

if not getattr(sys, "frozen", False):
    sys.path.insert(0, str(Path(__file__).resolve().parent / "src"))


def main():
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
    raise SystemExit(main())

