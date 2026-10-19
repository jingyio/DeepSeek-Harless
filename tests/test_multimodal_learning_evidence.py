"""Multimodal metadata needs an actual durable image block, not invented text."""
import json
from src.adapters.continuous_motif_learning import observations
def events(content):
    return [{'seq':1,'type':'tool/call','data':{'callId':'real-call','name':'mcp__file_management__view_document_page','arguments':'{"source_id":"real-source"}'}},
            {'seq':2,'type':'tool/result','data':{'message':{'content':[{'type':'tool-result','toolCallId':'real-call','content':content}]}}}]
def test_one_json_metadata_and_native_durable_image_are_preserved():
    content=[{'type':'text','text':json.dumps({'view_id':'real-view'})},
             {'type':'image','attachment':{'attachmentId':'sha256:'+'a'*64,'mediaType':'image/png','width':2,'height':2}}]
    rows=observations(events(content));assert len(rows)==1
    assert rows[0]['out']=={'view_id':'real-view'} and rows[0]['image_attachments']==[content[1]['attachment']]
def test_ambiguous_or_unadmitted_image_results_do_not_become_learning_evidence():
    text={'type':'text','text':'{"view_id":"x"}'}
    for content in [[text,text],[text,{'type':'image','data':'untrusted-base64'}],[text,{'type':'audio'}],[{'type':'text','text':'non-JSON diagnostic'}]]:
        assert observations(events(content))==[]
