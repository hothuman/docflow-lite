"""New neutral A4 family only. Never restyles supplied or previously issued files."""
from docx.shared import Pt,Inches,RGBColor
from docx.enum.text import WD_ALIGN_PARAGRAPH
from docx.enum.table import WD_CELL_VERTICAL_ALIGNMENT
from docx.oxml import OxmlElement
from docx.oxml.ns import qn

def refine(document,kind):
    normal=document.styles['Normal'];normal.font.name='Arial';normal.font.size=Pt(11);normal.paragraph_format.space_after=Pt(6);normal.paragraph_format.line_spacing=1.08
    for style in ('Title','Heading 1','Heading 2'):
        value=document.styles[style];value.font.color.rgb=RGBColor(0,0,0);value.font.bold=True;value.paragraph_format.keep_with_next=True
    document.styles['Title'].font.size=Pt(21);document.styles['Title'].paragraph_format.space_after=Pt(12)
    document.styles['Heading 1'].font.size=Pt(12);document.styles['Heading 1'].paragraph_format.space_before=Pt(10)
    for paragraph in document.paragraphs:
        if paragraph.text=='Исполнитель: {{organization_name}}':paragraph.text='{{organization_block}}';paragraph.paragraph_format.space_after=Pt(12)
        if paragraph.text in ('{{organization_details}}','{{organization_contact}}'):paragraph._p.getparent().remove(paragraph._p);continue
        if '{{received_at}}' in paragraph.text:paragraph.text=paragraph.text.replace('{{received_at}}','{{received_date}}')
        if '{{issued_at}}' in paragraph.text:paragraph.text=paragraph.text.replace('{{issued_at}}','{{issued_date}}')
        if '{{estimate_date}}' in paragraph.text:paragraph.text=paragraph.text.replace('{{estimate_date}}','{{estimate_day}}')
        if paragraph.text.startswith('Оборудование:'):paragraph.paragraph_format.space_after=Pt(12)
        if paragraph.text.startswith('Ремонт {{repair_number}}'):paragraph.runs[0].bold=True
        if paragraph.text.startswith('Передал '):
            paragraph.paragraph_format.space_before=Pt(16);paragraph.paragraph_format.keep_together=True
        if paragraph.text.startswith('Проект формы.'):
            for run in paragraph.runs:run.font.size=Pt(9)
        paragraph.paragraph_format.widow_control=True
    # Keep unchanged literal placeholders/markers and repeating item prototypes.
    widths=(.4,2.75,.6,.65,1.25,1.25)
    for table in document.tables:
        for column,width in zip(table.columns,widths):column.width=Inches(width)
        for row_index,row in enumerate(table.rows):
            if row_index:
                trpr=row._tr.get_or_add_trPr();keep=trpr.find(qn('w:cantSplit'))
                if keep is None:keep=OxmlElement('w:cantSplit');trpr.append(keep)
                keep.set(qn('w:val'),'1')
            for i,(cell,width) in enumerate(zip(row.cells,widths)):
                cell.width=Inches(width);cell.vertical_alignment=WD_CELL_VERTICAL_ALIGNMENT.CENTER
                if row_index and i==1 and len(cell.paragraphs)==2:
                    first,second=cell.paragraphs;first.text=first.text+'  '+second.text;second._p.getparent().remove(second._p)
                tcpr=cell._tc.get_or_add_tcPr();margin=OxmlElement('w:tcMar')
                for side in ('top','left','bottom','right'):
                    edge=OxmlElement('w:'+side);edge.set(qn('w:w'),'70');edge.set(qn('w:type'),'dxa');margin.append(edge)
                tcpr.append(margin)
                for paragraph_index,paragraph in enumerate(cell.paragraphs):
                    paragraph.paragraph_format.space_after=Pt(4);paragraph.paragraph_format.line_spacing=1.0
                    # Some editors ignore cantSplit alone. Chain the cells within
                    # a row, but never chain the final cell to the following row.
                    paragraph.paragraph_format.keep_together=True;paragraph.paragraph_format.keep_with_next=i<len(row.cells)-1 or paragraph_index<len(cell.paragraphs)-1
                    keep_lines=paragraph._p.get_or_add_pPr().find(qn('w:keepLines'))
                    if keep_lines is not None:keep_lines.set(qn('w:val'),'1')
                    if i>=4:paragraph.alignment=WD_ALIGN_PARAGRAPH.RIGHT
                    elif i in (0,2,3):paragraph.alignment=WD_ALIGN_PARAGRAPH.CENTER
                    for run in paragraph.runs:run.font.size=Pt(10);run.font.bold=row_index==0
                if row_index==0:
                    for old in list(tcpr.findall(qn('w:shd'))):tcpr.remove(old)
                    shade=OxmlElement('w:shd');shade.set(qn('w:fill'),'E4EBE7');tcpr.append(shade)
