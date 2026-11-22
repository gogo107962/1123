'use strict';
// 팀 앱 화면(청년비서_앱.html)의 구성과 스타일을 실제 온통청년 자료에 연결한 앱 화면.
// 판정 표현은 '등록 정보 비교'로 쓴다. 사람 검수 전 정책에는 '신청 가능'이라고 하지 않는다.
const $=s=>document.querySelector(s);
const esc=v=>String(v??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
const n=v=>Number(v||0).toLocaleString();
const store={get(k,d){try{return JSON.parse(localStorage.getItem(k))??d}catch{return d}},set(k,v){try{localStorage.setItem(k,JSON.stringify(v))}catch{}}};
const DEMO={name:'민지',birth:'2000-03',moved:'2024-02',age:26,sido:'28',region_code:'28177',job_code:'0013003',school_code:'',household:1,housing:'월세',exams:[{name:'정보처리기사',month:(d=>{d.setDate(1);d.setMonth(d.getMonth()-1);return d.getFullYear()+'-'+String(d.getMonth()+1).padStart(2,'0')})(new Date())}]};
// 오늘 날짜(한국 시간). D-day와 접수 상태는 서버가 요청 때마다 오늘 기준으로 계산하고, 화면은 날짜가 바뀌면 다시 불러온다.
const today=()=>new Date(Date.now()+9*3600e3).toISOString().slice(0,10);
// 지원 찾기의 종류 버튼. 앞의 다섯은 정책 대분류, 'k:'로 시작하는 둘은 글에서 찾는 낱말이다.
const KINDS=[['','전체'],['일자리','일자리'],['주거','주거'],['교육･직업훈련','교육 · 훈련'],['금융･복지･문화','금융 · 복지 · 문화'],['참여･기반','참여 · 기반'],['k:자격증,응시료','자격증 · 시험'],['k:어학','어학']];
const AGES=[['0-18','18세 이하'],['19-24','19~24세'],['25-29','25~29세'],['30-34','30~34세'],['35-39','35~39세'],['40-120','40세 이상']];
const WHO={orchestrator:'대화 오케스트레이터',slots:'내 정보 확인',engine:'판별 엔진',planner:'충돌·순서 플래너',docboard:'서류 준비판',question:'질문 선택기',output:'출력 검사'};
const CIRC='①②③④',HOWMANY=['','한','두','세','네'];
const NOFILTER={q:'',outcome:'',kind:'',sido:'',ages:'',open:false};
const shortSido=name=>({'충청북도':'충북','충청남도':'충남','경상북도':'경북','경상남도':'경남','전남광주통합특별시':'전남 · 광주'})[name]||name.replace(/(특별자치도|특별자치시|특별시|광역시|도)$/,'');
const OUT={api_match:['조건 맞아요','ok'],needs_check:['확인 필요','warn'],api_mismatch:['조건 달라요','bad']};
const RES={match:['맞아요','ok'],unknown:['확인 필요','warn'],mismatch:['달라요','bad']};
const CRIT={period:'신청기간',age:'나이',region:'거주지',income:'소득',job:'취업 상태',school:'학력',major:'전공',marriage:'결혼',exclusion:'참여 제한',target:'대상',apply:'신청 방법',exam:'대상 시험',housing:'주거'};
const PERIOD={open:'접수 중',rolling:'상시',upcoming:'시작 전',unknown:'기간 확인 필요',ended:'신청기간 지남',closed_code:'마감',closed_official:'공식 공고 종료'};
const REASON={closed:'마감됐어요',no_application_route:'신청 방법 정보가 없어요',no_region_code:'지역 정보가 없어요'};
const TOPICS={'자격증 응시료':'자격증 시험 쳤는데 응시료 지원받을 수 있어?','월세 지원':'월세 지원 받을 수 있어?','구직 수당':'취업 준비 중인데 구직 수당 받을 수 있어?','교통비':'교통비 지원 받을 수 있어?'};
const CATS=[['응시료','school','자격증 응시료'],['주거','home_work','월세 지원'],['취업','work','구직 수당'],['생활','directions_bus','교통비']];
const ENGINE={review_possible:['신청 검토 가능','ok'],ineligible:['조건 불충족','bad'],needs_review:['확인 필요','warn'],application_closed:['신청 기간 아님','gray']};
const EFFECT={pass:['충족','ok'],block:['불충족','bad'],unknown:['확인 필요','warn']};
const FIELD={documents:'제출서류',period:'신청 시기',method:'신청 방법',conditions:'대상 · 조건'};
const TOOLS={keyword_match:'낱말로 찾기',search_policies:'정책 검색',screen_profile:'내 정보와 조건 비교',plan_applications:'충돌·순서 플래너',prepare_documents:'서류 준비판'};
const ME=`<svg class="av" viewBox="0 0 80 80" aria-hidden="true"><rect width="80" height="80" fill="#FFE2B8"/><ellipse cx="40" cy="80" rx="28" ry="20" fill="#7FA0F5"/><circle cx="40" cy="37" r="18" fill="#FFEEDD"/><path d="M21 36 Q20 15 40 15 Q60 15 59 36 Q52 25 40 27 Q28 25 21 36 Z" fill="#4A3528"/><circle cx="33.5" cy="39" r="2.2" fill="#3A2E2A"/><circle cx="46.5" cy="39" r="2.2" fill="#3A2E2A"/><path d="M35.5 45.5 Q40 49.5 44.5 45.5" fill="none" stroke="#3A2E2A" stroke-width="1.8" stroke-linecap="round"/></svg>`;
const S={screen:'login',back:[],sheet:null,planTab:false,listTab:false,profile:store.get('youth-desk-profile',null),draft:null,
 names:{sido:{},sigungu:{},job_code:{},school_code:{}},benefits:[],groups:[],space:null,counts:null,query:{keywords:[],q:'',outcome:''},list:null,
 selected:store.get('youth-desk-selected',{}),docs:store.get('youth-desk-docs',{}),detail:null,detailId:null,plan:null,chat:[],busy:false};

async function api(path,method='GET',body){
 const response=await fetch(path,{method,headers:{'Content-Type':'application/json'},body:body===undefined?undefined:JSON.stringify(body)});
 let data;try{data=await response.json()}catch{throw new Error('서버 응답을 읽지 못했어요. 연결 상태를 확인해 주세요.')}
 if(!response.ok){const error=new Error(typeof data.detail==='string'?data.detail:'입력값을 확인해 주세요.');error.status=response.status;throw error}return data;
}
const space=(suffix='')=>'/api/desk/workspaces/'+encodeURIComponent(S.space.id)+suffix;
// 서버에는 비교에 쓰는 값만 보낸다. 이름은 브라우저에만 둔다.
// 출생 연월·전입한 달은 보낼 때마다 오늘 기준 나이·거주 기간으로 바꾼다. 거주 기간은 구간의 아래쪽 값(개월)이다.
const monthsSince=m=>{if(!m)return null;const [y,mo]=m.split('-').map(Number),now=new Date();return (now.getFullYear()-y)*12+now.getMonth()+1-mo};
const ageOf=b=>{const m=monthsSince(b);return m==null||m<0?null:Math.floor(m/12)};
const stayed=m=>{const v=monthsSince(m);return v==null||v<0?null:[60,36,24,12,6,0].find(x=>v>=x)};
const ym=m=>m?`${+m.slice(0,4)}년 ${+m.slice(5,7)}월`:'';
const mine=(p=S.profile)=>({age:p?.birth?ageOf(p.birth):p?.age??null,sido:p?.sido||null,region_code:p?.region_code||null,job_code:p?.job_code||null,school_code:p?.school_code||null,benefits:p?.benefits??null,groups:p?.groups??null,income_monthly:p?.income_monthly??null,income_band:p?.income_band||null,household:p?.household||null,residence_months:p?.moved?stayed(p.moved):p?.residence_months??null,income_bracket:p?.income_bracket??null,business:p?.business==='yes'?true:p?.business==='no'?false:null,exams:p?.exams?.length?p.exams.map(x=>x.name):null,housing:p?.housing||null});
// '받는 지원 없음'만으로는 비교했다고 하지 않는다(서버의 provided와 같은 기준).
const compared=()=>Object.values(mine()).some(v=>v!==null&&!(Array.isArray(v)&&!v.length));
// 출처 페이지에서 인용 문장이 자동 대조로 확인된 보완 기록인가
const sure=x=>(x.auto_check??'found')==='found';
const short=t=>String(t).replace(/\s*\(.*?\)/g,'');   // 'D-2' → 'D-2'
// 내 신청에 저장해 둔 정책(최대 5개). 고른 정책이 없을 때 내 신청 탭은 이 정책들의 서류와 순서를 보여 준다.
const savedIds=()=>[...new Set((S.space?.tasks||[]).filter(t=>!t.outdated).map(t=>t.external_id))].slice(0,5);
const planIds=()=>S.only&&S.selected[S.only]?[S.only]:selIds().length?selIds():S.planTab?savedIds():[];
const money=x=>x.amounts?.length?'글에 적힌 금액: '+x.amounts.map(a=>a.text).join(', '):'';
// 공식 사이트 링크: 공고(대조 출처 · 참고 안내), 신청 페이지, 온통청년의 정책 페이지. 온통청년 주소는 정책번호로 만들어 모든 정책에 있다.
const PORTAL=id=>'https://www.youthcenter.go.kr/youthPolicy/ythPlcyTotalSearch/ythPlcyDetail/'+encodeURIComponent(id);
const official=(links,id)=>{const apply=links.find(x=>x.title==='신청 안내 사이트'),notice=links.find(x=>x!==apply);return {apply,notice,all:[notice&&['공식 공고',notice.url],apply&&['신청 페이지',apply.url],['온통청년 정책 페이지',PORTAL(id)]].filter(Boolean)}};
const sites=(links,id)=>`<div class="pills">${official(links,id).all.map(([t,u])=>`<a class="btn line sm" href="${esc(u)}" target="_blank" rel="noopener noreferrer">${t}</a>`).join('')}</div>`;
// 예상 지원 금액: 제공 방법이 보조금 · 바우처인 정책의 글에 적힌 금액만 더한 값(서버 계산). 대출 · 보증은 한도라 따로 적는다.
const won=k=>k>=1e8?`${+(k/1e8).toFixed(2)}억 원`:`${Math.round(k/1e4).toLocaleString()}만 원`;
const est=P=>{const e=P.estimate,by=Object.fromEntries(P.policies.map(x=>[x.external_id,x])),parts=[e.monthly_krw?`매달 ${won(e.monthly_krw)}`:'',e.other_krw?(e.monthly_krw?'그 밖에 ':'')+won(e.other_krw):''].filter(Boolean);
 return (parts.length?`<p class="s14" style="margin:8px 0 0">예상 지원 금액 <strong class="h18">${parts.join(' + ')}</strong></p><p class="tiny">글에 적힌 금액 기준 · ${e.used.map(x=>esc(by[x.external_id].name)+' '+esc(x.text)).join(' · ')}</p>`:'')
  +(e.loans.length?`<p class="tiny">대출 · 보증 ${e.loans.length}건은 한도라서 더하지 않았어요: ${e.loans.map(id=>esc(by[id].name)+(by[id].amounts[0]?' '+esc(by[id].amounts[0].text):'')).join(', ')}</p>`:'')
  +(e.unsure.length?`<p class="tiny">${e.unsure.length}건은 지원금으로 등록돼 있지 않거나 금액 표현이 분명하지 않아 더하지 않았어요: ${e.unsure.map(id=>esc(by[id].name)).join(', ')}</p>`:'')};
const area=p=>[S.names.sido[p?.sido||p?.region_code?.slice(0,2)],S.names.sigungu[p?.region_code]].filter(Boolean).join(' ');
const chips=(p=mine())=>[p.age!=null?p.age+'세':'',area(p),S.names.job_code[p.job_code],S.names.school_code[p.school_code],p.income_monthly!=null?`월 ${p.income_monthly}만원`:'',p.household?`${p.household}인 가구`:'',...(p.groups||[]),...(p.benefits||[])].filter(Boolean);
const tasks=()=>(S.space?.tasks||[]).filter(t=>!t.outdated);
const selIds=()=>Object.keys(S.selected);
// 아이콘은 글꼴을 내려받지 않고 그린다(팀 앱 화면의 선 아이콘과 같은 모양).
const ICON={home:'<path d="m3 10 9-7 9 7v10a1 1 0 0 1-1 1h-5v-7H9v7H4a1 1 0 0 1-1-1Z"/>',search:'<circle cx="10.5" cy="10.5" r="6.5"/><path d="m16 16 5 5"/>',
 checklist:'<rect x="5" y="4" width="15" height="17" rx="3"/><path d="M9 3h7v4H9zM9 12l2 2 4-4M9 18h6"/>',notifications:'<path d="M5 17h14l-2-3V9a5 5 0 0 0-10 0v5ZM10 21h4"/>',
 person:'<circle cx="12" cy="8" r="4"/><path d="M4 21v-2a8 8 0 0 1 16 0v2"/>',description:'<path d="M14 3H6a1 1 0 0 0-1 1v16a1 1 0 0 0 1 1h12a1 1 0 0 0 1-1V8ZM14 3v5h5M9 12h6M9 16h6"/>',
 chevron_right:'<path d="m9 5 7 7-7 7"/>',arrow_back:'<path d="m15 5-7 7 7 7"/>',school:'<path d="m2 8 10-5 10 5-10 5ZM6 10v6q6 5 12 0v-6M22 8v8"/>',
 home_work:'<path d="m3 10 7-6 7 6v10H3ZM8 20v-6h4v6M16 3h5v17h-4M18 7h1M18 11h1"/>',work:'<rect x="3" y="7" width="18" height="14" rx="3"/><path d="M8 7V3h8v4M3 12q9 6 18 0M12 12v4"/>',
 directions_bus:'<rect x="5" y="3" width="14" height="17" rx="4"/><path d="M5 10h14M8 20v2M16 20v2M8 15h1M15 15h1"/>',add:'<path d="M12 4v16M4 12h16"/>',close:'<path d="m5 5 14 14M5 19 19 5"/>',
 auto_awesome:'<path d="m12 3 3 6 6 3-6 3-3 6-3-6-6-3 6-3ZM20 2v4M18 4h4"/>',arrow_upward:'<path d="M12 21V3m-7 7 7-7 7 7"/>',attach_file:'<path d="m8 13 7-7a3 3 0 0 1 4 4L9 20a5 5 0 0 1-7-7L13 2"/>'};
const ms=name=>`<span class="ms" aria-hidden="true"><svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.7" stroke-linecap="round" stroke-linejoin="round">${ICON[name]}</svg></span>`;
const pill=(t,k='gray')=>`<span class="pill ${k}">${t}</span>`;
const prow=(l,v)=>`<div class="prow"><span class="sub">${l}</span><span class="b" style="text-align:right">${esc(v)}</span></div>`;
const bar=(title,b,trailing='')=>`<header>${b?`<button class="ib" data-a="back" aria-label="${b==='x'?'챗봇 닫기':'뒤로'}">${ms(b==='x'?'close':'arrow_back')}</button>`:'<span class="sp"></span>'}<h1>${title}</h1>${trailing}</header>`;
const dock=a=>`<div class="bottom-dock"><nav aria-label="주 메뉴">${[['home','home','홈'],['browse','search','지원 찾기'],['plan','checklist','내 신청'],['profile','person','내 정보']].map(([k,i,l])=>`<button class="tab ${a===k?'on':''}" data-a="tab" data-s="${k}" ${a===k?'aria-current="page"':''}><span class="ti">${ms(i)}</span><span>${l}</span></button>`).join('')}</nav><button class="dock-chat" data-a="openchat" aria-label="청년비서 챗봇 열기"><svg viewBox="0 0 40 40" fill="none" aria-hidden="true"><path d="M10 9h20a6 6 0 0 1 6 6v10a6 6 0 0 1-6 6H18l-8 5v-5a6 6 0 0 1-6-6V15a6 6 0 0 1 6-6Z" fill="#e8edf1"/><path d="M12 19h16M12 24h10" stroke="#576d7d" stroke-width="2.5" stroke-linecap="round"/><circle cx="30" cy="10" r="5" fill="#e9d465"/></svg></button></div>`;
const wait=title=>bar(title,'b')+`<main class="pad"><p class="sub">불러오는 중…</p></main>`;

function toast(text){let el=$('#toast');if(!el){el=document.createElement('div');el.id='toast';el.className='toast';el.setAttribute('role','status');$('#app').append(el)}
 el.textContent=text;clearTimeout(toast.t);toast.t=setTimeout(()=>el.remove(),2600)}
function go(screen,replace){if(!replace)S.back.push(S.screen);S.screen=screen;S.sheet=null;render(true)}
function back(){S.screen=S.back.pop()||'home';S.sheet=null;render(true)}
function render(top){
 const old=$('#m'),typed=old?.value,focus=old&&document.activeElement===old,scroll=$('main')?.scrollTop||0;
 $('#view').innerHTML=V[S.screen]()+sheet();
 const input=$('#m');if(input&&typed)input.value=typed;if(input&&focus)input.focus();
 const main=$('main');if(main)main.scrollTop=S.screen==='chat'?main.scrollHeight:top?0:scroll;
}
async function run(fn){try{await fn()}catch(e){toast(e.message)}}

// ── 조건 대조에 쓰는 표시 값 ──
function cond(key,d){const st=d.bundle.structured,p=d.bundle.public_fields,a=st.age;
 // 긴 문장은 앞부분만 보여 주고, 전체 문장과 출처는 '더 보기'의 보완 정보에 있다.
 const said=(field,word)=>{const q=d.bundle.supplements.filter(x=>x.field===field&&sure(x)).flatMap(x=>x.quotes).find(q=>!word||q.includes(word));return q&&q.length>64?q.slice(0,62)+'…':q};
 if(key==='period')return said('period')?said('period')+' (공식 페이지)':p.aplyYmd||PERIOD[d.bundle.period_status];
 if(key==='income'&&said('conditions','소득'))return said('conditions','소득')+' (공식 페이지)';
 const found=key==='age'&&d.bundle.supplements.filter(sure).flatMap(x=>x.rules||[]).find(r=>r.predicate.fact==='age');
 if(found){const v=found.predicate.value,op=found.predicate.op;return (op==='gte'?`${v}세 이상`:op==='lte'?`${v}세 이하`:`${v[0]}~${v[1]}세`)+' (공식 페이지)'}
 if(key==='age')return a.kind==='range'?(a.max>=99?`${a.min}세 이상 (상한 ${a.max})`:`${a.min}~${a.max}세`):a.kind==='min_only'?`${a.min}세 이상`:a.kind==='max_only'?`${a.max}세 이하`:a.no_limit?'제한없음':'정보 없음';
 if(key==='region')return st.region.nationwide?'전국(시도 16곳 등록)':st.region.sido_names.join(', ')||'정보 없음';
 if(key==='exclusion')return st.exclusions.explicit_none?'해당 없음':`안내 ${st.exclusions.count}건`+(st.exclusions.kinds.length?` (${st.exclusions.kinds.join(', ')})`:'');
 if(key==='apply')return '정보 없음';
 if(key==='exam')return st.exam.kinds.length?'글에 적힌 종류: '+st.exam.kinds.join(', '):'응시료 지원 · 대상 시험은 공고에서 확인';
 if(key==='housing')return st.housing.no_home.length>64?st.housing.no_home.slice(0,62)+'…':st.housing.no_home;
 if(key==='target')return st.targets.join(', ');
 if(key==='income')return st.income.labels.concat(st.income.annual?[`${st.income.annual.max.toLocaleString()}만원 이하`]:[],st.income.median_pct.map(x=>`중위소득 ${x}%`)).join(', ')||'정보 없음';
 return st[key].labels.join(', ')||'정보 없음';}
function myValue(key){const p=mine();return {period:'오늘 기준',apply:'공고에서 확인',age:p.age!=null?p.age+'세':'',region:area(p),target:p.groups?.length?p.groups.join(', '):'해당 항목 선택 안 함',income:p.income_monthly!=null&&p.household?`월 ${p.income_monthly}만원 · ${p.household}인 가구`:'소득 입력 안 함',exclusion:p.benefits?.length?'받는 지원: '+p.benefits.join(', '):p.benefits?'받는 지원 없음':'받는 지원 입력 안 함',job:S.names.job_code[p.job_code],school:S.names.school_code[p.school_code],exam:p.exams?.join(', '),housing:p.housing}[key]||'입력 안 함'}
const noApply=d=>!!d.cmp?.screen?.criteria.some(c=>c.key==='apply');   // 신청 방법 미기재: 판정이 아니라 공식 사이트로 안내
const rows=d=>d.cmp?.screen?d.cmp.screen.criteria.filter(c=>c.result!=='skipped'&&c.counted!==false):[];   // 신청기간은 위쪽 표시로만 보여 준다

const V={
login:()=>`<main class="pad"><div class="login-intro"><h1 class="hero">공고는 저희가 읽을게요.<br>신청 준비만 하세요.</h1><p class="sub">청년비서 · 청년 지원 신청 준비 도우미</p></div>
<div class="col"><button class="btn" data-a="demo">데모 계정으로 시작</button><p class="sub c">가상 인물 '민지'의 정보로 바로 체험해요</p></div>
<div class="or"><span></span>또는<span></span></div><button class="btn line" data-a="start">내 정보 입력하고 시작</button>
<p class="tiny c mt">체험용 서비스예요. 실제 개인정보를 입력하지 마세요. 로그인 기능은 아직 없어요.</p></main>`,

home:()=>{const p=S.profile||{},t=tasks(),done=t.filter(x=>x.status==='done').length,c=S.counts,groups=new Set(t.map(x=>x.external_id)).size,next=t.find(x=>x.status!=='done'),top=c?.items[0],chev=ms('chevron_right'),hp=S.homePlan?.policies.length?S.homePlan:null,have=hp?hp.must.filter(d=>S.docs[d.key]).length:0,lack=hp?.must.find(d=>!S.docs[d.key]);
 return `<header class="home-head"><span class="wordmark">청년비서</span><button class="ib" data-a="notice" aria-label="알림">${ms('notifications')}</button></header>
<main class="pad home-main"><div class="greeting"><span>${esc(p.name||'체험 사용자')} 님</span><button data-a="tab" data-s="profile">${esc(area(p)||'내 정보 입력')} ${chev}</button></div>
<section class="balance-card"><div class="row"><h2>내가 준비 중인 지원</h2><span class="small-tag">저장한 정책</span></div><div class="balance-value">${groups}<span>건</span></div><p class="balance-caption">찾아둔 지원, 신청까지 차근차근</p>
<div class="account-actions"><button data-a="tab" data-s="browse">지원 더 찾기 ${ms('add')}</button><button data-a="tab" data-s="plan">내 신청 보기 ${chev}</button></div></section>
<section class="feed-card"><button class="section-heading" data-a="tab" data-s="plan">이어서 준비하기 ${chev}</button>
${t.length||hp?`<div class="policy-line"><span class="soft-icon yellow">${ms('description')}</span><div class="policy-copy"><strong>${esc(hp?hp.policies[0].name:t[0].policy_name)}</strong><span>${S.next?esc((S.next.nationwide?'전국':S.next.sido_names[0]||S.next.agency||'')+' · '):''}${hp&&hp.policies.length>1?`외 ${hp.policies.length-1}건 함께 준비`:t.length?`공고에서 확인할 일 ${t.length}개`:'신청 준비 중'}</span></div>${S.next?pill(esc(short(S.next.period_label)),S.next.period_status==='open'?'warn':'gray'):''}</div>
${hp&&hp.must.length?`<div class="prep-count"><span>서류 준비</span><strong>${have}<em> / ${hp.must.length}</em></strong></div><div class="prog"><div style="width:${have/hp.must.length*100}%"></div></div>
<button class="next-row" data-a="tab" data-s="plan"><span>${esc(lack?lack.name:'서류를 모두 준비했어요')}</span><span>${lack?'확인하기':'신청 전 점검으로'} ${chev}</span></button>`
 :`<div class="prep-count"><span>확인한 일</span><strong>${done}<em> / ${t.length}</em></strong></div><div class="prog"><div style="width:${t.length?done/t.length*100:0}%"></div></div>
<button class="next-row" data-a="tab" data-s="plan"><span>${esc(next?.title||(t.length?'모두 확인했어요':'서류 안내를 공고에서 확인해요'))}</span><span>확인하기 ${chev}</span></button>`}`
 :`<button class="next-row" style="margin-top:22px" data-a="tab" data-s="browse"><span>첫 지원 찾아보기</span>${chev}</button>`}</section>
<section class="feed-card"><button class="section-heading" data-a="tab" data-s="browse">나에게 필요한 지원 ${chev}</button>
<div class="category-grid">${CATS.map(([label,icon,topic])=>`<button class="category" data-a="topic" data-t="${topic}"><span class="category-icon">${ms(icon)}</span><span>${label}</span></button>`).join('')}</div></section>
<section class="feed-card"><button class="section-heading" ${compared()&&top?`data-a="detail" data-id="${esc(top.external_id)}"`:'data-a="tab" data-s="browse"'}>놓치기 전에 살펴봐요 ${chev}</button>
${!compared()?`<button class="next-row" style="margin-top:22px" data-a="tab" data-s="profile"><span>내 정보를 입력하면 맞는 지원부터 보여드려요</span>${chev}</button>`
 :!c?'<p class="sub" style="margin-top:14px">내 조건과 비교하고 있어요…</p>'
 :`${top?`<button class="recommend-line" data-a="detail" data-id="${esc(top.external_id)}"><span class="soft-icon mint">${ms('school')}</span><span class="policy-copy"><strong>${esc(top.name)}</strong><span>내 조건 확인하고 신청 준비하기</span></span>${chev}</button>`:''}
<details class="more" data-d="moreHome" ${S.moreHome?'open':''}><summary>내 조건과 비교한 결과 보기</summary><div class="pills">${pill('조건 맞아요 '+n(c.outcomes.api_match),'ok')}${pill('확인 필요 '+n(c.outcomes.needs_check),'warn')}${pill('조건 달라요 '+n(c.outcomes.api_mismatch),'bad')}</div>
<p class="tiny">온통청년에 등록된 값과 비교한 건수예요. 자격 판정이 아니에요. 중복 등록 ${n(c.merged)}건은 묶었고 ${n(c.tiers.link_only)}건은 비교하지 않았어요.</p></details>`}</section>
<button class="help-line" data-a="openchat">${ms('auto_awesome')} 복잡한 공고, 비서에게 물어보세요 ${chev}</button>
<p class="demo-note">가상 정보로 체험하는 화면이에요 · 정책 정보는 온통청년에서 가져왔어요</p></main>`+dock('home');},

chats:()=>{const list=store.get(CHATS,[]);
 return bar('이전 대화','b')+`<main class="pad">${list.length?list.map(x=>`<div class="card hist"><button class="cardbtn" data-a="oldchat" data-id="${esc(x.id)}"><span class="h16">${esc(x.title)}</span><span class="sub s13">${esc(x.on)} · 주고받은 말 ${x.chat.length}개${x.id===S.chatId?' · 지금 대화':''}</span></button><button class="link" data-a="delchat" data-id="${esc(x.id)}" aria-label="${esc(x.title)} 대화 지우기">지우기</button></div>`).join('')+'<p class="tiny mt">이 브라우저에만 남아요(최근 10개). 내 정보를 지우면 함께 지워져요.</p>':'<div class="card"><h3>이전 대화가 없어요</h3><p class="sub">챗봇에게 물어본 대화가 여기에 남아요.</p></div>'}</main>`},
chat:()=>{const bot=inner=>`<div class="m bot"><img class="av" src="/static/quokka.png" alt=""><div><p class="who">청년비서</p>${inner}</div></div>`;
 const msgs=S.chat.map((m,i)=>m.who!=='bot'?`<div class="m user"><div><p class="who r">${esc(S.profile?.name||'나')}</p><div class="bub">${esc(m.t)}</div></div>${ME}</div>`
  :m.pending?bot('<div class="bub"><span class="typing" role="status" aria-label="답변을 쓰고 있어요"><i></i><i></i><i></i></span></div>')
  :bot(`${m.known?`<div class="bub" style="margin-bottom:8px">내 정보(${esc(m.known.join(' · '))})가 저장돼 있어서 다시 묻지 않을게요.</div>`:''}${m.topics?.length?`<div class="bub"><strong>${HOWMANY[m.topics.length]} 가지 지원으로 나눠 찾았어요.</strong>${m.topics.map((t,k)=>`<div class="trow"><div><b>${CIRC[k]} ${esc(t.label)}</b><span class="tiny">정책 ${n(t.total)}건${m.cmp?` · 확인 필요 ${n(t.outcomes.needs_check)}건`:''}</span></div><button class="btn sm" data-a="results" data-i="${i}" data-t="${k}">결과 보기</button></div>`).join('')}</div>`:`<div class="bub">${esc(m.t)}</div>`}${m.compare||m.cnote?`<div class="bub" style="margin-top:8px;white-space:pre-line"><strong>함께 보면</strong>
${esc(m.compare?m.compare.text:m.cnote)}</div>`:''}${m.papers||m.pnote?`<div class="bub" style="margin-top:8px;white-space:pre-line"><strong>준비할 서류</strong>
${esc(m.papers?m.papers.text:m.pnote)}</div>`:''}${m.cta&&!m.topics?.length?`<button class="btn sm" data-a="results" data-i="${i}">결과 보기</button>`:''}${m.suggest?`<button class="btn line sm wrap" data-a="apply" data-i="${i}">내 정보에 반영하고 다시 찾기 · ${esc(chips(m.suggest).join(' · '))}</button>`:''}${m.ask?`<div class="bub" style="margin-top:8px"><strong>${esc(m.ask.text)}</strong></div><div class="opts">${m.ask.options.map(o=>`<button class="btn line" data-a="answer" data-i="${i}" data-v="${esc(o.value)}">${esc(o.label)}</button>`).join('')}<button class="btn line" data-a="skipask" data-i="${i}">잘 모르겠어요</button></div>`:''}${m.tools?`<p class="tiny" style="margin-top:6px">실행한 도구: ${m.tools.filter(t=>t.status==='ok').map(t=>TOOLS[t.tool]+(t.tool==='search_policies'&&m.topics?.length?`(주제 ${m.topics.length}개)`:'')).join(' → ')} · ${m.ai==='used'?'로컬 AI가 검색어를 고르고, 건수와 문장은 코드가 만들었어요.':'AI 없이 정해 둔 낱말로 찾았어요. 건수와 문장은 코드가 만들었어요.'}</p>`:''}${m.steps?`<details class="tiny" style="margin-top:6px"><summary>이번 답을 만든 순서</summary><ol style="margin:6px 0 0;padding-left:18px">${m.steps.map(x=>`<li><b>${WHO[x.who]}${x.who==='orchestrator'?(x.by==='ai'?' (로컬 AI)':' (AI 없이 코드)'):''}</b> ${esc(x.did)}</li>`).join('')}</ol></details>`:''}`)).join('');
 const opts=S.chat.length<=1&&!S.busy?[S.profile?.exams?.[0]?`${S.profile.exams[0].name} 봤는데 응시료 지원돼?`:TOPICS['자격증 응시료'],TOPICS['월세 지원'],'나에게 맞는 정책 찾아줘']:[];
 return bar('챗봇 상담','x','<span class="chat-tools"><button class="new-chat" data-a="history">이전 대화</button><button class="new-chat" data-a="newchat">새 대화</button></span>')+`<main class="pad chat" aria-live="polite">${S.chatOn&&S.chatOn!==today()?`<p class="tiny" style="text-align:center;margin:0 0 12px">${esc(S.chatOn)}에 나눈 대화예요. 건수와 마감은 그날 기준이니 다시 물어봐 주세요.</p>`:''}${msgs}</main>
${opts.length?`<div class="chat-suggestions"><div class="opts one">${opts.map(o=>`<button class="btn line" data-a="say" data-t="${esc(o)}">${esc(o)}</button>`).join('')}</div></div>`:''}
<form class="act chat-input" data-f="chat"><button type="button" class="rb" data-a="attach" aria-label="파일 첨부">${ms('attach_file')}</button><label class="sr" for="m">메시지</label><input id="m" class="round" type="text" maxlength="600" placeholder="청년비서한테 물어보세요" autocomplete="off"><button class="rb fill" aria-label="보내기">${ms('arrow_upward')}</button></form>`;},

results:()=>{const L=S.list,q=S.query,cmp=compared(),tab=S.listTab,myAge=mine().age;
 // 검색칸과 필터는 목록을 다시 불러오는 동안에도 그대로 둔다.
 const filters=`<form class="search" role="search" data-f="find">${ms('search')}<label class="sr" for="find">공고 검색</label><input id="find" maxlength="80" placeholder="공고 이름 · 내용으로 검색" autocomplete="off" enterkeyhint="search" type="search" value="${esc(q.q)}">${q.q?`<button type="button" class="ib" data-a="clearfind" aria-label="검색어 지우기">${ms('close')}</button>`:''}</form>
<div class="kinds" role="group" aria-label="종류">${KINDS.map(([k,l])=>`<button class="chip ${q.kind===k?'on':''}" aria-pressed="${q.kind===k}" data-a="kind" data-k="${esc(k)}">${l}</button>`).join('')}</div>
<div class="frow"><select data-q="sido" aria-label="지역"><option value="">지역 전체</option>${Object.entries(S.names.sido).sort().map(([c,name])=>`<option value="${esc(c)}" ${q.sido===c?'selected':''}>${esc(shortSido(name))}</option>`).join('')}</select><select data-q="ages" aria-label="나이"><option value="">나이 전체</option>${myAge!=null?`<option value="me" ${q.ages==='me'?'selected':''}>내 나이 (${myAge}세)</option>`:''}${AGES.map(([v,l])=>`<option value="${v}" ${q.ages===v?'selected':''}>${l}</option>`).join('')}</select><button class="chip ${q.open?'on':''}" aria-pressed="${!!q.open}" data-a="openonly">마감 제외</button></div>`;
 const T=!tab&&q.topics,allT=T&&q.topic==null;
 if(!L&&!allT)return tab?bar('지원 찾기')+`<main class="pad">${filters}<p class="sub">불러오는 중…</p></main>`+dock('browse'):wait('결과');
 const o=L?L.outcomes:{api_match:0,needs_check:0,api_mismatch:0},all=L?o.api_match+o.needs_check+o.api_mismatch+L.tiers.link_only:0,sel=selIds().length;
 const card=x=>{const link=cmp&&x.tier==='link_only',bad=x.screen?.outcome==='api_mismatch',st=!cmp?null:x.screen?OUT[x.screen.outcome]:['원문 링크만','gray'];
  const line=!cmp?esc(x.category||'분야 확인 필요'):link?x.reasons.map(r=>REASON[r]).join(' · ')+' · 원문에서 확인해 주세요'
   :bad?x.screen.criteria.filter(c=>c.result==='mismatch'&&c.counted!==false).map(c=>CRIT[c.key]).join(', ')+' 조건이 등록 정보와 달라요'
   :`맞아요 ${x.screen.criteria.filter(k=>k.result==='match'&&k.counted!==false).length} · 확인 필요 ${x.screen.to_confirm.length}${x.screen.to_confirm.length?` (${x.screen.to_confirm.map(k=>CRIT[k]).join(', ')})`:''}`+(x.summary?' · '+esc(x.summary):'');
  return `<div class="card ${bad||link?'dim':''}"><div class="rowt"><input type="checkbox" class="cb" data-a="sel" data-id="${esc(x.external_id)}" data-n="${esc(x.name)}" ${S.selected[x.external_id]?'checked':''} aria-label="${esc(x.name)} 함께 준비"><button class="cardbtn" data-a="detail" data-id="${esc(x.external_id)}"><span class="tiny">${esc(x.agency||'기관 확인 필요')}</span><span class="h16">${esc(x.name)}</span><span class="pills">${x.engine?pill('검수 완료','ok')+pill(...ENGINE[x.engine.status]):st?pill(...st):''}${pill(x.period_status==='open'?esc(short(x.period_label)):PERIOD[x.period_status])}${x.same_policy_count>1?pill('같은 정책 '+x.same_policy_count+'건 등록'):''}${x.screen?.criteria.some(c=>c.key==='apply')?pill('신청 방법은 공식 사이트에서'):''}</span><span class="${bad?'red':'sub'} s13">${line}</span>${money(x)&&(bad||link||!x.summary)?`<span class="tiny">${esc(money(x))}</span>`:''}</button></div></div>`};
 const item=x=>{const closed=x.reasons.includes('closed'),st=closed?['마감','gray']:!cmp?null:x.screen?OUT[x.screen.outcome]:['원문 링크만','gray'],where=x.nationwide?'전국':(x.sido_names[0]||x.agency||'지역 확인 필요')+(x.sido_names.length>1?' 외':'');
  return `<button class="feed-card browse-item" data-a="detail" data-id="${esc(x.external_id)}"><span class="tiny">${esc(where)} · ${esc(x.period_label.replace(/\s*\(.*?\)/g,''))}</span><strong>${esc(x.name)}</strong><span class="sub">${esc(x.summary||x.category||'지원 내용은 공고에서 확인')}</span><span class="pills">${x.engine?pill('검수 완료','ok')+pill(...ENGINE[x.engine.status]):st?pill(...st):''}</span></button>`};
   const outs=cmp?`<div class="chips">${[['',`전체 ${n(all)}`],['api_match',`맞아요 ${n(o.api_match)}`],['needs_check',`확인 필요 ${n(o.needs_check)}`],['api_mismatch',`달라요 ${n(o.api_mismatch)}`]].map(([k,l])=>`<button class="chip ${q.outcome===k?'on':''}" data-a="filter" data-k="${k}">${l}</button>`).join('')}</div>`:'';
  const topicLine=q.keywords.length?`<p class="tiny">찾는 주제: ${esc(q.keywords.join(' · '))} · <button class="link" data-a="cleartopic">주제 지우기</button></p>`:'';
  const tabs=T?`<div class="chips">${[['','전체'],...T.map((t,k)=>[k,`${CIRC[k]} ${t.label} ${n(t.total)}`])].map(([k,l])=>`<button class="chip ${String(q.topic??'')===String(k)?'on':''}" data-a="subtopic" data-k="${k}">${esc(l)}</button>`).join('')}</div>`:'';
  const selbar=`<div class="act"><span class="b s14">${sel}개 선택</span><button class="btn f1" data-a="plan" ${sel?'':'disabled'}>신청 계획 만들기</button></div>`;
  // 주제를 둘 이상 물었을 때의 '전체': 주제마다 구역을 나눠 위쪽 정책을 보여 주고, 더 보려면 그 주제의 탭으로 간다
  if(allT)return bar('결과','b')+`<main class="pad"><p class="h18">${HOWMANY[T.length]} 가지 지원으로 나눠 보여 드려요</p>${topicLine}${tabs}${T.map((t,k)=>`<div class="sect"><b>${CIRC[k]} ${esc(t.label)}</b><span class="tiny">${cmp?`확인 필요 ${n(t.outcomes.needs_check)}건`:`정책 ${n(t.total)}건`}</span><i></i></div>${t.items.map(card).join('')||'<div class="card"><p class="sub">찾은 정책이 없어요.</p></div>'}${t.total>t.items.length?`<button class="more-link" data-a="subtopic" data-k="${k}">${esc(t.label.includes('·')?t.label.split(' ')[0]:t.label.split(' ').pop())} 정책 더 보기 <span aria-hidden="true">⌄</span></button>`:''}`).join('')}
<p class="tiny mt">온통청년 정보${S.collected?`(${esc(S.collected)} 수집)`:''}와 비교한 결과이며 자격 판정이 아니에요 · 카드를 누르면 근거를 볼 수 있어요</p></main>${selbar}`;
  return (tab?bar('지원 찾기'):bar('결과','b'))+`<main class="pad">${tab?`${filters}<p class="tiny">${cmp?'내 정보 기준 · ':''}정책 ${n(cmp?all:L.total)}개</p>
${cmp?`<details class="more" data-d="moreBrowse" ${S.moreBrowse?'open':''}><summary>비교 결과별로 보기</summary>${outs}</details>`:''}`
 :`<p class="h18">${T?`${HOWMANY[T.length]} 가지 지원으로 나눠 보여 드려요`:cmp?`${n(all)}개 중 ${n(o.api_match)}개는 온통청년에 등록된 조건과 맞아요`:`${n(L.total)}개의 정책`}</p>
${topicLine}${tabs}
<form class="qform" data-f="q"><label class="sr" for="q">정책 이름으로 좁히기</label><input id="q" class="round" type="search" maxlength="80" value="${esc(q.q)}" placeholder="정책 이름 · 내용으로 좁히기"><button class="rb" aria-label="검색">${ms('search')}</button></form>${outs}`}
${L.items.map(tab?item:card).join('')||(tab?'<div class="card"><h3>찾은 정책이 없어요</h3><p class="sub">검색어나 필터를 바꿔 보세요.</p><button class="btn line w" style="margin-top:12px" data-a="clearfilters">검색 · 필터 지우기</button></div>':'<div class="card"><h3>찾은 정책이 없어요</h3><p class="sub">다른 말로 물어보거나 주제를 지워 보세요.</p></div>')}
${L.page<L.pages?`<button class="btn line w" data-a="more">더 보기 (${n(L.items.length)} / ${n(L.total)})</button>`:''}
<p class="tiny mt">오늘(${esc(L.as_of)}) 기준 · 온통청년 정보${S.collected?`(${esc(S.collected)} 수집)`:''}와 비교한 결과이며 자격 판정이 아니에요 · 카드를 누르면 근거를 볼 수 있어요</p></main>
${tab?(sel?`<div class="act floating"><span class="b s14">${sel}개 선택</span><button class="btn f1" data-a="plan">신청 계획 만들기</button></div>`:'')+dock('browse'):`<div class="act"><span class="b s14">${sel}개 선택</span><button class="btn f1" data-a="plan" ${sel?'':'disabled'}>신청 계획 만들기</button></div>`}`;},

detail:()=>{const d=S.detail;if(!d)return wait('정책 상세');
 const p=d.bundle.public_fields,check=d.bundle.source_check,r=rows(d),out=d.cmp?.screen?.outcome,site=official(d.sources,d.id);
 const field=(title,value,empty)=>`<div class="card"><h3>${title}</h3><p class="pre">${esc(value||empty)}</p></div>`;
 return bar('정책 상세','b')+`<main class="pad"><div><p class="tiny">${esc(p.sprvsnInstCdNm||'기관 확인 필요')}</p><h2 class="h20">${esc(p.plcyNm)}</h2><div class="pills">${out?pill(...OUT[out]):d.cmp?pill('원문 링크만'):''}${pill(esc(short(d.bundle.period_label||PERIOD[d.bundle.period_status])))}</div></div>
${check?`<div class="warnbox" role="status"><strong>${check.api_changed_since_check?'온통청년 정보가 바뀌어 다시 대조해야 해요.':check.official_status==='closed'?'확인한 공식 공고는 접수가 끝났어요.':'공식 안내 대조 기록'}</strong> ${esc(check.summary)} ${esc(check.official_period_text)} · 확인일 ${esc(check.checked_on)}</div>`:''}
${d.bundle.listed===false?`<div class="warnbox" role="status"><strong>온통청년에서 더 이상 보이지 않는 정책이에요.</strong> 마지막으로 수집된 날은 ${esc(String(d.bundle.fetched_at).slice(0,10))}이에요. 종료됐거나 내려갔을 수 있으니 기관에 확인하세요.</div>`:''}
${d.cmp?.engine?`<div class="card"><div class="row"><h3>검수된 규칙으로 본 결과</h3>${pill(...ENGINE[d.cmp.engine.status])}</div><p class="tiny">사람이 공고 원문과 대조해 승인한 규칙이에요. 검수 ${esc(d.cmp.engine.reviewed_by)} · ${esc(d.cmp.engine.reviewed_at)}</p><ul class="list">${d.cmp.engine.findings.map(f=>`<li class="rowbtn"><span class="s13">${esc(f.message)}</span>${pill(...EFFECT[f.effect])}</li>`).join('')}</ul><p class="tiny">최종 선정은 주관기관이 정해요.</p></div>`:''}
<div class="card"><h3>조건 대조</h3>${r.length?`<ul class="list">${r.map((c,i)=>`<li><button class="rowbtn" data-a="sheet" data-i="${i}"><span><span class="b">${CRIT[c.key]}</span><span class="sub s13 blk">지원 조건: ${esc(cond(c.key,d))}</span><span class="s13 blk">내 정보: ${esc(myValue(c.key))}</span></span>${pill(...RES[c.result])}</button></li>`).join('')}</ul><p class="tiny">조건을 누르면 근거가 열려요. 온통청년에 등록된 값과 비교한 결과이고, 전체 조건은 사람 검수 전이에요.</p>`
  :d.cmp?'<p class="sub">마감됐거나 등록된 정보가 부족해 조건을 비교하지 않았어요. 공고 원문에서 확인해 주세요.</p>'
  :`${['period','age','region','income','job'].map(k=>prow(CRIT[k],cond(k,d))).join('')}<p class="tiny" style="margin-top:8px">내 정보를 입력하면 조건을 비교해 드려요.</p>`}</div>
${field('지원 내용',p.plcySprtCn||p.plcyExplnCn,'온통청년 정보에 없어요. 공식 공고를 확인해 주세요.')}
<div class="card"><h3>공식 사이트</h3>${noApply(d)?`<p class="s14" style="margin:0 0 6px"><strong>신청 방법은 공식 사이트에서 확인해 주세요.</strong> 온통청년 정보에 신청 방법과 신청 주소가 등록돼 있지 않아요.</p>`:''}<p class="tiny">${site.notice?'':'온통청년 정보에 열리는 공고 주소가 없어 온통청년의 정책 페이지로 안내해요. '}새 창에서 열려요.</p>${sites(d.sources,d.id)}</div>
<details class="more" data-d="moreDetail" ${S.moreDetail?'open':''}><summary>더 보기 · 신청 방법, 제출서류, AI에게 물어보기</summary>
${d.bundle.supplements.length?`<div class="card"><div class="row"><h3>공식 페이지에서 보완한 정보</h3>${pill('사람 검수 전','warn')}</div><p class="tiny">온통청년 정보에 비어 있던 항목을 공식 페이지에서 찾아 적었어요. 원문 문장과 출처를 함께 보여 드려요.</p>${d.bundle.supplements.map(x=>`<p class="b s14" style="margin:10px 0 2px">${FIELD[x.field]} ${sure(x)?pill('출처에서 문장 확인','ok'):x.read_from==='image'?pill('공고 이미지에서 읽음'):(x.read_from||'').startsWith('attachment')?pill('공고 첨부파일에서 읽음'):pill('자동 대조 안 됨')}</p><p class="pre">${esc(x.value)}</p><p class="quote2">${x.quotes.map(q=>'“'+esc(q)+'”').join('<br>')}</p><a class="link s13" href="${esc(x.source_url)}" target="_blank" rel="noopener noreferrer">${esc(x.source_title)}</a> <span class="tiny">· 확인일 ${esc(x.checked_on)}</span>`).join('')}</div>`:''}
<div class="card"><div class="row"><h3>AI에게 물어보기</h3>${pill('로컬 AI')}</div><p class="tiny">AI가 이 정책 자료와 준비할 일을 조회해 무엇부터 확인할지 골라요. 안내는 검증된 문구로 보여 주고 자격을 확정하지 않아요.</p>${d.ai?.answer?`<p class="pre">${esc(d.ai.answer)}</p><p class="tiny" style="margin-top:6px">실행한 도구: ${d.ai.tools.map(t=>t.tool==='read_policy'?'정책 자료 조회':'준비 작업 조회').join(' → ')} · 저장한 것은 없어요.</p>`:d.ai?.error?`<p class="red s13">${esc(d.ai.error)}</p>`:''}<button class="btn line w" style="margin-top:10px" data-a="askpolicy" ${d.ai?.loading?'disabled':''}>${d.ai?.loading?'AI가 조회하고 있어요…':'무엇부터 확인할까요?'}</button></div>
${p.ptcpPrpTrgtCn?field('참여 제한 안내 ',p.ptcpPrpTrgtCn,''):''}
${field('신청 방법',p.plcyAplyMthdCn,'온통청년 정보에 없어요. 공식 공고를 확인해 주세요.')}
${field('제출서류 안내 ',p.sbmsnDcmntCn,'온통청년 정보에 없어요. 서류가 필요 없다는 뜻이 아니에요.')}
${(s=>s.no_limit||s.count?field('지원 규모 ',s.no_limit?'제한없음':`${s.count.toLocaleString()}명${s.first_come?' · 선착순(마감일 전에 끝날 수 있어요)':''}`,''):'')(d.bundle.structured.scale)}
${d.bundle.structured.selection.text?field('심사 · 발표 ',d.bundle.structured.selection.text,''):''}
</details>
<p class="tiny mt">최종 선정은 심사와 예산에 따라 달라질 수 있어요. 온통청년에서 가져온 정보이며 공고와 다를 수 있어요.</p></main>
<div class="act"><a class="btn line" href="${esc(site.notice?.url||PORTAL(d.id))}" target="_blank" rel="noopener noreferrer">공식 공고</a><button class="btn f1" data-a="prep">이 정책 준비하기</button></div>`;},

plan:()=>{const picked=selIds(),ids=planIds(),P=S.plan,saved=S.space?.tasks||[],tab=S.planTab;
 const head=bar(tab?'내 신청':'신청 계획',tab?null:'b'),foot=tab?dock('plan'):'';
 if(!ids.length&&!saved.length)return head+`<main class="pad"><div class="card"><h3>준비 중인 신청이 없어요</h3><p class="sub">챗봇에게 받고 싶은 지원을 물어보고, 결과에서 정책을 골라 주세요.</p><button class="btn w" style="margin-top:12px" data-a="openchat">챗봇에게 물어보기</button></div></main>`+foot;
 let draft='';
 if(ids.length&&!P)draft='<p class="sub">신청 계획을 만들고 있어요…</p>';
 else if(ids.length){const num=id=>P.order.indexOf(id)+1,by=Object.fromEntries(P.policies.map(x=>[x.external_id,x])),have=P.must.filter(d=>S.docs[d.key]).length,many=P.policies.length>1;
  const extra=S.only&&S.selected[S.only]&&selIds().length>1;
  draft=`${extra?`<p class="tiny" style="margin:0 4px 10px">방금 고른 정책만 보여 드려요. <button class="link" data-a="all" style="background:none;border:0;padding:0;color:inherit;text-decoration:underline;font:inherit;cursor:pointer">고른 정책 ${selIds().length}개 함께 보기</button></p>`:''}${P.conflicts.length?`<div class="warnbox" role="status"><strong>함께 받기 어려울 수 있어요.</strong> 안내 글에 아래 문구가 있어요. 사람 검수 전이니 기관에 확인하세요.${P.conflicts.map(c=>`<br>· ${num(c.from)}번 안내: “${esc(c.quote)}” → ${num(c.to)}번${c.kind==='named'?'의 이름이 보여요':'과 비슷한 사업 제한 문구예요'}`).join('')}</div>`:many?`<div class="warnbox" role="status"><strong>함께 받을 수 있는지 확인이 필요해요.</strong> 안내 글에서 서로 막는 문구는 없었지만, 중복 수혜 제한은 아직 검수하지 않았어요.</div>`:''}
<div class="card"><div class="row"><h3>${many?'통합 서류':'필요한 서류'}</h3><span class="tiny">${P.must.length}종 중 ${have}종 준비</span></div>
${P.documents.length?`<ul class="list">${P.documents.map(d=>{const tag=!many?'':d.policies.length===P.policies.length?'공통':d.policies.map(num).sort().join('·')+'번만';return `<li class="doc"><input type="checkbox" class="cb" data-a="doc" data-k="${esc(d.key)}" ${S.docs[d.key]?'checked':''} aria-label="${esc(d.name)} 보유"><div><div class="pills"><span class="b">${esc(d.name)}</span>${tag?pill(tag):''}${S.docs[d.key]?pill('보유','ok'):d.optional?pill('해당하는 경우만'):pill('부족','bad')}</div><p class="sub s13">${esc(d.kind)} · ${esc(d.how)}</p></div></li>`}).join('')}</ul>`:'<p class="sub">필요한 서류는 공고에서 확인해 주세요.</p>'}
${P.must.some(d=>!S.docs[d.key])?'<p class="tiny" style="margin-top:8px">지금 다 체크하지 못해도 괜찮아요. 고른 정책과 체크한 서류는 임시저장되고, ‘내 신청’에서 이어서 준비할 수 있어요.</p>':''}<details><summary>서류 안내 원문 · 주의할 점</summary>${P.documents_unlisted.length?`<p class="tiny" style="margin-top:8px">${P.documents_unlisted.map(num).sort().map(i=>i+'번').join(', ')} 정책은 서류 안내가 없어요. 서류가 필요 없다는 뜻이 아니에요.</p>`:''}<p class="tiny" style="margin-top:6px">서류 안내 글에서 이름을 찾은 서류예요. 발급일 · 포함 항목 · 대체서류는 공고에서 확인하세요.</p>${P.policies.map(x=>`<p class="b" style="margin:8px 0 0">${num(x.external_id)}. ${esc(x.name)}</p><p class="pre">${({api_other:'(신청 방법·기타 안내 글에서 읽음) ',web_check:'(공식 페이지에서 보완 · 사람 검수 전) ',attachment_pdf:'(공고 첨부파일에서 읽음 · 자동 대조 안 됨 · 사람 검수 전) ',attachment_hwpx:'(공고 첨부파일에서 읽음 · 자동 대조 안 됨 · 사람 검수 전) ',image:'(공고 이미지에서 읽음 · 자동 대조 안 됨 · 사람 검수 전) '})[x.documents_source]||''}${esc(x.documents_text||'정보 없음')}</p>`).join('')}</details></div>
<div class="card"><h3>신청 순서</h3><ol class="ord">${P.order.map(id=>`<li><strong>${esc(by[id].name)}</strong> · ${esc(by[id].period_label)}${picked.length?` <button class="link" data-a="unsel" data-id="${esc(id)}">빼기</button>`:''}${by[id].channels.length||by[id].amounts.length?`<span class="tiny blk">${esc([by[id].channels.length?'신청: '+by[id].channels.join(' · '):'',money(by[id])].filter(Boolean).join(' · '))}</span>`:''}</li>`).join('')}</ol>${est(P)}<details><summary>순서 · 금액 안내</summary><p class="tiny">온통청년에 등록된 날짜 순서예요. 실제 접수 여부와 마감 시각은 공고에서 확인하세요. 예상 지원 금액은 제공 방법이 보조금 · 바우처로 등록된 정책의 글에 적힌 금액을 하나씩 더한 참고 값이에요. 대출 · 보증은 한도라서 더하지 않았고, 실제 금액은 심사와 지원 기간에 따라 달라요.</p></details></div>`;}
 const groups=new Map();for(const t of saved)groups.has(t.external_id)?groups.get(t.external_id).push(t):groups.set(t.external_id,[t]);
 const done=saved.filter(t=>t.status==='done').length;
 const savedHtml=saved.length?`<div class="row" style="margin-top:6px"><h3>저장한 준비 작업</h3><span class="tiny">${saved.length}개 중 ${done}개 완료</span></div>${[...groups].map(([id,list])=>`<div class="card"><div class="row"><h3>${esc(list[0].policy_name)}</h3><button class="link" data-a="detail" data-id="${esc(id)}">정책 보기</button></div><ul class="list">${list.map(t=>`<li class="doc"><input type="checkbox" class="cb" data-a="task" data-id="${esc(t.id)}" ${t.status==='done'?'checked':''} ${t.outdated?'disabled':''} aria-label="${esc(t.title)} 완료"><div><span class="b">${esc(t.title)}</span><p class="sub s13">${esc(t.instructions)}</p>${t.outdated?'<p class="red s13">자료가 바뀌었어요. 정책을 다시 골라 계획을 승인해 주세요.</p>':''}</div></li>`).join('')}</ul></div>`).join('')}`:'';
 // '내 신청' 탭: 승인해 저장한 신청 계획을 정책별 카드로 먼저 보여 준다(저장한 날 · 지금의 접수 상태 · 준비 작업 진행 · 공식 사이트).
 const made=S.space?.plans||[],madeIds=new Set(made.map(x=>x.external_id)),drafting=ids.filter(id=>!madeIds.has(id)).length;
 const tasksOf=list=>`<ul class="list">${list.map(t=>`<li class="doc"><input type="checkbox" class="cb" data-a="task" data-id="${esc(t.id)}" ${t.status==='done'?'checked':''} ${t.outdated?'disabled':''} aria-label="${esc(t.title)} 완료"><div><span class="b">${esc(t.title)}</span><p class="sub s13">${esc(t.instructions)}</p>${t.outdated?'<p class="red s13">자료가 바뀌었어요. 정책을 다시 골라 계획을 승인해 주세요.</p>':''}</div></li>`).join('')}</ul>`;
 // 정책마다 한 줄(이름 · 접수 상태 · 진행)만 보이고, 누르면 준비 작업 체크리스트가 펼쳐진다. 펼친 상태는 다시 그려도 남는다(S['po_'+번호]).
 const madeHtml=`<div class="row" style="margin-top:2px"><h3>내가 세운 신청 계획</h3><span class="tiny">${made.length}건</span></div>${made.length?made.map(x=>`<details class="card plan-card" data-d="po_${esc(x.external_id)}" ${S['po_'+x.external_id]?'open':''}><summary><span class="row"><span class="h16">${esc(x.name)}</span><span class="chev" aria-hidden="true">⌄</span></span><span class="pills">${x.done===x.total?pill('준비 끝','ok'):pill('준비 중')}${pill(x.period_status==='open'?esc(short(x.period_label)):PERIOD[x.period_status],['ended','closed_code','closed_official'].includes(x.period_status)?'gray':'')}${x.outdated?pill('자료 바뀜','bad'):''}</span><span class="sub s13 blk">${esc(x.saved_on)}에 계획 저장 · 준비 작업 ${x.total}개 중 ${x.done}개 완료</span><span class="bar" role="img" aria-label="준비 작업 ${x.total}개 중 ${x.done}개 완료"><i style="width:${Math.round(x.done/x.total*100)}%"></i></span></summary>${tasksOf(groups.get(x.external_id)||[])}${sites(x.links,x.external_id)}<button class="link" style="margin-top:10px" data-a="detail" data-id="${esc(x.external_id)}">정책 조건 다시 보기</button></details>`).join(''):`<div class="card"><h3>아직 세운 신청 계획이 없어요</h3><p class="sub">${picked.length?'아래 임시저장한 계획에서 서류를 모두 체크하고 ‘신청 전 점검’에서 승인하면 여기에 남아요.':'정책을 고르고 ‘신청 전 점검’에서 계획을 승인하면 여기에 남아요.'}</p>${picked.length?'':'<button class="btn w" style="margin-top:12px" data-a="openchat">챗봇에게 물어보기</button>'}</div>`}`;
 // 임시저장: 골라 두었지만 아직 승인하지 않은 정책. 고른 정책과 체크한 서류는 이 브라우저에 이미 남아 있다(youth-desk-selected · youth-desk-docs).
 // 서류를 다 체크하지 못해 '신청 전 점검'으로 넘어가지 못한 계획을 여기서 확인하고 이어서 체크할 수 있다.
 const drafts=picked.filter(id=>!madeIds.has(id));
 const draftHtml=drafts.length?`<div class="row" style="margin-top:20px"><h3>임시저장</h3><span class="tiny">${drafts.length}건 · 승인 전</span></div>${drafts.map(id=>{const docs=P?P.documents.filter(d=>d.policies.includes(id)):null,must=docs?docs.filter(d=>!d.optional):[],have=must.filter(d=>S.docs[d.key]).length;
  return `<details class="card plan-card draft-card" data-d="pd_${esc(id)}" ${S['pd_'+id]?'open':''}><summary><span class="row"><span class="h16">${esc(S.selected[id])}</span><span class="chev" aria-hidden="true">⌄</span></span><span class="pills">${pill('임시저장')}${docs&&must.length?(have===must.length?pill('서류 준비 끝','ok'):pill(`서류 ${must.length-have}종 남음`,'bad')):''}</span><span class="sub s13 blk">${!docs?'서류를 확인하고 있어요…':must.length?`필요한 서류 ${must.length}종 중 ${have}종 준비`:'서류 안내가 없어요. 공고에서 확인해 주세요.'}</span>${docs&&must.length?`<span class="bar" role="img" aria-label="필요한 서류 ${must.length}종 중 ${have}종 준비"><i style="width:${Math.round(have/must.length*100)}%"></i></span>`:''}</summary>${docs?.length?`<ul class="list">${docs.map(d=>`<li class="doc"><input type="checkbox" class="cb" data-a="doc" data-k="${esc(d.key)}" ${S.docs[d.key]?'checked':''} aria-label="${esc(d.name)} 보유"><div><div class="pills"><span class="b">${esc(d.name)}</span>${S.docs[d.key]?pill('보유','ok'):d.optional?pill('해당하는 경우만'):pill('부족','bad')}</div><p class="sub s13">${esc(d.kind)} · ${esc(d.how)}</p></div></li>`).join('')}</ul>`:''}<button class="btn line w" style="margin-top:10px" data-a="plan">신청 계획 이어서 하기</button></details>`}).join('')}<p class="tiny" style="margin:10px 4px 0">고른 정책과 체크한 서류는 이 브라우저에 남아요. 서류를 모두 체크하고 ‘신청 전 점검’에서 승인하면 위의 ‘내가 세운 신청 계획’으로 옮겨져요.</p>`:'';
 if(tab)return head+`<main class="pad">${madeHtml}${draftHtml}</main>`+foot;
 return head+`<main class="pad">${draft}${savedHtml}</main>${picked.length&&P?(left=>`<div class="act ${tab?'floating':''}">${left?`<button class="btn f1" disabled>서류 ${left}종이 남았어요</button>`:`<button class="btn f1" data-a="check">신청 전 점검으로</button>`}</div>`)(P.must.filter(d=>!S.docs[d.key]).length):''}`+foot;},

check:()=>{const P=S.plan;if(!P)return wait('신청 전 점검');
 const by=Object.fromEntries(P.policies.map(x=>[x.external_id,x])),ps=P.order.map(id=>by[id]),nd=P.must,have=nd.filter(d=>S.docs[d.key]).length,left=nd.filter(d=>!S.docs[d.key]).map(d=>d.name);
 const short=x=>x.name.replace(/\s*\(.*?\)\s*/g,' ').trim();
 const message=ps.length>1?`${short(ps[0])} 관련 문의드립니다. ${ps.slice(1).map(short).join(', ')}도 함께 신청하려고 하는데, 함께 받을 수 있는지 확인 부탁드립니다.`
  :`${short(ps[0])} 관련 문의드립니다. 현재 받고 있거나 받았던 다른 청년 지원과 함께 받을 수 있는지, 제출서류와 발급일 기준을 확인 부탁드립니다.`;
 const row=x=>{const c=x.criteria?.filter(k=>k.result!=='skipped'&&k.counted!==false)||[],ok=c.filter(k=>k.result==='match'),bad=c.filter(k=>k.result==='mismatch').length,unk=c.filter(k=>k.result==='unknown').length;
  return `<li class="rowbtn"><span><span class="b">${ps.length>1?P.order.indexOf(x.external_id)+1+'. ':''}${esc(x.name)}</span><span class="sub s13 blk">${x.criteria?`등록된 조건 ${ok.length}개 맞아요${ok.length?' · '+ok.map(k=>CRIT[k.key]).join(', '):''}`:'내 정보가 없어 조건을 비교하지 않았어요'}</span></span>${!x.criteria?pill('비교 안 함'):bad?pill('달라요 '+bad,'bad'):unk?pill('확인 필요 '+unk,'warn'):pill('맞아요','ok')}</li>`};
 return bar('신청 전 점검','b')+`<main class="pad"><div><h2 class="h20">${ps.length>1?`정책 ${ps.length}개 신청 준비`:esc(ps[0].name)}</h2><p class="sub">${ps.map(x=>esc(x.period_label)).join(' · ')} · 기준일 ${esc(P.as_of)}</p></div>
<div class="card"><h3>점검 목록</h3><ul class="list">${ps.map(row).join('')}
<li class="rowbtn"><span><span class="b">서류 ${nd.length}종 중 ${have}종 준비</span><span class="sub s13 blk">${nd.length?left.length?'남은 서류: '+esc(left.join(', ')):'찾은 서류는 모두 준비했어요':'서류는 공고에서 확인해 주세요'}</span></span>${!nd.length?pill('확인 필요','warn'):left.length?pill('남음','bad'):pill('완료','ok')}</li>
<li class="rowbtn"><span><span class="b">중복 수혜 여부</span><span class="sub s13 blk">${P.conflicts.length?`안내 글에 함께 받기 어렵다는 문구가 ${P.conflicts.length}건 있어요. 기관에 문의한 뒤 신청하세요`:'검수 전이라 판단하지 않았어요. 기관에 문의한 뒤 신청하세요'}</span></span>${P.conflicts.length?pill('문구 있음','bad'):pill('확인 필요','warn')}</li></ul>
${left.length?`<button class="btn line w" style="margin:10px 0 6px" data-a="back">서류 체크하러 돌아가기</button>`:''}</div>
<details class="more" data-d="moreCheck" ${S.moreCheck?'open':''}><summary>승인하면 저장되는 확인 목록 보기</summary><div class="card"><h3>공고에서 확인할 일</h3><p class="tiny">승인하면 아래 일이 내 신청에 저장돼요.</p>${ps.map(x=>`<p class="b s14" style="margin:10px 0 2px">${esc(x.name)}</p><ul class="pre" style="padding-left:18px;margin:0">${x.tasks.map(t=>`<li>${esc(t.title)}</li>`).join('')}</ul>`).join('')}</div></details>
<div class="card"><h3>공식 사이트</h3><p class="tiny">신청 전에 공고를 한 번 더 확인하세요. 새 창에서 열려요.</p>${ps.map(x=>`${ps.length>1?`<p class="b s14" style="margin:10px 0 0">${esc(x.name)}</p>`:''}${sites(x.links,x.external_id)}`).join('')}</div>
<div class="card"><h3>문의 문구</h3><p class="quote2" id="msg">${esc(message)}</p><div class="row" style="justify-content:flex-start;gap:10px"><button class="btn line" data-a="copy">문구 복사</button><span class="tiny">${esc(ps[0].agency||'담당 기관은 공고에서 확인')}</span></div></div>
<p class="tiny mt">등록 정보를 정리한 안내예요. 제출 전에 공식 공고를 한 번 더 확인하세요.</p></main>
<div class="act">${(s=>`<a class="btn line" href="${esc((s.apply||s.notice)?.url||PORTAL(ps[0].external_id))}" target="_blank" rel="noopener noreferrer">${s.apply?'공식 신청 페이지로 이동':'공식 공고로 이동'}</a>`)(official(ps[0].links,ps[0].external_id))}<button class="btn f1" data-a="approve">승인하고 저장</button></div>`;},

profile:()=>{const d=S.draft||(S.draft={name:'',sido:'',job_code:'',school_code:'',...(S.profile||{})});
 if(d.job_pick===undefined)d.job_pick=d.job_code||((d.groups||[]).includes('대학(원)생')?'student':'');
 const sel=(k,label,list,none='선택 안 함')=>`<select data-k="${k}" aria-label="${label}"><option value="">${none}</option>${list.map(([v,t])=>`<option value="${esc(v)}" ${String(d[k]??'')===String(v)?'selected':''}>${esc(t)}</option>`).join('')}</select>`;
 const ko=(a,b)=>a[1].localeCompare(b[1],'ko'),age=d.birth?ageOf(d.birth):d.age===''||d.age==null?null:+d.age,place=area(d);
 // 취업 상태는 팀 화면의 세 가지를 앞에 두고, 코드표의 나머지를 뒤에 붙인다. '학생'은 대상 집단(대학(원)생)으로 저장한다.
 const jobs=[['0013003','취업 준비 중'],['0013001','재직 중'],['student','학생'],...Object.entries(S.names.job_code).filter(([c])=>!['0013003','0013001'].includes(c))];
 const month=(k,label,value)=>`<div class="prow"><label class="sub" for="${k}" style="margin:0;font-weight:400">${label}</label><span class="b"><input id="${k}" class="mon" data-k="${k}" type="month" min="1930-01" max="2099-12" value="${esc(value||'')}"></span></div>`;
 return bar('내 정보',S.profile?null:'b')+`<main class="pad"><div class="card"><div class="row" style="justify-content:flex-start;gap:14px"><span class="avl">${ME}</span><div class="f1"><p class="h20" style="margin:0">${esc(d.name||'체험 사용자')}</p><p class="tiny">챗봇 대화에 이 사진과 이름이 보여요</p></div>${pill(d.name==='민지'?'데모 계정':'체험')}</div></div>
<div class="card"><h3>기본 정보</h3><p class="tiny">나이와 거주 조건을 확인하는 데 써요</p>
<div class="prow"><label class="sub" for="birth" style="margin:0;font-weight:400">출생 연월</label><span class="b"><input id="birth" class="mon" data-k="birth" type="month" min="1930-01" max="2099-12" value="${esc(d.birth||'')}">${age!=null?` · ${age}세`:''}</span></div>
<div class="addr"><label for="sido">주소</label><div class="pair">${sel('sido','거주 시도',Object.entries(S.names.sido).sort(ko),'시 · 도').replace('<select ','<select id="sido" ')}${sel('region_code','시군구',Object.entries(S.names.sigungu).filter(([c])=>c.startsWith(d.sido||'-')).sort(ko),'시 · 군 · 구')}</div><p class="tiny">지원 조건 확인에는 <strong>${esc(place||'시 · 군 · 구')}</strong>까지만 써요</p></div>
${month('moved','전입한 달',d.moved)}</div>
<div class="card"><h3>일 · 학업</h3><p class="tiny">미취업 · 재직 · 재학 조건을 확인해요</p><div class="prow"><span class="sub">취업 상태</span>${sel('job_pick','취업 상태',jobs)}</div><div class="prow"><span class="sub">최종 학력</span>${sel('school_code','최종 학력',Object.entries(S.names.school_code))}</div></div>
<div class="card"><h3>사업 · 창업</h3><p class="tiny">창업 지원과, 사업자등록이 있으면 달라지는 조건을 확인해요</p><div class="prow"><span class="sub">사업자등록</span>${sel('business','사업자등록',[['yes','있음'],['no','없음']])}</div>
${d.business==='yes'?month('biz_opened','개업한 달',d.biz_opened)+`<div class="prow"><label class="sub" for="biz_type" style="margin:0;font-weight:400">업종</label><input id="biz_type" class="num" style="width:160px" data-k="biz_type" type="text" maxlength="20" value="${esc(d.biz_type||'')}" placeholder="예: 카페"></div>`:''}</div>
<div class="card"><h3>소득 · 가구</h3><p class="tiny">금액 대신 구간으로만 받아요</p><div class="prow"><span class="sub">소득 구간</span>${sel('income_band','소득 구간',[[60,'중위소득 60% 이하'],[100,'중위소득 100% 이하'],[150,'중위소득 150% 이하'],[999,'그 이상']])}</div><div class="prow"><span class="sub">가구원 수</span>${sel('household','가구원 수',[[1,'1명'],[2,'2명'],[3,'3명'],[4,'4명'],[5,'5명 이상']])}</div></div>
<div class="card"><h3>주거</h3><p class="tiny">월세 · 전세 지원을 찾을 때 참고해요</p><div class="prow"><span class="sub">주거 형태</span>${sel('housing','주거 형태',['월세','전세','자가','가족과 거주'].map(x=>[x,x]))}</div></div>
<div class="card"><h3>자격증 · 시험</h3><p class="tiny">응시료 지원을 물어볼 때 써요</p>${(d.exams||[]).map((x,i)=>`<div class="prow"><span><span class="b blk">${esc(x.name)}</span><span class="sub s13">${x.month?esc(ym(x.month))+' 응시':'응시한 달 미입력'}</span></span><button class="ib" data-a="delexam" data-i="${i}" aria-label="${esc(x.name)} 삭제">${ms('close')}</button></div>`).join('')}
${d._exam?`<div class="addf"><label for="exam_name">자격증 · 시험 이름</label><input id="exam_name" data-k="exam_name" type="text" maxlength="30" value="${esc(d.exam_name||'')}" placeholder="예: 정보처리기사"><label for="exam_month">응시한 달</label><input id="exam_month" data-k="exam_month" type="month" value="${esc(d.exam_month||'')}"><div class="row"><button class="btn line" data-a="addexam">추가</button></div></div>`:`<button class="link add" data-a="openexam">${ms('add')}자격증 · 시험 추가</button>`}</div>
<div class="card"><h3>받은 지원 이력</h3><p class="tiny">함께 받을 수 없는 지원인지 확인해요</p>${(d.benefits||[]).length?d.benefits.map(b=>`<div class="prow"><span class="b">${esc(b)}</span><button class="ib" data-a="delbenefit" data-v="${esc(b)}" aria-label="${esc(b)} 삭제">${ms('close')}</button></div>`).join(''):'<p class="sub prow">아직 등록한 이력이 없어요</p>'}
${d._ben?`<ul class="list">${S.benefits.map(b=>`<li class="doc"><input type="checkbox" class="cb" data-a="benefit" data-v="${esc(b)}" id="b-${esc(b)}" ${(d.benefits||[]).includes(b)?'checked':''}><label for="b-${esc(b)}" style="margin:0;font-weight:500">${esc(b)}</label></li>`).join('')}</ul>`:`<button class="link add" data-a="openben">${ms('add')}받은 지원 추가</button>`}</div>
<details class="more" data-d="moreProfile" ${S.moreProfile?'open':''}><summary>더 자세히 입력 (선택)</summary>
<div class="card"><h3>소득을 금액으로</h3><p class="tiny">금액을 넣으면 구간 대신 금액으로 비교해요. 학자금 지원구간은 한국장학재단에서 확인할 수 있어요.</p><div class="prow"><label class="sub" for="pay" style="margin:0;font-weight:400">월 소득(만원)</label><input id="pay" class="num" data-k="income_monthly" type="number" min="0" max="10000" inputmode="numeric" value="${esc(d.income_monthly??'')}" placeholder="예: 180"></div><div class="prow"><span class="sub">학자금 지원구간(소득분위)</span>${sel('income_bracket','학자금 지원구간',[[0,'기초·차상위'],...[1,2,3,4,5,6,7,8,9,10].map(i=>[i,i+'구간'])],'모름 · 선택 안 함')}</div></div>
<div class="card"><h3>해당하는 것</h3><p class="tiny">이름에 특정 대상이 적힌 정책(예: 대학생, 예술인)과 비교해요. 고르지 않으면 그런 정책은 ‘확인 필요’로 나와요.</p><ul class="list">${S.groups.map(g=>`<li class="doc"><input type="checkbox" class="cb" data-a="group" data-v="${esc(g)}" id="g-${esc(g)}" ${(d.groups||[]).includes(g)?'checked':''}><label for="g-${esc(g)}" style="margin:0;font-weight:500">${esc(g)}</label></li>`).join('')}</ul></div></details>
<p class="tiny">저장하면 찾아둔 지원 결과를 바뀐 정보로 다시 계산해요. 입력값은 이 브라우저에만 저장해요. 실제 개인정보를 입력하지 마세요.</p>
<button class="btn w" data-a="save">${S.profile?'저장하기':'저장하고 시작하기'}</button>${S.profile?'<button class="btn line w" data-a="logout">로그아웃</button>':''}</main>`+(S.profile?dock('profile'):'');}
};

function sheet(){if(S.sheet===null||S.screen!=='detail'||!S.detail)return'';const d=S.detail,c=rows(d)[S.sheet],link={url:official(d.sources,d.id).notice?.url||PORTAL(d.id)};
 // 이 조건에 쓰인 공식 페이지 기록(출처에서 문장이 확인된 것). 있으면 확인일과 출처를 함께 보여 준다.
 const note=d.bundle.supplements.find(x=>sure(x)&&(c.key==='period'?x.field==='period':c.key==='age'?(x.rules||[]).length:c.key==='income'&&x.field==='conditions'&&x.quotes.some(q=>q.includes('소득'))));
 return `<div class="scrim" data-a="closesheet"></div><section class="sheet" role="dialog" aria-label="근거 보기"><span class="grab"></span><div class="row"><h3 class="h18">근거 · ${CRIT[c.key]}</h3>${pill(...RES[c.result])}</div><blockquote>${esc(c.basis)}</blockquote>${prow('지원 조건',cond(c.key,d))}${c.where?prow('위치',c.where):''}${prow('내 정보',myValue(c.key))}${prow('정보 수집일',String(d.bundle.fetched_at).slice(0,10))}${note?prow('공식 페이지 확인일',note.checked_on)+`<p class="tiny">출처: <a class="link" href="${esc(note.source_url)}" target="_blank" rel="noopener noreferrer">${esc(note.source_title)}</a> · 사람 검수 전</p>`:''}<p class="tiny">온통청년에 등록된 값이에요. 공고 원문과 다를 수 있어 신청 전에 확인이 필요해요.</p><div class="row" style="gap:10px">${link?`<a class="btn line f1" href="${esc(link.url)}" target="_blank" rel="noopener noreferrer">공고 원문 보기</a>`:''}<button class="btn f1" data-a="closesheet">확인</button></div></section>`;}

// ── 데이터 불러오기 ──
async function refreshSpace(){S.space=await api(space())}
async function loadCounts(){const first=tasks()[0],ids=selIds().length?selIds():savedIds();
 // 홈의 서류 진행 표시: 고른 정책(없으면 저장한 정책)의 서류 목록
 if(ids.length&&S.space)api(space('/plan'),'POST',{external_ids:ids,profile:mine()}).then(r=>{r.must=r.documents.filter(d=>!d.optional);S.homePlan=r;if(S.screen==='home')render()},()=>{});else S.homePlan=null;
 if(first&&S.next?.external_id!==first.external_id)api('/api/integrations/ontong/screen','POST',{profile:{},q:first.external_id,page_size:1}).then(r=>{S.next=r.items[0]||null;if(S.screen==='home')render()},()=>{});
 if(!compared()){S.counts=null;return}S.counts=await api('/api/integrations/ontong/screen','POST',{profile:mine(),page_size:1});if(S.screen==='home')render()}
async function loadList(page=1){const q=S.query;if(page===1){S.list=null;if(S.screen==='results')render(true)}
 const word=q.kind?.startsWith('k:'),age=mine().age;
 const r=await api('/api/integrations/ontong/screen','POST',{profile:mine(),q:q.q,keywords:word?q.kind.slice(2).split(','):q.topics&&q.topic!=null?q.topics[q.topic].keywords:q.keywords,category:q.kind&&!word?q.kind:'',sido:q.sido||'',
  ages:q.ages==='me'?(age==null?'':`${age}-${age}`):q.ages||'',open_only:!!q.open,outcome:compared()?q.outcome:'',page,page_size:10});
 S.list={...r,items:page===1?r.items:S.list.items.concat(r.items)};if(S.screen==='results')render(page===1)}
function showResults(keywords=[],tab=false,topics=null,topic=null){S.listTab=tab;S.query={keywords,...NOFILTER,topics:topics?.length?topics:null,topic};if(tab){S.back=[];S.screen='results';S.sheet=null;render(true)}else go('results');
 if(S.query.topics&&topic==null){S.list=null;render(true);return Promise.resolve()}   // '전체'는 주제별 위쪽 정책만 보여 주므로 목록을 따로 부르지 않는다
 return loadList()}
async function openDetail(id){S.detail=null;S.detailId=id;go('detail');const path='/api/integrations/ontong/candidates/'+encodeURIComponent(id);
 const [bundle,preview,cmp]=await Promise.all([api(path),api(space('/policies/'+encodeURIComponent(id)+'/preview')),compared()?api(path+'/screen','POST',mine()):null]);
 if(S.detailId!==id)return;S.detail={id,bundle,cmp,sources:preview.tasks[0]?.sources||[]};if(S.screen==='detail')render(true)}
async function loadPlan(){S.plan=null;const ids=planIds();if(!ids.length)return;
 const r=await api(space('/plan'),'POST',{external_ids:ids,profile:mine()});
 if(ids.join()!==planIds().join())return;r.must=r.documents.filter(d=>!d.optional);S.plan=r;if(S.screen==='plan'||S.screen==='check')render()}
function select(id,name,on){if(on)S.selected[id]=name;else delete S.selected[id];store.set('youth-desk-selected',S.selected);S.plan=null;S.homePlan=null}
function showPlan(tab,only){S.only=only||null;S.planTab=tab;if(tab){S.back=[];S.screen='plan';S.sheet=null;render(true)}else go('plan');return (tab?refreshSpace().then(()=>{if(S.screen==='plan')render()}):Promise.resolve()).then(loadPlan)}
function openChat(first){if(!S.chat.length)S.chat.push({who:'bot',t:`안녕하세요${S.profile?.name?', '+S.profile.name+' 님':''}. 무엇을 받고 싶으세요?`});if(S.screen!=='chat')go('chat');if(first)say(first)}
// 이전 대화: 이 브라우저에만 남긴다(최근 10개, 가상 프로필로 나눈 대화). 서버에는 보내지 않고, 내 정보를 지우면 함께 지운다.
const CHATS='youth-desk-chats';
function keepChat(){const first=S.chat.find(m=>m.who==='user');if(!first)return;S.chatId=S.chatId||Date.now().toString(36);S.chatOn=today();
 const list=[{id:S.chatId,on:S.chatOn,title:first.t.slice(0,40),chat:S.chat.filter(m=>!m.pending),skip:S.skip||[]},...store.get(CHATS,[]).filter(x=>x.id!==S.chatId)].slice(0,10);
 while(list.length){try{localStorage.setItem(CHATS,JSON.stringify(list));return}catch{list.pop()}}}   // 자리가 모자라면 오래된 대화부터 뺀다
async function say(text,quiet){if(S.busy||!text)return;
 // 나이를 물은 직후 숫자만 답하면 내 정보에 넣고 같은 질문으로 다시 찾는다.
 const last=S.chat[S.chat.length-1],age=/^(\d{1,3})\s*(살|세)?$/.exec(text);
 if(last?.ask?.key==='age'&&age&&+age[1]<=120){saveProfile({...(S.profile||{}),age:+age[1]});last.ask=null;S.chat.push({who:'user',t:text});text=last.asked;quiet=true}
 else if(last?.ask)last.ask=null;
 if(!quiet)S.chat.push({who:'user',t:text});S.chat.push({who:'bot',pending:true,t:''});render();
 try{const r=await api('/api/integrations/ontong/ask','POST',{message:text,profile:mine(),skip:S.skip||[],selected:Object.keys(S.selected||{}).slice(0,5)});
  // 이 대화에서 처음 답할 때만, 비교에 쓰는 저장값(지역 · 나이 · 취업 상태 · 시험)을 알려 준다.
  const p=mine(),known=S.chat.some(m=>m.known)?[]:[area(p),p.age!=null?p.age+'세':'',S.names.job_code[p.job_code],...(p.exams||[])].filter(Boolean);
  S.chat[S.chat.length-1]={who:'bot',known:known.length?known:null,t:r.answer,cta:r.total>0,keywords:r.keywords,suggest:Object.keys(r.profile_suggestion).length?r.profile_suggestion:null,ask:r.question,tools:r.tools,ai:r.ai,asked:text,steps:r.steps,compare:r.compare,cnote:r.compare_note,papers:r.documents,pnote:r.documents_note,topics:r.topics,cmp:r.compared};
 }catch(e){S.chat[S.chat.length-1]={who:'bot',t:e.message}}
 keepChat();
 S.busy=false;if(S.screen==='chat')render()}
function saveProfile(next){S.profile=next;store.set('youth-desk-profile',next);S.draft=null;S.counts=null;S.list=null;S.plan=null}
async function approve(){const P=S.plan;
 try{for(const x of P.policies)S.space=await api(space('/policies/'+encodeURIComponent(x.external_id)+'/confirm'),'POST',{approved:true,preview_token:x.preview_token})}
 catch(e){if(e.status===409){await loadPlan()}throw e}
 S.selected={};store.set('youth-desk-selected',{});S.plan=null;S.planTab=true;S.back=[];S.screen='plan';render(true);toast('확인할 일을 내 신청에 저장했어요.')}

document.addEventListener('click',e=>{const el=e.target.closest('[data-a]');if(!el||el.tagName==='INPUT')return;const a=el.dataset.a,d=el.dataset;
 if(a==='back')back();
 else if(a==='demo'){saveProfile(DEMO);go('home',true);run(loadCounts)}
 else if(a==='start')go('profile');
 else if(a==='tab'){S.draft=null;if(d.s==='plan')run(()=>showPlan(true));else if(d.s==='browse')run(()=>showResults([],true));else{S.back=[];S.screen=d.s;S.sheet=null;render(true);if(d.s==='home')run(async()=>{if(!S.counts||!S.homePlan)await loadCounts()})}}
 else if(a==='openchat')openChat();else if(a==='topic')openChat(TOPICS[d.t]);else if(a==='say')say(d.t);
 else if(a==='results')run(()=>showResults(S.chat[d.i].keywords,false,S.chat[d.i].topics,d.t!=null?+d.t:null));else if(a==='browse')run(()=>showResults([],true));
 else if(a==='newchat'){if(!S.busy){S.chat=[];S.skip=[];S.chatId=null;S.chatOn=null;openChat();render(true)}}
 else if(a==='history'){if(!S.busy)go('chats')}
 else if(a==='oldchat'){const x=store.get(CHATS,[]).find(c=>c.id===d.id);if(x){S.chat=x.chat;S.chatId=x.id;S.skip=x.skip||[];S.chatOn=x.on;back()}}
 else if(a==='delchat'){store.set(CHATS,store.get(CHATS,[]).filter(c=>c.id!==d.id));if(S.chatId===d.id)S.chatId=null;render()}else if(a==='attach')toast('체험판에서는 파일을 첨부할 수 없어요');else if(a==='notice')toast('새로운 알림이 없어요');
 else if(a==='apply'){const m=S.chat[d.i];saveProfile({...(S.profile||{}),...m.suggest});m.suggest=null;m.ask=null;say(m.asked,true)}
 else if(a==='skipask'){const m=S.chat[d.i];S.skip=[...(S.skip||[]),m.ask.key];S.chat.push({who:'user',t:'잘 모르겠어요'});m.ask=null;say(m.asked,true)}
 else if(a==='answer'){const m=S.chat[d.i];saveProfile({...(S.profile||{}),[m.ask.key]:m.ask.key==='benefits'?(d.v?[d.v]:[]):d.v});S.chat.push({who:'user',t:el.textContent});m.ask=null;say(m.asked,true)}
 else if(a==='filter'){S.query.outcome=d.k;run(()=>loadList())}else if(a==='more')run(()=>loadList(S.list.page+1));
 else if(a==='cleartopic'){S.query.keywords=[];S.query.topics=null;S.query.topic=null;run(()=>loadList())}
 else if(a==='subtopic'){S.query.topic=d.k===''?null:+d.k;S.query.outcome='';S.query.q='';if(S.query.topic==null){S.list=null;render(true)}else run(()=>loadList())}
 else if(a==='kind'){S.query.kind=d.k;run(()=>loadList())}else if(a==='openonly'){S.query.open=!S.query.open;run(()=>loadList())}
 else if(a==='clearfind'){S.query.q='';run(()=>loadList())}else if(a==='clearfilters'){S.query={keywords:[],...NOFILTER};run(()=>loadList())}
 else if(a==='detail')run(()=>openDetail(d.id));else if(a==='sheet'){S.sheet=+d.i;render()}else if(a==='closesheet'){S.sheet=null;render()}
 else if(a==='askpolicy'){const d0=S.detail;d0.ai={loading:true};render();run(async()=>{try{const r=await api(space('/assistant'),'POST',{external_id:d0.id,message:'이 정책은 무엇부터 확인해야 해?'});d0.ai={answer:r.answer,tools:r.tools}}catch(e){d0.ai={error:e.message}}if(S.detail===d0&&S.screen==='detail')render()})}
 else if(a==='prep'){if(!S.selected[S.detail.id]&&selIds().length>=5){toast('한 번에 5개까지 함께 준비할 수 있어요.');return}select(S.detail.id,S.detail.bundle.public_fields.plcyNm,true);run(()=>showPlan(false,S.detail.id))}
 // 전에 고른 정책이 남아 있을 때: 방금 '이 정책 준비하기'를 누른 정책만 남긴다
 else if(a==='all'){S.only=null;S.plan=null;render();run(loadPlan)}
 else if(a==='plan')run(()=>showPlan(false));else if(a==='check'){go('check');if(!S.plan)run(loadPlan)}
 else if(a==='unsel'){select(d.id,'',false);if(!selIds().length&&!S.planTab&&!(S.space?.tasks||[]).length)back();else{render();run(loadPlan)}}
 else if(a==='copy'){const text=$('#msg').textContent;navigator.clipboard?.writeText(text).then(()=>toast('문구를 복사했어요'),()=>toast('복사하지 못했어요. 길게 눌러 복사해 주세요'))??toast('복사하지 못했어요. 길게 눌러 복사해 주세요')}
 else if(a==='approve')run(approve);
 else if(a==='save'){const f=S.draft,pay=String(f.income_monthly??'').trim(),money=pay===''?null:Number(pay),num=v=>v==null||v===''?null:Number(v);
  if(money!==null&&(!Number.isInteger(money)||money<0||money>10000)){toast('월 소득은 0~10000 사이의 만원 단위 숫자로 입력해 주세요.');return}
  if(f.birth&&(ageOf(f.birth)==null||ageOf(f.birth)>120)){toast('출생 연월을 확인해 주세요.');return}
  if(f.moved&&monthsSince(f.moved)<0){toast('전입한 달을 확인해 주세요.');return}
  const student=f.job_pick==='student',groups=new Set(f.groups||[]);if(student)groups.add('대학(원)생');
  const first=!S.profile;saveProfile({name:f.name||'',birth:f.birth||'',age:f.birth?ageOf(f.birth):num(f.age),moved:f.moved||'',residence_months:f.moved?null:num(f.residence_months),sido:f.sido,region_code:f.region_code||'',
   job_code:student?'':f.job_pick||'',school_code:f.school_code,income_band:num(f.income_band),income_monthly:money,household:num(f.household),income_bracket:num(f.income_bracket),housing:f.housing||'',exams:f.exams||[],business:f.business||'',biz_opened:f.business==='yes'?f.biz_opened||'':'',biz_type:f.business==='yes'?(f.biz_type||'').trim():'',
   benefits:f.benefits??null,groups:f.groups||student?[...groups]:null});
  if(first){S.back=[];go('home',true)}else render();run(loadCounts);toast(compared()?'저장했어요. 내 정보 기준으로 다시 찾아요.':'저장했어요. 정보 없이 전체 정책을 보여드려요.')}
 else if(a==='openexam'){S.draft._exam=true;render()}else if(a==='openben'){S.draft._ben=true;render()}
 else if(a==='addexam'){const f=S.draft,name=(f.exam_name||'').trim();if(!name){toast('자격증이나 시험 이름을 적어 주세요.');return}f.exams=[...(f.exams||[]),{name,month:f.exam_month||''}].slice(0,5);f.exam_name='';f.exam_month='';f._exam=false;render()}
 else if(a==='delexam'){S.draft.exams=(S.draft.exams||[]).filter((_,i)=>i!==+d.i);render()}
 else if(a==='delbenefit'){S.draft.benefits=(S.draft.benefits||[]).filter(x=>x!==d.v);render()}
 else if(a==='logout'){localStorage.removeItem('youth-desk-profile');localStorage.removeItem(CHATS);S.chatId=null;S.chatOn=null;S.profile=null;S.draft=null;S.counts=null;S.list=null;S.chat=[];S.back=[];S.screen='login';render(true);toast('내 정보를 지웠어요.')}
});
document.addEventListener('change',e=>{const t=e.target,d=t.dataset;
 if(d.q){S.query[d.q]=t.value;run(()=>loadList());return}
 if(d.a==='sel'){if(t.checked&&selIds().length>=5){t.checked=false;toast('한 번에 5개까지 함께 준비할 수 있어요.');return}select(d.id,d.n,t.checked);render()}
 else if(d.a==='doc'){S.docs[d.k]=t.checked;store.set('youth-desk-docs',S.docs);render()}
 else if(d.a==='group'&&S.draft){const now=new Set(S.draft.groups||[]);t.checked?now.add(d.v):now.delete(d.v);S.draft.groups=[...now]}
 else if(d.a==='benefit'&&S.draft){const now=new Set(S.draft.benefits||[]);t.checked?now.add(d.v):now.delete(d.v);S.draft.benefits=[...now];render()}
 else if(d.a==='task')run(async()=>{try{await api(space('/tasks/'+encodeURIComponent(d.id)),'PATCH',{status:t.checked?'done':'todo'});await refreshSpace();render()}catch(error){t.checked=!t.checked;throw error}});
 else if(d.k&&S.draft){S.draft[d.k]=t.value;if(d.k==='sido'){S.draft.region_code='';render()}else if(d.k==='birth'||d.k==='region_code'||d.k==='business')render()}});
document.addEventListener('input',e=>{const t=e.target;if(t.dataset.k&&S.draft)S.draft[t.dataset.k]=t.value});
// 접어 둔 부분은 다시 그려도 펼친 상태를 기억한다.
document.addEventListener('toggle',e=>{const k=e.target.dataset?.d;if(k)S[k]=e.target.open},true);
document.addEventListener('submit',e=>{e.preventDefault();const f=e.target.dataset.f;
 if(f==='chat'){const input=$('#m'),text=input.value.trim();input.value='';say(text)}
 else if(f==='q'||f==='find'){S.query.q=$(f==='q'?'#q':'#find').value.trim();run(()=>loadList())}});

// 글꼴은 화면을 막지 않게 스크립트로 불러온다(인라인 핸들러를 쓰지 않아 CSP를 지킨다). 인터넷이 없으면 기기 글꼴로 보인다.
document.head.append(Object.assign(document.createElement('link'),{rel:'stylesheet',href:'https://fonts.googleapis.com/css2?family=Noto+Sans+KR:wght@400;500;700;800&display=swap'}));
// 화면을 켜 둔 채 날짜가 바뀌면(자정을 넘기거나 다음 날 다시 열면) D-day와 접수 상태가 어제 것이므로 다시 불러온다.
let loadedOn=today();
const freshen=()=>{if(document.visibilityState==='visible'&&today()!==loadedOn)location.reload()};
document.addEventListener('visibilitychange',freshen);setInterval(freshen,60000);
(async function init(){render();
 try{let wid=localStorage.getItem('youth-desk-workspace');
  if(wid){try{S.space=await api('/api/desk/workspaces/'+encodeURIComponent(wid))}catch(e){if(e.status!==404)throw e;wid=null}}
  if(!wid){const created=await api('/api/desk/workspaces','POST');localStorage.setItem('youth-desk-workspace',created.id);S.space=await api('/api/desk/workspaces/'+encodeURIComponent(created.id))}
  const [codebook,regions]=await Promise.all([api('/api/integrations/ontong/codebook'),api('/api/integrations/ontong/regions')]);S.names.sido=regions.sido;S.names.sigungu=regions.sigungu;
  // '제한없음'은 정책 쪽 표기라 내 상태로 고를 수 없다.
  for(const [key,field,skip] of [['job_code','jobCd','0013010'],['school_code','schoolCd','0049010']])S.names[key]=Object.fromEntries(Object.entries(codebook.groups[field].codes).filter(([code])=>code!==skip).map(([code,item])=>[code,item.label]));
  S.benefits=regions.benefits;S.groups=regions.groups;
  api('/api/integrations/ontong').then(r=>{S.collected=(r.last_run?.finished_at||'').slice(0,10)},()=>{});
  if(S.profile){S.screen='home';render();await loadCounts()}else render();
 }catch(e){toast(e.message+' 새로고침해 주세요.')}
})();
