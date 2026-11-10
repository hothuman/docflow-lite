"""Preferred cell widths must not expand a bundled example outside its page."""
from pathlib import Path
from docx import Document
import docflow

def test_example_table_preferred_widths_fit_printable_page():
    for path in (Path(docflow.__file__).parent/'examples').glob('*.docx'):
        document=Document(path);section=document.sections[0]
        printable=section.page_width-section.left_margin-section.right_margin
        for table in document.tables:
            preferred=[column.width or 0 for column in table.columns]
            for row in table.rows:
                for i,cell in enumerate(row.cells):preferred[i]=max(preferred[i],cell.width or 0)
            assert sum(preferred)<=printable+635,path.name
