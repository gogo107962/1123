'use strict';
const $=id=>document.getElementById(id);
const esc=value=>String(value??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
const SCREEN_LABEL={api_match:['rolling','API 조건과 맞아요'],needs_check:['unknown','확인 필요'],api_mismatch:['closed','API 조건과 달라요']};
const RESULT_LABEL={match:['rolling','맞아요'],unknown:['unknown','확인 필요'],mismatch:['closed','달라요']};
const TOOL_NAMES={search_policies:'정책 검색',screen_profile:'내 정보와 조건 비교'};
const CHAT_STARTERS=['자격증 시험 쳤는데 지원받을 수 있어?','월세 지원 받을 수 있어?','나에게 맞는 정책 찾아줘'];
const PROFILE_KEY='youth-desk-profile',DEMO={name:'민지',age:26,sido:'11',job_code:'0013003',school_code:''};
const CRITERIA={period:'신청기간',age:'나이',region:'지역',income:'소득',job:'취업 상태',school:'학력',major:'전공',marriage:'결혼',exclusion:'참여 제한',target:'대상'};
let profile=null,finder=null,chat=[],chatBusy=false,names={sido:{},job_code:{},school_code:{}},space=null,results=[],page=1,tab='explore',activePolicy=null,activePlan=null,dialogVersion=0,loading=false,health=null,toastTimer;
async function api(path,method='GET',body){
 const response=await fetch(path,{method,headers:{'Content-Type':'application/json'},body:body===undefined?undefined:JSON.stringify(body)});
 let data;try{data=await response.json()}catch{throw new Error('서버 응답을 읽지 못했어요. 연결 상태를 확인해 주세요.')}
 if(!response.ok){const error=new Error(typeof data.detail==='string'?data.detail:'입력값을 확인해 주세요.');error.status=response.status;throw error}return data;
}
try{profile=JSON.parse(localStorage.getItem(PROFILE_KEY))}catch{}
// 서버에는 비교에 쓰는 값만 보낸다. 이름은 브라우저에만 둔다.
function mine(p=profile){return {age:p?.age??null,sido:p?.sido||null,job_code:p?.job_code||null,school_code:p?.school_code||null}}
function compared(){return Object.values(mine()).some(v=>v!==null)}
function chipsOf(p){return [p.age!=null?p.age+'세':'',names.sido[p.sido],names.job_code[p.job_code],names.school_code[p.school_code]].filter(Boolean)}
function label(p){return p.tier?`<span class="period-label ${p.screen?SCREEN_LABEL[p.screen.outcome][0]:''}">${p.screen?SCREEN_LABEL[p.screen.outcome][1]:'원문 링크만 · 비교 제외'}</span>`:''}
function saveProfile(next){profile=next;try{localStorage.setItem(PROFILE_KEY,JSON.stringify(next))}catch{}renderProfile()}
function renderProfile(){
 const p=profile||{},on=compared();$('pAge').value=p.age??'';$('pSido').value=p.sido||'';$('pJob').value=p.job_code||'';$('pSchool').value=p.school_code||'';
 $('profileTitle').textContent=profile?'내 정보':'먼저 내 정보를 알려 주세요';
 $('greeting').textContent=p.name?`${p.name} 님, 어떤 지원을 찾으세요?`:'나의 정책 준비 도우미';
 $('profileCardTitle').textContent=on?'내 정보 기준으로 찾아요':'내 정보를 입력하면 맞는 정책부터 보여드려요';
 $('profileChips').innerHTML=chipsOf(mine()).map(c=>`<span class="badge">${esc(c)}</span>`).join('');
 $('profileCardNote').textContent=on?'API에 적힌 조건과 비교한 결과예요. 자격 판정이 아니니 공고 원문을 확인해 주세요.':'';
 $('outcomeLabel').hidden=!on;$('profileCardEdit').textContent=on?'내 정보 수정':'내 정보 입력';
 // 내 정보로 비교하는 동안에는 코드 필터가 적용되지 않으므로 숨긴다.
 $('codeFilterPanel').hidden=on;
}
function renderChat(){
 $('chatLog').innerHTML=`<div class="msg bot"><p>안녕하세요${profile?.name?', '+esc(profile.name)+' 님':''}. 어떤 지원을 찾으세요? 상황을 말해 주시면 수집된 정책에서 찾아볼게요.</p></div>`+chat.map((m,i)=>m.who==='user'?`<div class="msg user"><p>${esc(m.text)}</p></div>`:`<div class="msg bot"><p>${esc(m.text)}</p>${(m.items||[]).map(p=>`<button class="chat-card" data-open="${esc(p.external_id)}"><strong>${esc(p.name)}</strong><span>${esc(p.agency||'기관 안내 확인 필요')}</span>${label(p)}</button>`).join('')}${m.total>(m.items||[]).length?`<button class="button subtle" data-chat-more="${i}">전체 ${m.total.toLocaleString()}건 보기 →</button>`:''}${m.suggest?`<button class="button subtle" data-chat-apply="${i}">내 정보에 반영하고 다시 찾기: ${esc(chipsOf(m.suggest).join(' · '))}</button>`:''}${m.tools?`<span class="small">실행한 도구: ${m.tools.filter(t=>t.status==='ok').map(t=>TOOL_NAMES[t.tool]).join(' → ')} · ${esc(m.notice)}</span>`:''}</div>`).join('');
 $('chatOptions').innerHTML=chat.length?'':CHAT_STARTERS.map(t=>`<button data-chat-say="${esc(t)}">${esc(t)}</button>`).join('');
 $('chatLog').scrollTop=$('chatLog').scrollHeight;
}
async function sendChat(text){
 if(chatBusy||!text)return;chatBusy=true;chat.push({who:'user',text},{who:'bot',text:'로컬 AI가 수집된 정책에서 찾고 있어요…'});renderChat();
 try{const r=await api('/api/integrations/ontong/ask','POST',{message:text,profile:mine()});
  chat[chat.length-1]={who:'bot',text:r.answer,items:r.items,total:r.total,keywords:r.keywords,suggest:Object.keys(r.profile_suggestion).length?r.profile_suggestion:null,tools:r.tools,notice:r.notice,asked:text};
 }catch(e){chat[chat.length-1]={who:'bot',text:e.message}}
 chatBusy=false;renderChat();
}
function toast(message){$('toast').textContent=message;$('toast').hidden=false;clearTimeout(toastTimer);toastTimer=setTimeout(()=>$('toast').hidden=true,4500)}
async function action(fn){if(loading)return;loading=true;try{await fn()}catch(e){toast(e.message)}finally{loading=false}}
function endpoint(suffix=''){if(!space)throw new Error('준비 공간을 불러오는 중이에요.');return '/api/desk/workspaces/'+encodeURIComponent(space.id)+suffix}
function saved(id){return space?.bookmarks.some(p=>p.external_id===id)}
function cards(rows){return rows.map(p=>`<article class="policy-card" data-policy-id="${esc(p.external_id)}"><div class="card-top"><span class="badge">${esc(p.category||'관심 정책')}</span><button class="save-icon ${saved(p.external_id)?'saved':''}" data-save="${esc(p.external_id)}" aria-label="${esc(p.name)} ${saved(p.external_id)?'관심 해제':'관심 저장'}" aria-pressed="${saved(p.external_id)?'true':'false'}">${saved(p.external_id)?'★':'☆'}</button></div><h3>${esc(p.name)}</h3>${p.application_hint?`<span class="period-label ${esc(p.application_hint.kind)}">${esc(p.application_hint.label)}</span>`:""}${label(p)}<p class="agency">${esc(p.agency||'기관 안내 확인 필요')}</p><p class="card-summary">${esc(p.summary||(p.screen?.to_confirm.length?'공고에서 확인할 것: '+p.screen.to_confirm.map(k=>CRITERIA[k]).join(', '):'')||'공식 안내에서 지원 내용과 조건을 확인해 주세요.')}</p><div class="card-bottom"><span>${p.source_check?'원문 대조 기록 있음':'자격·모집 여부 확인 필요'}</span><button class="text-button" data-open="${esc(p.external_id)}">자세히 보기 ↗</button></div></article>`).join('')}
function empty(title,description){return `<div class="empty"><strong>${esc(title)}</strong><p>${esc(description)}</p><button class="button primary" data-go-explore>정책 찾아보기 →</button></div>`}
function renderWorkspace(){
 if(!space)return;
 const current=space.tasks.filter(t=>!t.outdated),done=current.filter(t=>t.status==='done').length;
 $('savedCount').textContent=space.bookmarks.length;$('taskCount').textContent=current.filter(t=>t.status!=='done').length;
 $('resumeCount').textContent=current.length?`${current.length-done}개 남았어요 · ${done}개 완료`:'첫 준비를 시작해 보세요';
 $('savedGrid').innerHTML=space.bookmarks.length?cards(space.bookmarks):empty('마음에 드는 정책을 모아보세요','정책 카드의 별을 누르면 여기에 저장됩니다.');
 $('progressText').textContent=`${done} / ${current.length} 완료`;$('progressBar').max=Math.max(1,current.length);$('progressBar').value=done;
 const groups=Map.groupBy?Map.groupBy(space.tasks,t=>t.external_id):space.tasks.reduce((m,t)=>(m.has(t.external_id)?m.get(t.external_id).push(t):m.set(t.external_id,[t]),m),new Map());
 $('tasksList').innerHTML=space.tasks.length?Array.from(groups,([id,tasks])=>`<section class="task-group"><div class="task-heading"><h3>${esc(tasks[0].policy_name)}</h3><button class="text-button" data-open="${esc(id)}">정책 확인 ↗</button></div>${tasks.map(t=>`<label class="task-item ${t.status==='done'?'done':''}"><input type="checkbox" data-task="${esc(t.id)}" ${t.status==='done'?'checked':''} ${t.outdated?'disabled':''} aria-label="${esc(t.title)} 완료"><span><strong>${esc(t.title)}</strong><p>${esc(t.instructions)}</p>${t.outdated?'<span class="stale">자료가 변경됐어요. 정책 상세에서 준비할 일을 다시 승인해 주세요.</span>':''}<span>${t.sources.map(s=>`<a href="${esc(s.url)}" target="_blank" rel="noopener noreferrer">${esc(s.title)} ↗</a>`).join('')}</span></span></label>`).join('')}</section>`).join(''):empty('첫 번째 준비를 시작해 보세요','정책 상세에서 준비할 일을 확인하고 승인하면 이곳에 담깁니다.');
 if(results.length)$('policyGrid').innerHTML=cards(results);
 if(activePolicy)$('detailSave').textContent=saved(activePolicy.external_id)?'★ 관심 정책 저장됨 · 해제':'☆ 관심 정책 저장';
}
async function refreshSpace(){space=await api(endpoint());renderWorkspace()}
function switchTab(next){tab=next;$('chatFab').hidden=next==='profile';for(const name of ['explore','saved','tasks','profile'])$(name+'View').hidden=name!==next;document.querySelectorAll('[data-tab]').forEach(b=>{b.classList.toggle('active',b.dataset.tab===next);if(b.dataset.tab===next)b.setAttribute('aria-current','page');else b.removeAttribute('aria-current')});window.scrollTo({top:0,behavior:'smooth'})}
async function search(){
 $('resultCount').textContent='정책을 찾고 있어요…';
 const category=$('category').value;
 const params=new URLSearchParams({q:$('searchInput').value.trim(),category,page:String(page),page_size:'12',application_code:$('applicationCode').value,job_code:$('jobCode').value,income_code:$('incomeCode').value});
 const selected=['applicationCode','jobCode','incomeCode'].filter(id=>$(id).value).length;
 $('filterCount').textContent=selected?`${selected}개 선택`:'';
 const on=compared();
 $('finderChip').innerHTML=on&&finder?`<button class="text-button" id="finderClear">‘${esc(finder.keywords.join('·'))}’ 찾는 중 ×</button>`:'';
 const r=on?await api('/api/integrations/ontong/screen','POST',{profile:mine(),q:params.get('q'),category,outcome:$('screenOutcome').value,keywords:finder?.keywords||[],page,page_size:12}):await api('/api/integrations/ontong/search?'+params);results=r.items;
 if(r.categories)$('category').innerHTML='<option value="">전체 분야</option>'+r.categories.map(c=>`<option value="${esc(c)}" ${category===c?'selected':''}>${esc(c)}</option>`).join('');
 $('resultCount').textContent=on?`맞아요 ${r.outcomes.api_match.toLocaleString()} · 확인 필요 ${r.outcomes.needs_check.toLocaleString()} · 달라요 ${r.outcomes.api_mismatch.toLocaleString()} · 원문 링크만 ${r.tiers.link_only.toLocaleString()}`:`${r.total.toLocaleString()}개의 정책`;
 $('policyGrid').innerHTML=results.length?cards(results):'<div class="empty"><strong>검색 결과가 없어요</strong><p>정책명 대신 지역이나 다른 단어로 검색해 보세요.</p><button class="button subtle" id="resetEmpty">검색 조건 초기화</button></div>';
 $('pageLabel').textContent=r.pages?`${page} / ${r.pages}`:'0 / 0';$('prevPage').disabled=page<=1;$('nextPage').disabled=page>=r.pages;
}
async function toggleSave(id){if(saved(id))await api(endpoint('/bookmarks/'+encodeURIComponent(id)),'DELETE');else await api(endpoint('/bookmarks/'+encodeURIComponent(id)),'PUT');await refreshSpace();toast(saved(id)?'관심 정책에 저장했어요.':'관심 정책에서 해제했어요. 준비 작업은 유지됩니다.')}
async function openPolicy(id){
 const version=++dialogVersion;activePolicy=null;activePlan=null;
 $('detailLoading').hidden=false;$('detailBody').hidden=true;$('previewSection').hidden=true;$('aiAnswer').textContent='';$('aiStatus').textContent='';$('aiQuestion').value='';$('askPolicy').disabled=false;
 if(!$('policyDialog').open)$('policyDialog').showModal();
 try{
  const [bundle,plan,cmp]=await Promise.all([api('/api/integrations/ontong/candidates/'+encodeURIComponent(id)),api(endpoint('/policies/'+encodeURIComponent(id)+'/preview')),compared()?api('/api/integrations/ontong/candidates/'+encodeURIComponent(id)+'/screen','POST',mine()):null]);
  if(version!==dialogVersion)return;
  activePolicy=bundle;activePlan=plan;const p=bundle.public_fields,check=bundle.source_check;
  $('detailTitle').textContent=p.plcyNm;$('detailAgency').textContent=p.sprvsnInstCdNm||'기관 안내 확인 필요';
  const decoded=bundle.decoded;
  $('detailCompare').innerHTML=!cmp?'':'<h3>내 정보와 API 조건 비교</h3>'+(cmp.screen?'<dl>'+cmp.screen.criteria.filter(c=>c.result!=='skipped').map(c=>`<div><dt>${CRITERIA[c.key]} <span class="period-label ${RESULT_LABEL[c.result][0]}">${RESULT_LABEL[c.result][1]}</span></dt><dd>${esc(c.basis)}</dd></div>`).join('')+'</dl>':'<p class="small">마감됐거나 API 정보가 부족해 조건을 비교하지 않았어요. 공고 원문에서 확인해 주세요.</p>')+`<p class="small">${esc(cmp.notice)}</p>`;
  $('detailCodes').innerHTML=decoded?'<h3>API 조건 읽기</h3><dl>'+decoded.fields.filter(f=>!f.missing).map(f=>`<div><dt>${esc(f.title)}</dt><dd>${esc([...f.labels,...f.unknown_codes.map(c=>'미확인 코드 '+c)].join(', '))}</dd></div>`).join('')+`</dl><p class="small">${esc(decoded.notice)}</p><p class="small">${esc(decoded.income.notice)}</p><p class="small">${esc(decoded.region.notice)}</p>`:'';
  $('detailQuestions').innerHTML='<h3>먼저 확인할 질문</h3><ol>'+(bundle.questions||[]).map(q=>`<li>${esc(q.question)}</li>`).join('')+'</ol>';
  $('detailBadges').innerHTML=`<span class="badge">${esc(p.lclsfNm||'정책 안내')}</span> <span class="badge warn">전체 조건 검수 전</span>`;
  $('detailEvidence').innerHTML=check?`<strong>${check.api_changed_since_check?'수집 자료가 바뀌어 재대조가 필요해요':check.official_status==='closed'?'확인한 공식 공고는 접수가 끝났어요':'공식 안내 대조 기록'}</strong><p>${esc(check.summary)}</p><p>${esc(check.official_period_text)}</p><p>확인일 ${esc(check.checked_on)} · 전체 자격 판정은 아닙니다.</p>`:'<strong>신청 전에 공식 모집공고를 확인해 주세요</strong><p>온통청년 수집 정보입니다. 실제 신청기간·자격·중복 수혜 조건은 아직 모두 검수하지 않았어요.</p>';
  const fields=[['지원 내용',p.plcySprtCn||p.plcyExplnCn],['API에 기재된 신청기간',p.aplyYmd],['추가 신청 조건',p.addAplyQlfcCndCn],['참여 제한 안내',p.ptcpPrpTrgtCn],['제출서류 안내',p.sbmsnDcmntCn],['신청 방법',p.plcyAplyMthdCn]];
  $('detailFields').innerHTML=fields.map(([title,value])=>`<section class="detail-field"><h3>${esc(title)}</h3><p>${esc(value||'수집 자료에 기재되지 않았어요. 조건이나 서류가 없다는 의미가 아니므로 공식 공고를 확인해 주세요.')}</p></section>`).join('');
  $('detailSources').innerHTML=plan.tasks[0]?.sources.map(s=>`<a href="${esc(s.url)}" target="_blank" rel="noopener noreferrer">${esc(s.title)} ↗</a>`).join('')||'<p class="small">사용 가능한 원문 링크가 없어요. 담당 기관의 공식 사이트에서 공고를 확인해 주세요.</p>';
  $('previewTasks').innerHTML=plan.tasks.map((t,i)=>`<div class="preview-item"><strong>${i+1}. ${esc(t.title)}</strong><p>${esc(t.instructions)}</p></div>`).join('');
  $('detailSave').textContent=saved(id)?'★ 관심 정책 저장됨 · 해제':'☆ 관심 정책 저장';
  $('aiReady').textContent=health?.llm_enabled?'로컬 AI 연결됨':'연결 상태 다시 확인';
  $('detailLoading').hidden=true;$('detailBody').hidden=false;
 }catch(e){if(version===dialogVersion)$('detailLoading').textContent=e.message}
}
async function ask(){
 if(!activePolicy)return;const message=$('aiQuestion').value.trim()||'이 정책은 무엇부터 확인해야 해?';
 const version=dialogVersion,id=activePolicy.external_id;$('askPolicy').disabled=true;$('aiStatus').textContent='로컬 AI가 정책 자료와 준비 작업을 조회하고 있어요. 첫 실행에는 시간이 걸릴 수 있어요.';$('aiAnswer').textContent='';
 try{
  const r=await api(endpoint('/assistant'),'POST',{external_id:id,message});
  if(version!==dialogVersion)return;
  const context=r.evidence_context;
  $('aiAnswer').innerHTML=(context?`<div class="evidence-box"><strong>기록된 공식 접수기간</strong><p>${esc(context.period)}</p><p>원문 대조일: ${esc(context.checked_on)}</p><p>${esc(context.note)}</p></div>`:'')+`<p>${esc(r.answer)}</p><p class="small">실행한 도구: ${r.tools.map(t=>t.tool==='read_policy'?'정책 자료 조회':'준비 작업 조회').join(' → ')}</p><p class="small">${esc(r.notice)}</p>`;$('aiStatus').textContent='조회 완료 · 준비 작업은 아직 저장하지 않았어요.';
 }catch(e){if(version===dialogVersion)$('aiStatus').textContent=e.message}
 finally{if(version===dialogVersion)$('askPolicy').disabled=false}
}
async function init(){
 try{
  let wid=localStorage.getItem('youth-desk-workspace');
  if(wid){try{space=await api('/api/desk/workspaces/'+encodeURIComponent(wid))}catch(e){if(e.status!==404)throw e;wid=null}}
  if(!wid){const created=await api('/api/desk/workspaces','POST');localStorage.setItem('youth-desk-workspace',created.id);space=await api('/api/desk/workspaces/'+encodeURIComponent(created.id))}
  const codebook=await api('/api/integrations/ontong/codebook');
  for(const [id,field] of [['applicationCode','aplyPrdSeCd'],['jobCode','jobCd'],['incomeCode','earnCndSeCd']]){
   $(id).innerHTML='<option value="">전체</option>'+Object.entries(codebook.groups[field].codes).map(([code,item])=>`<option value="${esc(code)}">${esc(item.label)}</option>`).join('');
  }
  const regions=await api('/api/integrations/ontong/regions');names.sido=regions.sido;
  // '제한없음'은 정책 쪽 표기라 내 상태로 고를 수 없다.
  for(const [key,field,skip] of [['job_code','jobCd','0013010'],['school_code','schoolCd','0049010']])names[key]=Object.fromEntries(Object.entries(codebook.groups[field].codes).filter(([code])=>code!==skip).map(([code,item])=>[code,item.label]));
  for(const [id,key] of [['pSido','sido'],['pJob','job_code'],['pSchool','school_code']])$(id).innerHTML+=Object.entries(names[key]).sort((a,b)=>key==='sido'?a[1].localeCompare(b[1],'ko'):0).map(([code,name])=>`<option value="${esc(code)}">${esc(name)}</option>`).join('');
  renderProfile();renderWorkspace();await search();
  if(!profile)switchTab('profile');
  const state=await api('/api/integrations/ontong');$('catalogCount').textContent=`저장된 정책 ${state.candidate_count.toLocaleString()}개`;
  health=await api('/api/health');
 }catch(e){$('fatal').hidden=false;$('fatal').textContent=e.message+' 페이지를 새로고침해 주세요.'}
}
document.addEventListener('DOMContentLoaded',()=>{
 $('searchForm').onsubmit=e=>{e.preventDefault();action(async()=>{page=1;await search()})};$('category').onchange=()=>action(async()=>{page=1;await search()});
 $('clearSearch').onclick=()=>action(async()=>{$('searchInput').value='';$('category').value='';for(const id of ['applicationCode','jobCode','incomeCode'])$(id).value='';finder=null;$('screenOutcome').value='';page=1;await search()});
 const applyProfile=next=>action(async()=>{saveProfile(next);finder=null;$('screenOutcome').value='';page=1;switchTab('explore');await search();toast(compared()?'내 정보 기준으로 다시 찾았어요.':'정보 없이 전체 정책을 보여드려요.')});
 $('profileForm').onsubmit=e=>{e.preventDefault();const age=$('pAge').value.trim(),n=age===''?null:Number(age);
  if(n!==null&&(!Number.isInteger(n)||n<0||n>120)){toast('나이는 0~120 사이의 숫자로 입력해 주세요.');return}
  applyProfile({...(profile?.name?{name:profile.name}:{}),age:n,sido:$('pSido').value,job_code:$('pJob').value,school_code:$('pSchool').value})};
 $('profileDemo').onclick=()=>applyProfile(DEMO);$('profileSkip').onclick=()=>applyProfile({});
 $('chatFab').onclick=()=>{renderChat();if(!$('chatDialog').open)$('chatDialog').showModal();$('chatInput').focus()};$('closeChat').onclick=()=>$('chatDialog').close();
 $('chatForm').onsubmit=e=>{e.preventDefault();const text=$('chatInput').value.trim();$('chatInput').value='';sendChat(text)};
 $('screenOutcome').onchange=()=>{if(profile)action(async()=>{page=1;await search()})};
 for(const id of ['applicationCode','jobCode','incomeCode'])$(id).onchange=()=>action(async()=>{page=1;await search()});
 $('prevPage').onclick=()=>action(async()=>{page=Math.max(1,page-1);await search()});$('nextPage').onclick=()=>action(async()=>{page++;await search()});
 document.addEventListener('click',e=>{
  const target=e.target.closest('button');if(!target)return;
  if(target.dataset.tab)switchTab(target.dataset.tab);
  if(target.hasAttribute('data-go-explore'))switchTab('explore');
  if(target.hasAttribute('data-go-tasks'))switchTab('tasks');
  if(target.dataset.query)action(async()=>{$('searchInput').value=target.dataset.query;$('category').value='';page=1;await search()});
  if(target.dataset.open)action(()=>openPolicy(target.dataset.open));
  if(target.dataset.save)action(()=>toggleSave(target.dataset.save));
  if(target.id==='resetEmpty')$('clearSearch').click();
  if(target.id==='finderClear')action(async()=>{finder=null;page=1;await search()});
  if(target.dataset.chatSay)sendChat(target.dataset.chatSay);
  if(target.dataset.chatApply){const m=chat[target.dataset.chatApply];saveProfile({...(profile||{}),...m.suggest});m.suggest=null;sendChat(m.asked)}
  // 내 정보가 없으면 조건 비교를 할 수 없어 첫 검색어로 이름 검색을 한다.
  if(target.dataset.chatMore){const m=chat[target.dataset.chatMore];if(compared())finder={keywords:m.keywords};else $('searchInput').value=m.keywords[0]||'';$('chatDialog').close();switchTab('explore');action(async()=>{page=1;await search()})}
 });
 $('tasksList').onchange=e=>{if(e.target.dataset.task){const box=e.target;action(async()=>{try{await api(endpoint('/tasks/'+encodeURIComponent(box.dataset.task)),'PATCH',{status:box.checked?'done':'todo'});await refreshSpace()}catch(error){box.checked=!box.checked;throw error}})}};
 $('closeDialog').onclick=()=>$('policyDialog').close();$('policyDialog').addEventListener('close',()=>{dialogVersion++;activePolicy=null;activePlan=null});
 $('detailSave').onclick=()=>action(()=>toggleSave(activePolicy.external_id));
 $('showPreview').onclick=()=>{$('previewSection').hidden=false;$('previewSection').scrollIntoView({behavior:'smooth',block:'start'})};
 $('approvePlan').onclick=()=>action(async()=>{
  if(!activePolicy||!activePlan)return;
  try{space=await api(endpoint('/policies/'+encodeURIComponent(activePolicy.external_id)+'/confirm'),'POST',{approved:true,preview_token:activePlan.preview_token});renderWorkspace();$('policyDialog').close();switchTab('tasks');toast('확인한 작업을 준비판에 저장했어요.')}
  catch(e){if(e.status===409){await openPolicy(activePolicy.external_id);$('previewSection').hidden=false}throw e}
 });
 $('askPolicy').onclick=ask;
 init();
});
