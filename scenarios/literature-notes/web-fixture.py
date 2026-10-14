"""Free protocol provider decisions; explicit gaps, no scientific interpretation."""
PREFIX = 'mcp__literature_web__'
FIELDS = ('research_goal', 'method', 'evaluation', 'findings', 'limitations')


def action(values, _event):
    delivered = next((v for v in values if v.get('status') in ('delivered', 'delivered_with_gaps')), None)
    if delivered:
        return None, {'status': delivered['status'], 'scope': 'protocol_only'}
    flows = [(i, v) for i, v in enumerate(values) if v.get('phase') in ('review', 'synthesis')]
    if flows:
        index, flow = flows[-1]
        recent = values[index + 1:]
        if flow['phase'] == 'synthesis':
            if not any(v.get('scope') == 'synthesis_only' for v in recent):
                return PREFIX + 'read_final_synthesis', {}
            return PREFIX + 'deliver_research_notes', {'synthesis_hypothesis': '协议模拟仅检验任务隔离与交付，不形成科研结论。'}
        for cid in flow['target_claim_ids']:
            if not any(v.get('claim_id') == cid for v in recent):
                return PREFIX + 'read_claim_repair_packet', {'claim_id': cid}
        return PREFIX + 'submit_claim_repair', {'decisions': [
            {'claim_id': cid, 'verdict': 'not_extracted', 'reason': '模拟不执行科学理解。'}
            for cid in flow['target_claim_ids']], 'synthesis_hypothesis': '协议模拟仅检验链路，不形成科研结论。'}
    selected = next((v for v in values if 'papers' in v and 'page_numbering' in v), None)
    if selected is None: return PREFIX + 'list_pdfs', {}
    for paper in selected['papers']:
        pid = paper['paper_id']
        if not any(v.get('paper_id') == pid and 'coverage' in v for v in values):
            return PREFIX + 'prepare_pdf', {'paper_id': pid}
        if not any(v.get('paper_id') == pid and 'contexts' in v for v in values):
            meta = next(v for v in values if v.get('paper_id') == pid and 'coverage' in v)
            return PREFIX + 'read_pdf_evidence_plan', {'paper_id': pid,
                'document_version_sha256': meta['document_version_sha256'],
                'windows': [{'page': '1', 'start': 0, 'length': 1200}]}
    return PREFIX + 'preview_research_notes', {'draft': {'papers': [
        {'paper_id': p['paper_id'], 'fields': [{'name': f, 'status': 'not_extracted',
            'statement': '协议模拟未执行科学理解。', 'citations': []} for f in FIELDS]}
        for p in selected['papers']], 'synthesis': '协议模拟只检验隔离、自动复核流程与缺口交付。'}}
