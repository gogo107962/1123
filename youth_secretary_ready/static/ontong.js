// Public candidates are escaped as text, never executed or interpreted as rules.
let ontongPage=1;
function sourceCheckHtml(check){
 if(!check)return '<p class="hint">공식 모집 공고 대조 기록 없음</p>';
 return `<div class="notice ${check.kind==='period_match'?'neutral':''}" data-source-check><strong>${check.api_changed_since_check?'API 변경됨 · 재대조 필요':check.kind==='period_conflict'?'API와 공식 접수기간 차이':check.kind==='closure_notice'?'공식 조기 마감 안내 확인':'공식 접수기간 대조'}</strong><p>${esc(check.summary)}</p><p>공식 안내: ${esc(check.official_period_text)}</p><p>확인일 ${esc(check.checked_on)} · ${esc(check.scope)}</p><a href="${esc(check.source_url)}" target="_blank" rel="noopener noreferrer">${esc(check.source_title)}</a><p>${esc(check.notice)}</p>${check.policy_code?`<button class="btn small" data-open-draft="${esc(check.policy_code)}">연결된 규칙·서류 초안 검토</button>`:''}</div>`;
}
async function renderOntong(){
 const category=el('ontongCategory').value;
 const params=new URLSearchParams({q:el('ontongLocalQuery').value.trim(),category,quality:el('ontongQuality').value,page:String(ontongPage),page_size:'20'});
 const [state,result]=await Promise.all([api('/api/integrations/ontong'),api('/api/integrations/ontong/search?'+params)]);
 const rows=result.items;
 el('ontongCategory').innerHTML='<option value="">전체 분야</option>'+result.categories.map(c=>`<option value="${esc(c)}" ${c===category?'selected':''}>${esc(c)}</option>`).join('');
 el('ontongPage').textContent=`검색 결과 ${result.total}건 · ${result.pages?result.page:0} / ${result.pages}페이지`;
 el('ontongPrev').disabled=ontongPage<=1;el('ontongNext').disabled=ontongPage>=result.pages;
 el('ontongStatus').textContent=(state.configured?'인증키 설정됨':'인증키 미설정')+` · 저장된 후보 ${state.candidate_count}건`+(state.last_run?` · 최근 수집 ${state.last_run.status==='success'?'성공':state.last_run.status==='running'?'진행 중':'실패'}`:' · 아직 실제 수집 기록 없음');
 el('syncOntong').disabled=!state.configured||state.busy;
 el('ontongCandidates').innerHTML=rows.map(p=>`<article class="card ontong-candidate" data-external-id="${esc(p.external_id)}"><span class="tag review">실제 API 수집 · 검수 전</span> <span class="tag">${esc(p.category||'분야 미기재')}</span><h3>${esc(p.name)}</h3><p>${esc(p.agency||'기관 미기재')}</p><p>${esc(p.summary)}</p><p class="hint">API 신청기간 원문: ${esc(p.application_text||'미기재 · 원문 확인 필요')}<br>모집 중 여부와 지원 자격은 아직 판별하지 않습니다.<br>수집 확인: ${esc(p.last_seen_at)} · 정책번호 ${esc(p.external_id)}</p>${sourceCheckHtml(p.source_check)}${p.source_url?`<a href="${esc(p.source_url)}" target="_blank" rel="noopener noreferrer">API 제공 참고 링크 (검수 전)</a>`:'<p class="hint">사용 가능한 참고 링크 없음 · 공고 직접 확인 필요</p>'}<details><summary data-candidate-open="${esc(p.external_id)}">제출서류·조건 원문 검토</summary><div data-candidate-detail></div></details><button class="btn small" data-candidate-download="${esc(p.external_id)}">검토 자료 JSON 내려받기</button></article>`).join('')||'<p class="hint">검색 조건에 맞는 저장된 정책이 없습니다.</p>';
 document.querySelectorAll('[data-open-draft]').forEach(button=>button.onclick=()=>action(async()=>{
  await renderCatalog();
  const card=document.querySelector(`[data-review-code="${CSS.escape(button.dataset.openDraft)}"]`);
  if(!card)throw new Error('연결된 검수 초안이 아직 DB에 등록되지 않았습니다.');
  card.closest('details').open=true;card.scrollIntoView({behavior:'smooth',block:'start'});
 }));
 document.querySelectorAll('[data-candidate-open]').forEach(button=>button.onclick=()=>action(async()=>{
  const bundle=await api('/api/integrations/ontong/candidates/'+encodeURIComponent(button.dataset.candidateOpen));
  const p=bundle.public_fields;
  button.parentElement.querySelector('[data-candidate-detail]').innerHTML=[['지원 내용',p.plcySprtCn],['추가 신청 조건',p.addAplyQlfcCndCn],['참여 제한',p.ptcpPrpTrgtCn],['신청 방법',p.plcyAplyMthdCn],['제출서류',p.sbmsnDcmntCn],['기타 사항',p.etcMttrCn]].map(([title,value])=>`<h4>${esc(title)}</h4><p class="ontong-text">${esc(value||'API 미기재 · 제한/서류가 없다는 의미가 아닙니다.')}</p>`).join('');
 }));
 document.querySelectorAll('[data-candidate-download]').forEach(button=>button.onclick=()=>action(async()=>{
  const bundle=await api('/api/integrations/ontong/candidates/'+encodeURIComponent(button.dataset.candidateDownload));
  const url=URL.createObjectURL(new Blob([JSON.stringify(bundle,null,2)],{type:'application/json;charset=utf-8'}));
  const a=document.createElement('a');a.href=url;a.download='ontong-review-'+bundle.external_id+'.json';document.body.append(a);a.click();a.remove();setTimeout(()=>URL.revokeObjectURL(url),1000);
 }));
}
document.addEventListener('DOMContentLoaded',()=>{
 el('ontongLocalSearch').onsubmit=event=>{event.preventDefault();action(async()=>{ontongPage=1;await renderOntong()})};
 el('ontongPrev').onclick=()=>action(async()=>{ontongPage=Math.max(1,ontongPage-1);await renderOntong()});
 el('ontongNext').onclick=()=>action(async()=>{ontongPage+=1;await renderOntong()});
 el('refreshOntong').onclick=()=>action(renderOntong);
 el('syncOntong').onclick=()=>action(async()=>{
  el('ontongResult').textContent='온통청년에서 정책을 가져오는 중…';
  try{
   const r=await api('/api/integrations/ontong/sync','POST',{keyword:el('ontongKeyword').value.trim(),page_size:10,max_pages:1});
   el('ontongResult').textContent=`검색 결과 ${r.matched_total}건 중 ${r.received}건 재확인 · 신규/변경 ${r.changed}건 저장${r.has_more?' · 이번 호출은 첫 페이지만 조회했습니다.':''}`;
  }catch(e){el('ontongResult').textContent=e.message}
  await renderOntong();
 });
 // Reads only our DB; no upstream request is made on page load.
 renderOntong().catch(()=>{el('ontongStatus').textContent='연결 설정을 불러오지 못했습니다. 다시 확인을 눌러 주세요.'});
});
