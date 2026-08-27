# -*- coding: utf-8 -*-
"""A tiny, dependency-free .xlsx writer (an .xlsx is just a zip of XML parts).

TypeR ships with the Python standard library only — no openpyxl/pandas — so this
hand-rolls the minimal Office Open XML a spreadsheet app (Excel, LibreOffice,
Google Sheets) needs to open the file: one worksheet, a bold + frozen header
row, string and number cells, and column widths. Strings are written inline, so
there is no shared-strings table to keep in sync.

Public API: ``write_xlsx(path, sheet_name, headers, rows, widths=None)``.
"""

import zipfile


def _col_letter(n):
    """0-based column index -> spreadsheet column letters (0->A, 26->AA)."""
    s = ""
    n += 1
    while n:
        n, r = divmod(n - 1, 26)
        s = chr(65 + r) + s
    return s


def _esc(text):
    return (str(text).replace("&", "&amp;").replace("<", "&lt;")
            .replace(">", "&gt;"))


def _cell(col, row, value, style=None):
    ref = "%s%d" % (_col_letter(col), row)
    s = ' s="%d"' % style if style else ""
    # numbers (but not bools) become numeric cells; everything else is text
    if isinstance(value, bool):
        value = str(value)
    elif isinstance(value, (int, float)):
        return '<c r="%s"%s><v>%s</v></c>' % (ref, s, value)
    if value is None:
        value = ""
    return ('<c r="%s"%s t="inlineStr"><is><t xml:space="preserve">%s</t>'
            '</is></c>' % (ref, s, _esc(value)))


_CONTENT_TYPES = (
    '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
    '<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">'
    '<Default Extension="rels" ContentType="application/vnd.openxmlformats-'
    'package.relationships+xml"/>'
    '<Default Extension="xml" ContentType="application/xml"/>'
    '<Override PartName="/xl/workbook.xml" ContentType="application/vnd.'
    'openxmlformats-officedocument.spreadsheetml.sheet.main+xml"/>'
    '<Override PartName="/xl/worksheets/sheet1.xml" ContentType="application/'
    'vnd.openxmlformats-officedocument.spreadsheetml.worksheet+xml"/>'
    '<Override PartName="/xl/styles.xml" ContentType="application/vnd.'
    'openxmlformats-officedocument.spreadsheetml.styles+xml"/></Types>')

_ROOT_RELS = (
    '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
    '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/'
    'relationships"><Relationship Id="rId1" Type="http://schemas.openxml'
    'formats.org/officeDocument/2006/relationships/officeDocument" '
    'Target="xl/workbook.xml"/></Relationships>')

_WB_RELS = (
    '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
    '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/'
    'relationships"><Relationship Id="rId1" Type="http://schemas.openxml'
    'formats.org/officeDocument/2006/relationships/worksheet" '
    'Target="worksheets/sheet1.xml"/><Relationship Id="rId2" Type="http://'
    'schemas.openxmlformats.org/officeDocument/2006/relationships/styles" '
    'Target="styles.xml"/></Relationships>')

# two fonts (normal + bold); the header row uses cellXfs index 1 (bold)
_STYLES = (
    '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
    '<styleSheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/'
    'main"><fonts count="2"><font><sz val="11"/><name val="Calibri"/></font>'
    '<font><b/><sz val="11"/><name val="Calibri"/></font></fonts>'
    '<fills count="2"><fill><patternFill patternType="none"/></fill>'
    '<fill><patternFill patternType="gray125"/></fill></fills>'
    '<borders count="1"><border/></borders>'
    '<cellStyleXfs count="1"><xf/></cellStyleXfs>'
    '<cellXfs count="2"><xf/><xf fontId="1" applyFont="1"/></cellXfs>'
    '<cellStyles count="1"><cellStyle name="Normal" xfId="0" builtinId="0"/>'
    '</cellStyles></styleSheet>')


def _freeze_pane(freeze_rows, freeze_cols):
    if not freeze_rows and not freeze_cols:
        return ""
    attrs = []
    if freeze_cols:
        attrs.append('xSplit="%d"' % freeze_cols)
    if freeze_rows:
        attrs.append('ySplit="%d"' % freeze_rows)
    top = "%s%d" % (_col_letter(freeze_cols), freeze_rows + 1)
    pane = ("bottomRight" if freeze_rows and freeze_cols
            else "bottomLeft" if freeze_rows else "topRight")
    attrs.append('topLeftCell="%s"' % top)
    attrs.append('activePane="%s"' % pane)
    return '<pane %s state="frozen"/>' % " ".join(attrs)


def write_xlsx(path, sheet_name, headers, rows, widths=None,
               freeze_rows=1, freeze_cols=0):
    """Write a single-sheet .xlsx to `path`.

    sheet_name:  the worksheet tab name.
    headers:     list of column titles (rendered as a bold, frozen first row).
    rows:        list of rows, each a list of cell values (str / int / float).
    widths:      optional list of column widths (in Excel width units).
    freeze_rows: header rows to freeze at the top (default 1).
    freeze_cols: leading columns to freeze on the left (e.g. 1 keeps the
                 character column visible while scrolling right).
    """
    wb = ('<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
          '<workbook xmlns="http://schemas.openxmlformats.org/spreadsheetml/'
          '2006/main" xmlns:r="http://schemas.openxmlformats.org/office'
          'Document/2006/relationships"><sheets><sheet name="%s" sheetId="1" '
          'r:id="rId1"/></sheets></workbook>' % _esc(sheet_name)[:31])

    cols_xml = ""
    if widths:
        parts = ['<cols>']
        for i, w in enumerate(widths):
            parts.append('<col min="%d" max="%d" width="%.1f" customWidth="1"/>'
                         % (i + 1, i + 1, w))
        parts.append('</cols>')
        cols_xml = "".join(parts)

    body = ['<row r="1">']
    for c, h in enumerate(headers):
        body.append(_cell(c, 1, h, style=1))
    body.append('</row>')
    for ri, row in enumerate(rows, start=2):
        body.append('<row r="%d">' % ri)
        for c, val in enumerate(row):
            body.append(_cell(c, ri, val))
        body.append('</row>')

    sheet = ('<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
             '<worksheet xmlns="http://schemas.openxmlformats.org/spreadsheet'
             'ml/2006/main"><sheetViews><sheetView workbookViewId="0">'
             + _freeze_pane(freeze_rows, freeze_cols)
             + '</sheetView></sheetViews>' + cols_xml
             + '<sheetData>' + "".join(body) + '</sheetData></worksheet>')

    with zipfile.ZipFile(path, "w", zipfile.ZIP_DEFLATED) as z:
        z.writestr("[Content_Types].xml", _CONTENT_TYPES)
        z.writestr("_rels/.rels", _ROOT_RELS)
        z.writestr("xl/workbook.xml", wb)
        z.writestr("xl/_rels/workbook.xml.rels", _WB_RELS)
        z.writestr("xl/styles.xml", _STYLES)
        z.writestr("xl/worksheets/sheet1.xml", sheet)
