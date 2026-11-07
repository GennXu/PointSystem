"""Optional document build: pip install reportlab; run on Windows with Microsoft JhengHei."""
import html
import json
from pathlib import Path
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.lib import colors
from reportlab.lib.styles import ParagraphStyle
from reportlab.platypus import SimpleDocTemplate, Paragraph, PageBreak
from reportlab.lib.pagesizes import A4

root = Path(__file__).resolve().parent.parent
pages = json.loads((root / 'docs/manual_content.json').read_text(encoding='utf8'))
pdfmetrics.registerFont(TTFont('JhengHei', 'C:/Windows/Fonts/msjh.ttc', subfontIndex=0))
styles = {
    'title': ParagraphStyle('title', fontName='JhengHei', fontSize=24, leading=33, spaceAfter=16),
    'subtitle': ParagraphStyle('subtitle', fontName='JhengHei', fontSize=11, leading=18, textColor=colors.HexColor('#526273'), spaceAfter=17),
    'h': ParagraphStyle('h', fontName='JhengHei', fontSize=14, leading=21, spaceBefore=13, spaceAfter=7),
    'p': ParagraphStyle('p', fontName='JhengHei', fontSize=10.5, leading=17, spaceAfter=8, wordWrap='CJK'),
    'step': ParagraphStyle('step', fontName='JhengHei', fontSize=10.5, leading=17, spaceAfter=9, leftIndent=17, firstLineIndent=-17, wordWrap='CJK'),
    'code': ParagraphStyle('code', fontName='JhengHei', fontSize=9, leading=15, spaceAfter=9, wordWrap='CJK'),
}
story = []
for i, (title, subtitle, blocks) in enumerate(pages):
    if i:
        story.append(PageBreak())
    story.append(Paragraph(html.escape(title), styles['title']))
    story.append(Paragraph(html.escape(subtitle), styles['subtitle']))
    for kind, content in blocks:
        story.append(Paragraph(html.escape(content).replace('\n', '<br/>'), styles[kind]))

def footer(canvas, doc):
    canvas.setFont('JhengHei', 8)
    canvas.setFillColor(colors.HexColor('#687787'))
    canvas.drawString(45, 27, 'QR 點數系統 1.1.0　操作手冊')
    canvas.drawRightString(A4[0]-45, 27, f'{doc.page} / {len(pages)}')

SimpleDocTemplate(str(root / '操作手冊.pdf'), pagesize=A4, rightMargin=45, leftMargin=45, topMargin=43, bottomMargin=45, title='QR 點數系統操作手冊', author='QR Point System').build(story, onFirstPage=footer, onLaterPages=footer)
