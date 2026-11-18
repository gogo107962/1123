import json
import httpx
import pytest
from test_project import ctx
from test_ontong import item,response,count,KEY
import ontong
from sync_all_ontong import sync_all


@pytest.fixture(autouse=True)
def key(monkeypatch):monkeypatch.setenv('ONTONG_YOUTH_API_KEY',KEY)


def full(tmp_path,handler,**kwargs):
    return sync_all(checkpoint=tmp_path/'checkpoint.json',transport=httpx.MockTransport(handler),
                    pause=lambda _:None,page_size=2,**kwargs)


def test_full_unfiltered_final_partial_page_and_recheck(ctx,tmp_path):
    calls=[]
    def handler(r):
        assert 'plcyNm' not in r.url.params
        n=int(r.url.params['pageNum']);calls.append(n)
        return response([item('1'),item('2')] if n==1 else [item('3')],total=3,page=n,size=2)
    run=full(tmp_path,handler)
    assert calls==[1,2,1] and run['received']==3 and run['has_more']==0
    assert count('ontong_candidates')==count('ontong_snapshots')==3
    assert len(ctx.get('/api/policies').json())==3


def test_failed_page_resumes_without_partial_candidate_publish(ctx,tmp_path):
    calls=[]
    def failing(r):
        n=int(r.url.params['pageNum']);calls.append(n)
        return response([item('1'),item('2')],total=3,size=2) if n==1 else httpx.Response(429)
    with pytest.raises(ontong.OntongError):full(tmp_path,failing)
    assert calls==[1,2] and count('ontong_candidates')==0
    checkpoint=json.loads((tmp_path/'checkpoint.json').read_text(encoding='utf-8'))
    assert checkpoint['pages']==1 and len(checkpoint['items'])==2
    calls.clear()
    def good(r):
        n=int(r.url.params['pageNum']);calls.append(n)
        return response([item('1'),item('2')] if n==1 else [item('3')],total=3,page=n,size=2)
    assert full(tmp_path,good,resume=True)['status']=='success'
    assert calls==[1,2,1] and count('ontong_candidates')==3


@pytest.mark.parametrize('mode',['duplicate','count_change','first_page_drift'])
def test_drift_never_publishes_partial_data(ctx,tmp_path,mode):
    calls=[]
    def handler(r):
        n=int(r.url.params['pageNum']);calls.append(n)
        if mode=='first_page_drift' and len(calls)==3:
            return response([item('new'),item('2')],total=3,size=2)
        return response([item('1'),item('2')] if n==1 else [item('1' if mode=='duplicate' else '3')],
                        total=4 if mode=='count_change' and n==2 else 3,page=n,size=2)
    with pytest.raises(ontong.OntongError):full(tmp_path,handler)
    assert count('ontong_candidates')==0


def test_transient_errors_retry_with_bound(ctx,tmp_path):
    calls=[]
    def handler(r):
        calls.append(1)
        if len(calls)<3:return httpx.Response(503)
        return response([item('1')],size=2)
    assert full(tmp_path,handler)['received']==1
    assert len(calls)==4


def test_empty_full_collection_keeps_old_candidates(ctx,tmp_path):
    ontong.sync(transport=httpx.MockTransport(lambda r:response([item()])))
    result=full(tmp_path,lambda r:response([],size=2))
    assert result['received']==0 and count('ontong_candidates')==1
