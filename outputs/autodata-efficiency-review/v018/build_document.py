"""Build an editable Word document and a readable HTML copy from Markdown."""
from pathlib import Path
from zipfile import ZipFile, ZIP_DEFLATED
import xml.etree.ElementTree as E
import markdown
P=Path(__file__).resolve().parent
stem='AutoData入门说明'
text=(P/(stem+'.md')).read_text()
body=markdown.markdown(text,extensions=['tables'])
css='body{background:#f0f3f7;color:#233345;font:18px/1.95 system-ui,sans-serif;margin:0}main{background:white;max-width:860px;margin:32px auto;padding:48px 64px}h1{font-size:30px;line-height:1.4}h2{font-size:23px;color:#176b78;margin-top:38px}table{border-collapse:collapse;width:100%;font-size:16px;line-height:1.7}th,td{border:1px solid #d5dde5;padding:12px;text-align:left}th{background:#edf4f6}li{margin:8px 0}@media(max-width:700px){main{margin:0;padding:24px}table{font-size:14px}th,td{padding:6px}}@media print{body{background:white}main{margin:0;padding:0}h2{break-after:avoid}tr{break-inside:avoid}}'
(P/(stem+'.html')).write_text('<!doctype html><html lang="zh-CN"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>AutoData 数据生成系统入门说明</title><style>'+css+'</style><main>'+body+'</main></html>')
W='http://schemas.openxmlformats.org/wordprocessingml/2006/main'
E.register_namespace('w',W)
def sub(parent,tag,attrs=None,text=None):
    n=E.SubElement(parent,'{'+W+'}'+tag,{'{'+W+'}'+k:str(v) for k,v in (attrs or {}).items()})
    if text is not None:n.text=text
    return n
def run(p,txt,bold=False):
    if not txt:return
    r=sub(p,'r')
    if bold:sub(sub(r,'rPr'),'b')
    t=sub(r,'t',text=txt);t.set('{http://www.w3.org/XML/1998/namespace}space','preserve')
def inline(p,node,bold=False):
    run(p,node.text,bold)
    for c in node:
        inline(p,c,bold or c.tag in ['strong','th'])
        run(p,c.tail,bold)
def paragraph(parent,node,style=None,prefix=''):
    p=sub(parent,'p')
    if style:sub(sub(p,'pPr'),'pStyle',{'val':style})
    run(p,prefix);inline(p,node)
    return p
root=E.Element('{'+W+'}document');b=sub(root,'body')
for node in E.fromstring('<root>'+body+'</root>'):
    if node.tag in ['h1','h2','p']:
        paragraph(b,node,{'h1':'Title','h2':'Heading1'}.get(node.tag))
    elif node.tag in ['ol','ul']:
        for i,li in enumerate(node,1):paragraph(b,li,prefix=f'{i}. ' if node.tag=='ol' else '• ')
    elif node.tag=='table':
        table=sub(b,'tbl');pr=sub(table,'tblPr');sub(pr,'tblW',{'w':0,'type':'auto'})
        borders=sub(pr,'tblBorders')
        for edge in ['top','left','bottom','right','insideH','insideV']:sub(borders,edge,{'val':'single','sz':4,'color':'CBD5DF'})
        for row in node.findall('.//tr'):
            tr=sub(table,'tr');sub(sub(tr,'trPr'),'cantSplit')
            if row[0].tag=='th':sub(tr.find('{'+W+'}trPr'),'tblHeader')
            for cell in row:
                tc=sub(tr,'tc');pr=sub(tc,'tcPr');sub(pr,'tcW',{'w':int(9000/len(row)),'type':'dxa'})
                if cell.tag=='th':sub(pr,'shd',{'fill':'EDF4F6'})
                paragraph(tc,cell,style='TableText')
        sub(b,'p')
sect=sub(b,'sectPr');sub(sect,'pgSz',{'w':11906,'h':16838});sub(sect,'pgMar',{'top':1200,'right':1250,'bottom':1200,'left':1250,'header':500,'footer':500})
styles=E.Element('{'+W+'}styles');defaults=sub(styles,'docDefaults');rp=sub(sub(defaults,'rPrDefault'),'rPr');sub(rp,'rFonts',{'ascii':'Calibri','hAnsi':'Calibri','eastAsia':'Microsoft YaHei'});sub(rp,'sz',{'val':22});sub(rp,'lang',{'val':'zh-CN','eastAsia':'zh-CN'})
pp=sub(sub(defaults,'pPrDefault'),'pPr');sub(pp,'spacing',{'after':150,'line':330,'lineRule':'auto'})
for sid,size,color in [('Normal',22,'233345'),('Title',36,'233345'),('Heading1',28,'176B78'),('TableText',20,'233345')]:
    s=sub(styles,'style',{'type':'paragraph','styleId':sid});sub(s,'name',{'val':sid});ppr=sub(s,'pPr')
    if sid in ['Title','Heading1']:
        sub(ppr,'keepNext');sub(ppr,'spacing',{'before':260,'after':160});sub(ppr,'outlineLvl',{'val':0 if sid=='Heading1' else 9})
    rp=sub(s,'rPr');sub(rp,'sz',{'val':size});sub(rp,'color',{'val':color})
    if sid in ['Title','Heading1']:sub(rp,'b')
xml=lambda r:E.tostring(r,encoding='utf-8',xml_declaration=True)
with ZipFile(P/(stem+'.docx'),'w',ZIP_DEFLATED) as z:
    z.writestr('[Content_Types].xml','<?xml version="1.0"?><Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types"><Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/><Default Extension="xml" ContentType="application/xml"/><Override PartName="/word/document.xml" ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.document.main+xml"/><Override PartName="/word/styles.xml" ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.styles+xml"/></Types>')
    z.writestr('_rels/.rels','<?xml version="1.0"?><Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships"><Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" Target="word/document.xml"/></Relationships>')
    z.writestr('word/_rels/document.xml.rels','<?xml version="1.0"?><Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships"><Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/styles" Target="styles.xml"/></Relationships>')
    z.writestr('word/document.xml',xml(root));z.writestr('word/styles.xml',xml(styles))
# Check that every paragraph and table cell has survived conversion.
word_text=''.join(root.itertext())
for n in E.fromstring('<root>'+body+'</root>').iter():
    if n.tag in ['p','h1','h2','td','th','li']:
        assert ''.join(n.itertext()) in word_text,n.tag
with ZipFile(P/(stem+'.docx')) as z:
    assert z.testzip() is None
    for name in z.namelist():E.fromstring(z.read(name))
print('Word and HTML generated; all paragraphs and table cells verified.')
