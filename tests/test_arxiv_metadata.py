import pytest
from src.adapters.arxiv_metadata import parse_feed,validate_ids


def feed(entries):
    return ('<feed xmlns="http://www.w3.org/2005/Atom" xmlns:arxiv="http://arxiv.org/schemas/atom">'+entries+'</feed>').encode()


def entry(identifier='2401.02954v3'):
    return '<entry><id>http://arxiv.org/abs/'+identifier+'</id><title>A title</title><author><name>A Researcher</name></author><published>2024-01-05T00:00:00Z</published><updated>2025-02-04T00:00:00Z</updated><arxiv:doi>10.1234/example</arxiv:doi><arxiv:journal_ref>A journal</arxiv:journal_ref></entry>'


def test_explicit_ids_keep_order_versions_initial_dates_and_uncertainty():
    result=parse_feed(feed(entry()),['2402.12345','2401.02954'])
    assert [r['requested_id'] for r in result['items']]==['2402.12345','2401.02954']
    assert result['items'][0]['status']=='missing_from_feed'
    item=result['items'][1]
    assert item['returned_id']=='2401.02954v3' and item['published'].startswith('2024') and item['updated'].startswith('2025')
    assert not item['formal_publication_confirmed'] and not item['bibliography_match_confirmed']


def test_comments_are_evidence_clues_without_publication_confirmation():
    xml=entry().replace('</entry>','<arxiv:comment>Accepted at a conference</arxiv:comment></entry>')
    item=parse_feed(feed(xml),['2401.02954'])['items'][0]
    assert item['comments']=='Accepted at a conference'
    assert item['formal_publication_confirmed'] is False


@pytest.mark.parametrize('body',[b'<html>Access denied</html>',b'<!DOCTYPE x [<!ENTITY x "x">]><feed/>',feed(entry()+entry()),feed(entry('2402.12345'))])
def test_error_pages_entity_declarations_duplicates_and_unsolicited_results_fail(body):
    with pytest.raises(ValueError): parse_feed(body,['2401.02954'])


def test_requested_revision_cannot_silently_be_replaced_by_latest_version():
    with pytest.raises(ValueError): parse_feed(feed(entry()),['2401.02954v2'])


@pytest.mark.parametrize('ids',[['2401.02954','2401.02954'],['2401.02954&search_query=all'],['https://internal/'],['2401.02954']*65])
def test_unbounded_or_injectable_queries_rejected(ids):
    with pytest.raises(ValueError): validate_ids(ids)
