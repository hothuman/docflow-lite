"""Print family7, independent of SQLite schema6. Only newly requested defaults."""
from docx.shared import Mm,Pt,RGBColor,Twips
from docx.oxml import OxmlElement
from docx.oxml.ns import qn


def refine(document):
    section=document.sections[0]
    section.page_width=Mm(210);section.page_height=Mm(297)
    section.left_margin=section.right_margin=Mm(17)
    section.top_margin=section.bottom_margin=Mm(17)
    section.header_distance=section.footer_distance=Mm(8)
    normal=document.styles['Normal'];normal.font.size=Pt(11)
    normal.paragraph_format.line_spacing=1.05;normal.paragraph_format.space_after=Pt(5)
    document.styles['Title'].font.size=Pt(18)
    document.styles['Title'].paragraph_format.space_after=Pt(10)
    for style in ('Normal','Title','Heading 1','Heading 2'):
        p=document.styles[style];p.font.color.rgb=RGBColor(0,0,0)
        lang=OxmlElement('w:lang');lang.set(qn('w:val'),'ru-RU');p.element.get_or_add_rPr().append(lang)
    widths=(11,76,14,14,30,31)  #176mm; the number column fits four digits.
    printable=(section.page_width-section.left_margin-section.right_margin)//635
    ticks=[round(Mm(value)/635) for value in widths[:-1]]
    widths=[Twips(value) for value in [*ticks,printable-sum(ticks)]]
    for table in document.tables:
        table.autofit=False
        tblw=table._tbl.tblPr.find(qn('w:tblW'))
        tblw.set(qn('w:type'),'dxa');tblw.set(qn('w:w'),str(printable))
        for column,width in zip(table.columns,widths):column.width=width
        for row in table.rows:
            for cell,width in zip(row.cells,widths):
                cell.width=width
                for paragraph in cell.paragraphs:
                    paragraph.paragraph_format.space_before=Pt(2);paragraph.paragraph_format.space_after=Pt(2)
                    for run in paragraph.runs:run.font.size=Pt(10)
    # The established signature/context chain and row safety flags remain.
    # A renderer may still split an oversized row; do not force page breaks.
