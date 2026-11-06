# -*- coding: utf-8 -*-
"""Generate ops defense speech v6 docx (no cover, plain paragraphs) from ops-defense-v6.md."""
import os, sys, importlib.util, zipfile

BASE = r"D:\SmartOpsAgent\docs\competition"
spec = importlib.util.spec_from_file_location("md2docx", os.path.join(BASE, "_md2docx.py"))
m = importlib.util.module_from_spec(spec)
sys.modules["md2docx"] = m
spec.loader.exec_module(m)

W = 'xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main"'

md = open(os.path.join(BASE, "ops-defense-v6.md"), encoding="utf-8").read()
body = []
for b in m.parse(md):
    body.append(m.block_to_xml(b))

sect = ('<w:sectPr><w:pgSz w:w="11906" w:h="16838"/>'
        '<w:pgMar w:top="1417" w:right="1417" w:bottom="1417" w:left="1417" '
        'w:header="851" w:footer="992" w:gutter="0"/>'
        '<w:cols w:space="425"/><w:docGrid w:linePitch="312"/></w:sectPr>')
document = ('<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
            f'<w:document {W} xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships">'
            f'<w:body>{"".join(body)}{sect}</w:body></w:document>')

ct = ('<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
      '<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">'
      '<Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>'
      '<Default Extension="xml" ContentType="application/xml"/>'
      '<Override PartName="/word/document.xml" ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.document.main+xml"/>'
      '<Override PartName="/word/styles.xml" ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.styles+xml"/>'
      '<Override PartName="/docProps/core.xml" ContentType="application/vnd.openxmlformats-package.core-properties+xml"/>'
      '<Override PartName="/docProps/app.xml" ContentType="application/vnd.openxmlformats-officedocument.extended-properties+xml"/>'
      '</Types>')
rels = ('<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
        '<Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" Target="word/document.xml"/>'
        '</Relationships>')
drels = ('<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
         '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
         '<Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/styles" Target="styles.xml"/>'
         '</Relationships>')
core = ('<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        '<cp:coreProperties xmlns:cp="http://schemas.openxmlformats.org/package/2006/metadata/core-properties" '
        'xmlns:dc="http://purl.org/dc/elements/1.1/" xmlns:dcterms="http://purl.org/dc/terms/" '
        'xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"><dc:title>ops 6分钟答辩（第6版）</dc:title>'
        '<dc:creator>SmartOpsAgent</dc:creator><cp:lastModifiedBy>SmartOpsAgent</cp:lastModifiedBy>'
        '<dcterms:created xsi:type="dcterms:W3CDTF">2026-11-06T00:00:00Z</dcterms:created>'
        '<dcterms:modified xsi:type="dcterms:W3CDTF">2026-11-06T00:00:00Z</dcterms:modified>'
        '</cp:coreProperties>')
app = ('<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
       '<Properties xmlns="http://schemas.openxmlformats.org/officeDocument/2006/extended-properties">'
       '<Application>SmartOpsAgent</Application></Properties>')

out = os.path.join(BASE, "ops 6分钟答辩(6).docx")
with zipfile.ZipFile(out, "w", zipfile.ZIP_DEFLATED) as z:
    z.writestr("[Content_Types].xml", ct)
    z.writestr("_rels/.rels", rels)
    z.writestr("word/document.xml", document)
    z.writestr("word/styles.xml", m.styles_xml())
    z.writestr("word/_rels/document.xml.rels", drels)
    z.writestr("docProps/core.xml", core)
    z.writestr("docProps/app.xml", app)
print("DOCX ->", out, os.path.getsize(out))
