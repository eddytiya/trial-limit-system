from pathlib import Path
from xml.sax.saxutils import escape
from docx import Document
from docx.text.paragraph import Paragraph as DocParagraph
from docx.table import Table as DocTable
from docx.oxml.ns import qn
from reportlab.platypus import SimpleDocTemplate,Paragraph,Table,TableStyle,PageBreak,Spacer
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
import pypdfium2 as pdfium

OUT=Path(__file__).resolve().parent
source=Document(OUT/'Trial_Limit_System_Development_Summary_2026-10-15.docx')
pdf=OUT/'Trial_Limit_System_Development_Summary_2026-10-15.pdf'
styles={
 'Normal':ParagraphStyle('Body',fontName='Helvetica',fontSize=10,leading=13,spaceAfter=6),
 'Title':ParagraphStyle('Title',fontName='Helvetica-Bold',fontSize=23,leading=27,spaceAfter=10),
 'Subtitle':ParagraphStyle('Subtitle',fontName='Helvetica',fontSize=11,leading=15,spaceAfter=15),
 'Heading 1':ParagraphStyle('Heading',fontName='Helvetica-Bold',fontSize=13,leading=17,spaceBefore=11,spaceAfter=7,keepWithNext=True),
 'Cell':ParagraphStyle('Cell',fontName='Helvetica',fontSize=9,leading=12),
 'Header':ParagraphStyle('Header',fontName='Helvetica-Bold',fontSize=9,leading=12)
}
def text(value):
 return escape(value.replace('\u2013','-').replace('\u2014','-').replace('\u2212','-').replace('\u2019',"'")).replace('\n','<br/>')
story=[]
for element in source.element.body:
 if element.tag==qn('w:p'):
  para=DocParagraph(element,source)
  if any(b.get(qn('w:type'))=='page' for b in element.iter(qn('w:br'))):
   story.append(PageBreak());continue
  if para.text.strip():story.append(Paragraph(text(para.text),styles.get(para.style.name,styles['Normal'])))
 elif element.tag==qn('w:tbl'):
  table=DocTable(element,source)
  rows=[[Paragraph(text(c.text),styles['Header' if i==0 else 'Cell']) for c in r.cells] for i,r in enumerate(table.rows)]
  t=Table(rows,colWidths=[150,60,50,40,187],repeatRows=1,hAlign='LEFT')
  t.setStyle(TableStyle([('BACKGROUND',(0,0),(-1,0),colors.HexColor('#DCE8ED')),
    ('ROWBACKGROUNDS',(0,1),(-1,-1),[colors.white,colors.HexColor('#F4F7F8')]),
    ('GRID',(0,0),(-1,-1),.5,colors.HexColor('#D9D9D9')),('VALIGN',(0,0),(-1,-1),'MIDDLE'),
    ('LEFTPADDING',(0,0),(-1,-1),8),('RIGHTPADDING',(0,0),(-1,-1),8),
    ('TOPPADDING',(0,0),(-1,-1),9),('BOTTOMPADDING',(0,0),(-1,-1),9)]))
  story.extend([t,Spacer(1,10)])
def footer(canvas,doc):
 canvas.setFont('Helvetica',8);canvas.setFillColor(colors.HexColor('#666666'))
 canvas.drawString(54,29,'Trial Limit System | 15 October 2026')
 canvas.drawRightString(A4[0]-54,29,str(doc.page))
SimpleDocTemplate(str(pdf),pagesize=A4,leftMargin=54,rightMargin=54,topMargin=45,bottomMargin=45,
 title='Trial Limit System Development Summary',author='').build(story,onFirstPage=footer,onLaterPages=footer)
qa=OUT/'pdf_qa';qa.mkdir(exist_ok=True)
document=pdfium.PdfDocument(str(pdf))
print('Pages:',len(document))
for i,page in enumerate(document):
 page.render(scale=1.6).to_pil().save(qa/f'page-{i+1}.png')
 print(i+1, page.get_textpage().get_text_range()[:80])
print(pdf)
