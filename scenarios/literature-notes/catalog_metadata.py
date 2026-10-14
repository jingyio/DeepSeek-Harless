"""Conservative source-bound metadata candidates, not scholarly identity inference."""
from collections import Counter
import re
from mcp.server.mcpserver.exceptions import ToolError
from pdf_tools import digest

YEAR = r'(?:1[5-9]|20|21)\d{2}'
NAME_TOKEN = re.compile(r"[A-Za-z]+(?:[-'’][A-Za-z]+)*\.?")
PERSON_TOKEN = re.compile(r"(?:[A-Z][a-z]+(?:[-'’][A-Z]?[a-z]+)*|[A-Z]\.)")


def name_tokens(text):
    return NAME_TOKEN.findall(text)


def metadata_candidates(text, version):
    dates = []
    labels = {'published': 'publication', 'published online': 'publication', 'publication date': 'publication',
              '发布日期': 'publication', '在线发表': 'publication', '发表日期': 'publication',
              'received': 'received', '收稿': 'received', 'accepted': 'accepted', '接受': 'accepted',
              'copyright': 'copyright', '©': 'copyright'}
    pattern = r'(?im)^[ \t]*(Published(?:[ \t]+online)?|Publication[ \t]+date|发布日期|在线发表|发表日期|Received|收稿|Accepted|接受|Copyright|©)(?=[ \t:：]|\d)[ \t:：]*[^\n]{0,100}'
    for match in re.finditer(pattern, text):
        years = re.findall(r'(?<!\d)' + YEAR + r'(?!\d)', match.group())
        if len(set(years)) == 1:
            label = ' '.join(match.group(1).lower().split())
            dates.append({'kind':labels[label], 'year':years[0], 'start':match.start(), 'end':match.end(), 'anchor':match.group()})
    arxiv = r'arXiv:[ \t]*\d{4}\.\d{4,5}(?:v\d+)?\s*(?:\[[^\]\n]{1,30}\]\s*)?(?:\d{1,2}[ \t]+[A-Za-z]{3,12}[ \t]+)((?:20|21)\d{2})\b'
    for match in re.finditer(arxiv, text, re.IGNORECASE):
        dates.append({'kind':'preprint', 'year':match.group(1), 'start':match.start(), 'end':match.end(), 'anchor':match.group()})
    dates.sort(key=lambda row:row['start'])
    for row in dates:
        row['candidate_id'] = 'date-' + digest({'version':version, **row})[:24]
        row['eligible_bibliography_year'] = row['kind'] in ('publication','preprint')

    lines = [(m.start(), m.end(), m.group()) for m in re.finditer(r'[^\n]+', text) if m.group().strip()]
    boundary = re.search(r'(?im)^[ \t]*(?:abstract|a[ \t]+bstract|received[ \t]*:|accepted[ \t]*:)', text)
    stop = boundary.start() if boundary else min(len(text), 3000)
    regions = []
    i = 0
    while i < len(lines):
        start,end,line = lines[i]; tokens = name_tokens(line)
        if start >= stop: break
        # Require an explicit affiliation/correspondence marker; title-like name tokens alone do not qualify.
        if any(c in line for c in '∗†‡✉*') and len(tokens) >= 4 and all(PERSON_TOKEN.fullmatch(t) for t in tokens):
            j = i + 1
            while j < len(lines) and lines[j][0] < stop:
                more = name_tokens(lines[j][2])
                if len(more) < 4 or not all(PERSON_TOKEN.fullmatch(t) for t in more): break
                end = lines[j][1]; j += 1
            regions.append({'start':start,'end':end,'candidate_kind':'marked_author_header'})
            i = j
        else: i += 1
    if not regions:
        # Alternate known layout: name / affiliation / email, possibly displaced by column extraction.
        for i,(_,_,line) in enumerate(lines):
            if i < 2 or not re.search(r'\b[^\s@]+@[^\s@]+\.[A-Za-z]{2,}\b', line): continue
            start,end,candidate = lines[i-2]; tokens = name_tokens(candidate)
            if 2 <= len(tokens) <= 5 and all(PERSON_TOKEN.fullmatch(t) for t in tokens):
                regions.append({'start':start,'end':end,'candidate_kind':'email_profile_name'})
    unique = {(r['start'],r['end']):r for r in regions}
    regions = sorted(unique.values(),key=lambda r:r['start'])[:16]
    for row in regions:
        row['anchor'] = text[row['start']:row['end']]
        row['name_tokens'] = name_tokens(row['anchor'])
        row['region_id'] = 'authors-' + digest({'version':version, **row})[:24]
    return {'date_candidates':dates, 'author_regions':regions,
            'candidate_scope':'bounded explicit date labels; marked Latin-name headers or name/affiliation/email profiles',
            'complete_author_list_certified':False}


def resolve_year(selection, packet):
    rows = packet['date_candidates']; chosen = selection['candidate_id']
    eligible = [r for r in rows if r['eligible_bibliography_year']]
    origin = 'model_selected_date'
    if chosen is not None:
        selected = next((r for r in rows if r['candidate_id']==chosen),None)
        if not selected or not selected['eligible_bibliography_year']:
            raise ToolError('year.candidate_id must be a current publication/preprint candidate, never received/accepted/copyright')
    elif len({r['year'] for r in eligible}) == 1:
        selected = next((r for r in eligible if r['kind']=='publication'),eligible[0])
        origin = 'runtime_unambiguous_date'
    else:
        return {'value':None,'anchor':'','kind':'unknown','candidate_id':None,
                'selection_origin':'runtime_ambiguous_dates' if eligible else 'runtime_no_supported_date'}
    return {'value':selected['year'],'anchor':selected['anchor'],'kind':selected['kind'],
            'candidate_id':selected['candidate_id'],'selection_origin':origin}


def check_author_coverage(coverage, authors, packet):
    regions = packet['author_regions']; ids = [r['region_id'] for r in regions]
    selected = coverage['region_ids']; status = coverage['status']
    if len(set(selected)) != len(selected) or any(i not in ids for i in selected):
        raise ToolError('author_coverage.region_ids must be unique current tool-issued candidates')
    if status=='unavailable' and (regions or authors):
        raise ToolError('visible author candidates cannot be declared unavailable; copy the names or explicitly mark partial with a reason')
    if status=='partial' and not coverage['reason'].strip(): raise ToolError('partial author coverage needs a reason')
    expected = Counter(t for r in regions for t in r['name_tokens'])
    actual = Counter(t for a in authors for t in name_tokens(a['value']))
    uncovered = list((expected-actual).elements())
    if status=='covered' and (set(selected)!=set(ids) or uncovered):
        raise ToolError('author coverage incomplete: ' + str({'region_ids':ids,'uncovered_name_tokens':uncovered,
            'instruction':'copy the visible author names; if the candidate is not an author region, mark partial with a concrete reason'}))
    return {**coverage,'uncovered_name_tokens':uncovered,'candidate_regions_covered':status=='covered',
            'complete_author_list_certified':False}
