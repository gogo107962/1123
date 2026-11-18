'use strict';
// 사람 검수 화면. 승인은 검수자가 이름을 적고 출처별 문장을 직접 확인해 체크해야만 된다.
const $=id=>document.getElementById(id);
const esc=v=>String(v??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
let current=null;
async function api(path,method='GET',body){
 const response=await fetch(path,{method,headers:{'Content-Type':'application/json'},body:body===undefined?undefined:JSON.stringify(body)});
 const data=await response.json().catch(()=>({detail:'서버 응답을 읽지 못했습니다.'}));
 if(!response.ok)throw new Error(typeof data.detail==='string'?data.detail:'입력값을 확인해 주세요.');return data;
}
function fail(e){$('error').hidden=false;$('error').textContent=e.message}
async function list(){
 const rows=await api('/api/review/drafts');
 $('list').innerHTML=rows.map(r=>`<button data-code="${esc(r.code)}"><strong>${esc(r.name)}</strong><span>${esc(r.agency)} · 규칙 ${r.rules} · 확인 항목 ${r.checks} · 출처 ${r.sources}</span>${r.approved?`<span class="badge">승인됨 · ${esc(r.approved_by)}</span>`:'<span class="badge warn">검수 전</span>'}</button>`).join('')||'<p class="note">초안이 없습니다. tools/draft_policy.py 로 만드세요.</p>';
}
function show(d){
 current=d;$('detail').hidden=false;
 $('detail').innerHTML=`<h2>${esc(d.name)}</h2><p class="note">${esc(d.agency)} · ${esc(d.region)} · ${esc(d.category)} · <a href="${esc(d.official_url)}" target="_blank" rel="noopener noreferrer">공식 주소 열기</a></p>
<h3>1. 출처 확인</h3><p class="note">링크를 열어 원문에 있는 문장을 확인하고, 문장을 고친 뒤 체크하세요. 체크한 출처만 승인본에 들어갑니다.</p>
${d.sources.map(s=>`<div class="item"><strong>${esc(s.ref)}</strong> · <a href="${esc(s.url)}" target="_blank" rel="noopener noreferrer">${esc(s.title)}</a><textarea data-quote="${esc(s.ref)}" placeholder="원문에서 확인한 문장을 그대로 붙여 넣으세요">${esc(s.excerpt)}</textarea><label><input type="checkbox" data-source="${esc(s.ref)}"> 원문에서 이 문장을 직접 확인했습니다</label></div>`).join('')}
<h3>2. 규칙</h3><p class="note">원문과 맞는 규칙만 남기세요. 출처를 확인하지 않은 규칙은 승인본에서 빠집니다.</p>
${d.rules.map(r=>`<div class="item"><label><input type="checkbox" data-rule="${esc(r.id)}" checked> <span><strong>${esc(r.id)}</strong> (출처 ${esc(r.source_ref)}) ${esc(r.message)}<br><code>${esc(JSON.stringify(r.predicate))}</code></span></label></div>`).join('')}
<h3>3. 사람이 따로 확인할 항목 ${(d.manual_checks||[]).length}개</h3><p class="note">승인해도 이 항목들은 남아서 앱에 ‘확인 필요’로 표시됩니다.</p>
${(d.manual_checks||[]).map(c=>`<div class="item">${esc(c.message)}</div>`).join('')}
<h3>4. 서류 ${d.documents.length}개</h3>${d.documents.map(x=>`<div class="item"><strong>${esc(x.title)}</strong> (출처 ${esc(x.source_ref)}) ${esc(x.instructions||'')}</div>`).join('')||'<p class="note">옮겨진 서류가 없습니다.</p>'}
<div class="approve"><h3 style="margin-top:0">승인</h3><label for="reviewer">검수자 이름</label><input id="reviewer" type="text" maxlength="40" autocomplete="off">
<label><input type="checkbox" id="confirmed"> 공고 원문과 직접 대조했고, 위에서 체크한 출처와 규칙이 원문과 맞습니다</label>
<p><button class="button primary" id="approve">승인하고 판별 엔진에 등록</button></p><p id="result" class="note" role="status"></p></div>`;
 $('detail').scrollIntoView({behavior:'smooth'});
}
document.addEventListener('click',e=>{
 const row=e.target.closest('[data-code]');
 if(row)api('/api/review/drafts/'+encodeURIComponent(row.dataset.code)).then(show,fail);
 if(e.target.id==='approve'&&current){
  const sources={};document.querySelectorAll('[data-source]:checked').forEach(box=>{sources[box.dataset.source]=document.querySelector(`[data-quote="${box.dataset.source}"]`).value});
  const keep=[...document.querySelectorAll('[data-rule]:checked')].map(box=>box.dataset.rule);
  api('/api/review/drafts/'+encodeURIComponent(current.code)+'/approve','POST',{reviewed_by:$('reviewer').value,confirmed:$('confirmed').checked,sources,keep_rules:keep})
   .then(r=>{$('result').textContent=`승인했습니다. 규칙 ${r.rules}개, 출처 ${r.sources}개가 등록됐고 빠진 출처는 ${r.dropped_sources.join(', ')||'없음'}입니다.`;return list()},e=>{$('result').textContent=e.message});
 }
});
list().catch(fail);
