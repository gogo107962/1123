"""Offline contract/regression tests. Mocked responses are not live API evidence."""
import json
import logging
import httpx
import pytest
from test_project import ctx
from db import connect
from policy_data import load_policies
import ontong

KEY = 'unit-test-key-never-real'


@pytest.fixture(autouse=True)
def fake_key(monkeypatch):
    monkeypatch.setenv('ONTONG_YOUTH_API_KEY', KEY)


def item(number='202611160001', **overrides):
    return {'plcyNo': number, 'plcyNm': '월세 지원', 'plcyExplnCn': '월세 준비 안내',
            'sprvsnInstCdNm': '샘플기관', 'aplyYmd': '', 'sbmsnDcmntCn': '임대차계약서',
            'refUrlAddr1': 'https://example.org/notice', **overrides}


def response(items, total=None, page=1, size=10):
    return httpx.Response(200, json={'resultCode': 200, 'resultMessage': '정상',
        'result': {'pagging': {'totCount': len(items) if total is None else total, 'pageNum': page, 'pageSize': size},
                   'youthPolicyList': items}})


def collect(items, **kwargs):
    return ontong.sync('월세', transport=httpx.MockTransport(lambda r: response(items)), **kwargs)


def count(table):
    with connect() as con: return con.execute('SELECT count(*) FROM '+table).fetchone()[0]


def test_live_contract_stages_without_approving(ctx):
    before = load_policies()
    def handler(request):
        assert str(request.url).startswith(ontong.ENDPOINT)
        assert request.url.params['apiKeyNm'] == KEY
        assert request.url.params['plcyNm'] == '월세'
        return response([item(sprvsnInstPicNm='담당자명', unexpected=KEY)])
    run = ontong.sync('월세', transport=httpx.MockTransport(handler))
    assert run['status'] == 'success' and run['changed'] == 1
    assert load_policies() == before
    row = ctx.get('/api/integrations/ontong/candidates').json()[0]
    assert row['review_status'] == 'unreviewed' and row['application_text'] == ''
    bundle = ctx.get('/api/integrations/ontong/candidates/'+row['external_id']).json()
    assert 'sprvsnInstPicNm' not in bundle['public_fields']
    assert KEY not in json.dumps(bundle)
    sid = ctx.post('/api/sessions', json={}).json()['id']
    assert ctx.put(f'/api/sessions/{sid}/selected', json={'selected':[row['external_id']]}).status_code == 422


def test_repeated_collection_is_idempotent_and_changes_keep_history(ctx):
    assert collect([item()])['changed'] == 1
    assert collect([item()])['changed'] == 0
    assert count('ontong_candidates') == count('ontong_snapshots') == 1
    assert collect([item(sbmsnDcmntCn='수정된 서류')])['changed'] == 1
    assert count('ontong_candidates') == 1 and count('ontong_snapshots') == 2


def test_bounded_pagination(ctx):
    calls = []
    def handler(request):
        page = int(request.url.params['pageNum']); calls.append(page)
        return response([item(str(page))], total=10, page=page, size=1)
    run = ontong.sync('월세', page_size=1, max_pages=2, transport=httpx.MockTransport(handler))
    assert calls == [1,2] and run['received'] == 2 and run['has_more'] == 1


@pytest.mark.parametrize('failure', ['timeout','duplicate','total_changed','wrong_page'])
def test_failed_later_page_rolls_back_whole_batch(ctx, failure):
    collect([item()])
    def handler(request):
        page = int(request.url.params['pageNum'])
        if page == 1:return response([item('new1')], total=2, page=1, size=1)
        if failure == 'timeout': raise httpx.ReadTimeout('URL contains '+KEY, request=request)
        return response([item('new1' if failure == 'duplicate' else 'new2')],
                        total=3 if failure == 'total_changed' else 2,
                        page=1 if failure == 'wrong_page' else 2, size=1)
    with pytest.raises(ontong.OntongError) as exc:
        ontong.sync(page_size=1,max_pages=2,transport=httpx.MockTransport(handler))
    assert KEY not in str(exc.value)
    assert count('ontong_candidates') == count('ontong_snapshots') == 1
    assert ontong.status()['last_run']['status'] == 'failed'


@pytest.mark.parametrize('status,code', [(401,'auth'),(403,'auth'),(429,'rate_limit'),(503,'upstream'),(302,'upstream')])
def test_http_failure_safe_and_no_redirect(ctx,status,code):
    seen=[]
    def handler(request):
        seen.append(request)
        return httpx.Response(status, text=KEY, headers={'Location':'https://example.org/leak'})
    with pytest.raises(ontong.OntongError) as exc:
        ontong.sync(transport=httpx.MockTransport(handler))
    assert exc.value.code == code and KEY not in str(exc.value)
    assert len(seen)==1 and count('ontong_candidates')==0


@pytest.mark.parametrize('data', [None,[],{'resultCode':500},{'resultCode':200,'result':{}},
    {'resultCode':200,'result':{'pagging':{},'youthPolicyList':[]}}])
def test_malformed_success_is_not_empty_success(ctx,data):
    with pytest.raises(ontong.OntongError):
        ontong.sync(transport=httpx.MockTransport(lambda r:httpx.Response(200,json=data)))
    assert count('ontong_candidates')==0


def test_oversize_response_is_rejected(ctx):
    with pytest.raises(ontong.OntongError):
        ontong.sync(transport=httpx.MockTransport(lambda r:httpx.Response(200,content=b'x'*2_000_001)))
    assert count('ontong_candidates')==0


@pytest.mark.parametrize('bad', [item(plcyNo=''),item(plcyNm=''),item(plcyExplnCn=KEY),item(sbmsnDcmntCn={'invalid':True})])
def test_bad_item_stops_batch(ctx,bad):
    with pytest.raises(ontong.OntongError):collect([item('good'),bad])
    assert count('ontong_candidates')==0


def test_empty_search_does_not_delete_existing(ctx):
    collect([item()]); run=collect([])
    assert run['received']==0 and run['matched_total']==0 and count('ontong_candidates')==1


@pytest.mark.parametrize('url', ['javascript:alert(1)','www.example.org','https://user:pass@example.org','https://example.org/\nattack'])
def test_unusable_links_are_not_made_clickable(ctx,url):
    collect([item(refUrlAddr1=url)])
    assert ontong.candidates()[0]['source_url']==''
    assert ontong.review_bundle(item()['plcyNo'])['public_fields']['refUrlAddr1']==url.strip()


def test_key_status_is_local_read_only_and_hot_reloads(ctx,monkeypatch,tmp_path):
    monkeypatch.delenv('ONTONG_YOUTH_API_KEY')
    path=tmp_path/'key.txt';monkeypatch.setattr(ontong,'KEY_FILE',path)
    assert ctx.get('/api/integrations/ontong').json()['configured'] is False
    assert ctx.post('/api/integrations/ontong/sync',json={}).status_code==503
    path.write_text('\ufeff'+KEY+'\n',encoding='utf-8')
    result=ctx.get('/api/integrations/ontong')
    assert result.json()['configured'] is True and KEY not in result.text
    assert count('ontong_sync_runs')==0


def test_request_caps_and_concurrent_guard(ctx):
    assert ctx.post('/api/integrations/ontong/sync',json={'max_pages':4}).status_code==422
    assert ctx.post('/api/integrations/ontong/sync',json={'page_size':1000}).status_code==422
    assert ctx.post('/api/integrations/ontong/sync',json={'keyword':KEY}).status_code==422
    with ontong.LOCK:
        assert ctx.post('/api/integrations/ontong/sync',json={}).status_code==409
    assert count('ontong_sync_runs')==0


def test_http_logs_do_not_disclose_key(ctx,caplog):
    with caplog.at_level(logging.DEBUG):collect([item()])
    assert KEY not in caplog.text


def test_database_error_rolls_back_candidates(ctx):
    collect([item()])
    with connect() as con:
        con.execute("CREATE TRIGGER fail_snapshot BEFORE INSERT ON ontong_snapshots BEGIN SELECT RAISE(ABORT,'stop'); END")
    with pytest.raises(ontong.OntongError) as exc:collect([item(sbmsnDcmntCn='changed')])
    assert exc.value.code=='storage'
    assert ontong.review_bundle(item()['plcyNo'])['public_fields']['sbmsnDcmntCn']=='임대차계약서'
    assert count('ontong_snapshots')==1
