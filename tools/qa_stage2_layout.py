"""Stage2 compact logical client sizes, using the unchanged strict layout checks."""
import argparse,os
from pathlib import Path
import docflow.service.layout_check as layout
from qa_refinement_ui import run
if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--output',type=Path,required=True);args=parser.parse_args()
    scale=float(os.environ.get('QT_SCALE_FACTOR','1'))
    layout.SIZES=tuple((round(w*scale),round(h*scale)) for w,h in ((560,420),(820,620),(1060,740)))
    raise SystemExit(run(args.output))
