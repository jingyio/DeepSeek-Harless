"""Author four small Word/image/text fixture sets with the bundled Python runtime."""
from pathlib import Path
import argparse
from docx import Document
from docx.shared import Inches, Pt, RGBColor
from PIL import Image, ImageDraw

def main():
    p=argparse.ArgumentParser(); p.add_argument('--output',type=Path,required=True); args=p.parse_args()
    for i,variant in enumerate(('a','b','c','d','e')):
        out=args.output/variant; out.mkdir(parents=True,exist_ok=False)
        project=('Orion','Willow','Harbor','Cedar','Aurora')[i]
        doc=Document(); section=doc.sections[0]
        section.top_margin=section.bottom_margin=Inches(.8)
        for border in doc.styles.element.xpath('.//w:pBdr'):
            border.getparent().remove(border)
        for name in ('Normal','Title','Heading 1'):
            doc.styles[name].font.name='Arial'; doc.styles[name].font.color.rgb=RGBColor(0,0,0)
        doc.styles['Normal'].font.size=Pt(11)
        doc.add_paragraph(f'{project} research project',style='Title')
        doc.add_paragraph(f'The {project} team studies reusable execution graphs and file indexing. '
                          'The research meeting will compare workflow learning with ordinary scripts.')
        doc.add_paragraph('Next actions',style='Heading 1')
        doc.add_paragraph(f'Prepare {3+i} document examples. Check parameter provenance. '
                          'Keep final scientific judgments separate from file integrity checks.')
        doc.save(out/'brief.docx')
        (out/'minutes.txt').write_text(f'{project} research meeting\nTopic: execution graphs and workflow reuse.\n'
                                     f'Action: prepare {3+i} indexed files.\n',encoding='utf-8')
        (out/'invoice.txt').write_text(f'Administration invoice\nProject: {project}\nAmount: {120+i*35}\n'
                                     'Office supplies and travel reimbursement.\n',encoding='utf-8')
        (out/'notes.md').write_text(f'# {project} reference notes\nResearch on graph learning and tool execution.\n'
                                  'The generated examples are for file management experiments.\n',encoding='utf-8')
        image=Image.new('RGB',(640+i*40,360+i*20),'#eef3f6'); draw=ImageDraw.Draw(image)
        draw.rectangle((24,24,image.width-24,image.height-24),outline='#29475f',width=3)
        draw.text((48,60),f'{project} team event',fill='#132b3e')
        draw.text((48,100),f'Workshop room {i+1}',fill='#132b3e')
        image.save(out/'poster.png')
        (out/'empty.txt').write_text('',encoding='utf-8')
        if variant in ('d','e'):
            from reportlab.pdfgen import canvas
            pdf=canvas.Canvas(str(out/'paper.pdf'));pdf.setTitle(f'{project} file workflow study')
            pdf.setFont('Helvetica-Bold',18);pdf.drawString(60,760,f'{project} file workflow study')
            pdf.setFont('Helvetica',11)
            for y,line in enumerate(('Research topic: execution graphs and file indexing.',
                                     'Method: compare repeated workflow handling with scripts.',
                                     'This generated document is an experimental file fixture.')):
                pdf.drawString(60,710-y*24,line)
            pdf.save()
    print('Authored five Word/image/text sets and two held-out PDF fixtures.')

if __name__=='__main__': main()
