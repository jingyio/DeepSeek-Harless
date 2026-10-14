"""Conservative geometry repair of wide prose blocks with a persistent centre gutter.

No OCR, table interpretation, word deletion or hyphen rewriting. Ambiguous blocks
remain in the original Poppler text; layout correctness is not certified.
"""
import re
import xml.etree.ElementTree as ET

NS = {'h': 'http://www.w3.org/1999/xhtml'}


def repair_columns(xml_bytes, original_pages):
    xml = xml_bytes.decode('utf-8')
    prefix = 'SSSXMLCONTROL'
    while prefix in xml:
        prefix += 'X'
    controls = {prefix + str(ord(c)) + 'END': c for c in set(re.findall(r'[\x00-\x08\x0b\x0c\x0e-\x1f]', xml))}
    for token, control in controls.items(): xml = xml.replace(control, token)
    try:
        pages = ET.fromstring(xml).findall('.//h:page', NS)
    except ET.ParseError:
        raise ValueError('geometry XML could not be decoded') from None
    for page in pages:
        for word in page.findall('.//h:word', NS):
            for token, control in controls.items():
                word.text = (word.text or '').replace(token, control)
    if len(pages) != len(original_pages):
        raise ValueError('bbox and text page counts differ')
    output, repairs = list(original_pages), []
    for number, page in enumerate(pages):
        width = float(page.attrib['width']); midpoint = width / 2
        replacements = {}
        for block in page.findall('.//h:block', NS):
            lines = block.findall('h:line', NS)
            words = [w for line in lines for w in line.findall('h:word', NS)]
            # Tables/numeric blocks and ordinary narrow columns stay untouched.
            if (len(lines) < 6 or len(words) < 80
                    or float(block.attrib['xMax']) - float(block.attrib['xMin']) < width * .72
                    or sum(bool(re.search(r'[A-Za-z]{3}', w.text or '')) for w in words) / len(words) < .65):
                continue
            left_lines = [line for line in lines if float(line.attrib['xMax']) <= midpoint]
            right_lines = [line for line in lines if float(line.attrib['xMin']) >= midpoint]
            if min(len(left_lines), len(right_lines)) < 6 or len(left_lines) + len(right_lines) < len(lines) * .9:
                continue
            gutter_left = max(float(line.attrib['xMax']) for line in left_lines)
            gutter_right = min(float(line.attrib['xMin']) for line in right_lines)
            if gutter_right - gutter_left < 8: continue
            # Some mathematical lines extend slightly into the gutter. Keep all
            # their words on the left only when none crosses the right boundary.
            cut = gutter_right - .5
            # Every word must belong to one side, including short unpaired lines.
            columns = [[], []]
            for line in lines:
                row = line.findall('h:word', NS)
                if any(float(w.attrib['xMin']) < cut < float(w.attrib['xMax']) for w in row):
                    break
                for side in (0, 1):
                    chosen = [w.text or '' for w in row if (float(w.attrib['xMax']) <= cut) == (side == 0)]
                    if chosen: columns[side].append(' '.join(chosen))
            else:
                originals = [w.text or '' for w in words]
                if any(not word for word in originals): continue
                replacement = '\n'.join(columns[0]) + '\n\n' + '\n'.join(columns[1])
                # Every geometry word is retained exactly once. The original
                # plain-text extractor may remove discretionary hyphens; use
                # bbox glyph text for the whole repaired page instead of
                # pretending it has the old plain-text offsets.
                if sorted(replacement.split()) != sorted(originals): continue
                replacements[id(block)] = replacement
                repairs.append({'page': number + 1, 'word_count': len(words),
                                'operation': 'geometry_column_order; no semantic certification'})
        if replacements:
            output[number] = '\n\n'.join(replacements.get(id(block), '\n'.join(
                ' '.join(w.text or '' for w in line.findall('h:word', NS))
                for line in block.findall('h:line', NS))) for block in page.findall('.//h:block', NS))
    return output, repairs
