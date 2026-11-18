from pathlib import Path
import html
import re
import urllib.parse

ROOT = Path(__file__).resolve().parent
SOURCE = ROOT / '청년비서_수상전략_및_실행계획.md'
OUTPUT = ROOT / '청년비서_수상전략_및_실행계획.html'
source = SOURCE.read_text(encoding='utf-8')


def inline(value):
    tokens = []

    def token(markup):
        tokens.append(markup)
        return f'\x00{len(tokens)-1}\x00'

    value = re.sub(r'`([^`]+)`', lambda m: token('<code>' + html.escape(m[1]) + '</code>'), value)
    value = re.sub(r'\[([^\]]+)\]\((https?://[^\s]+?)\)', lambda m: token(
        '<a class="source-link" href="' + html.escape(m[2], quote=True) + '" target="_blank" rel="noopener noreferrer">' + html.escape(m[1]) + '<span aria-hidden="true"> ↗</span></a>'), value)
    value = html.escape(value)
    value = re.sub(r'\*\*(.+?)\*\*', r'<strong>\1</strong>', value)
    return re.sub(r'\x00(\d+)\x00', lambda m: tokens[int(m[1])], value)


def render(markdown):
    lines = markdown.strip().splitlines()
    result = []
    i = 0
    while i < len(lines):
        line = lines[i].strip()
        if not line:
            i += 1
            continue
        if line.startswith('```'):
            language = line[3:].strip()
            code = []
            i += 1
            while i < len(lines) and not lines[i].strip().startswith('```'):
                code.append(lines[i])
                i += 1
            result.append('<div class="code-block"><span class="code-label">' + html.escape(language or 'FLOW / STRUCTURE') + '</span><pre><code>' + html.escape('\n'.join(code)) + '</code></pre></div>')
            i += 1
            continue
        if line.startswith('|'):
            rows = []
            while i < len(lines) and lines[i].strip().startswith('|'):
                row = lines[i].strip().strip('|').split('|')
                if not all(re.fullmatch(r'\s*:?-+:?\s*', cell) for cell in row):
                    rows.append(row)
                i += 1
            head = '<thead><tr>' + ''.join('<th scope="col">' + inline(cell.strip()) + '</th>' for cell in rows[0]) + '</tr></thead>'
            body = '<tbody>' + ''.join('<tr>' + ''.join('<td>' + inline(cell.strip()) + '</td>' for cell in row) + '</tr>' for row in rows[1:]) + '</tbody>'
            result.append('<div class="table-scroll" role="region" tabindex="0" aria-label="표, 작은 화면에서는 가로로 스크롤">' + '<table>' + head + body + '</table></div>')
            continue
        if re.match(r'^(- |\d+\. )', line):
            ordered = bool(re.match(r'^\d+\. ', line))
            tag = 'ol' if ordered else 'ul'
            items = []
            pattern = r'^\d+\. ' if ordered else r'^- '
            while i < len(lines) and re.match(pattern, lines[i].strip()):
                items.append('<li>' + inline(re.sub(pattern, '', lines[i].strip())) + '</li>')
                i += 1
            result.append('<' + tag + '>' + ''.join(items) + '</' + tag + '>')
            continue
        if re.fullmatch(r'\*\*7-\d\..+\*\*', line):
            result.append('<h3>' + inline(line[2:-2]) + '</h3>')
            i += 1
            continue
        paragraph = [line]
        i += 1
        while i < len(lines) and lines[i].strip() and not re.match(r'^(\||```|- |\d+\. )', lines[i].strip()):
            paragraph.append(lines[i].strip())
            i += 1
        result.append('<p>' + inline(' '.join(paragraph)) + '</p>')
    return '\n'.join(result)


matches = list(re.finditer(r'^\*\*(\d+)\. (.+?)\*\*\s*$', source, re.M))
sections = []
for i, match in enumerate(matches):
    end = matches[i+1].start() if i + 1 < len(matches) else len(source)
    sections.append((int(match[1]), match[2], source[match.end():end]))
assert len(sections) == 19
intro = source[source.find('\n') + 1:matches[0].start()]
labels = ['최종 제안과 판단','주관기관의 평가 관점','원안에서 고칠 내용','최신성 검증 사례','MVP 범위','사용자 경험','데이터 파이프라인','판단·서류 통합','AI와 코드의 역할','무료 기술 구성','개인정보·가상 시연','평가·비교 실험','본선 평가표 대응','AI 개발 작업 분할','일정·중단 기준','무료 예산·호출 한도','발표·예상 질문','제출·출처 관리','첫 세 작업']
groups = {1: '01 / 전략과 범위', 6: '02 / 제품과 기술', 12: '03 / 검증과 실행'}
nav = []
cards = []
for number, title, body in sections:
    if number in groups:
        nav.append('<p class="nav-group">' + groups[number] + '</p>')
    nav.append(f'<a href="#section-{number}" data-section="{number}"><span>{number:02}</span>{labels[number-1]}</a>')
    cards.append(f'<details class="chapter" id="section-{number}" open><summary><span class="chapter-num">{number:02}</span><h2>{html.escape(title)}</h2><span class="chevron" aria-hidden="true">+</span></summary><div class="chapter-body">{render(body)}</div></details>')

CSS = r'''
:root{--ink:#18231d;--muted:#657269;--green:#244b36;--line:#dce2d9;--paper:#f5f6ef;--white:#fff;--lime:#d8f18a;--soft:#edf2e8;--amber:#785a15}
*{box-sizing:border-box}html{scroll-behavior:smooth;scroll-padding-top:90px}body{margin:0;background:var(--paper);color:var(--ink);font-family:"Pretendard","Noto Sans KR","Malgun Gothic",system-ui,sans-serif;line-height:1.85;word-break:keep-all;overflow-wrap:anywhere}a{color:inherit}button,input{font:inherit}button,a,input,summary{touch-action:manipulation}button:focus-visible,a:focus-visible,input:focus-visible,summary:focus-visible,[tabindex]:focus-visible{outline:3px solid #658637;outline-offset:4px}button{cursor:pointer}.skip{position:fixed;top:-90px;left:20px;z-index:100;background:var(--lime);padding:12px}.skip:focus{top:10px}
.topbar{height:66px;position:sticky;top:0;z-index:20;display:flex;justify-content:space-between;align-items:center;padding:0 36px;background:rgba(245,246,239,.96);border-bottom:1px solid var(--line);backdrop-filter:blur(12px)}.brand{display:flex;align-items:center;gap:11px;text-decoration:none;font-size:17px;font-weight:800;letter-spacing:-.5px}.brand-icon{display:grid;place-items:center;width:28px;height:28px;border-radius:8px;background:var(--green);color:var(--lime);font-size:16px}.top-sub{font-size:11px;color:var(--muted);letter-spacing:1.5px;margin-left:10px}.top-actions{display:flex;align-items:center;gap:8px}.button{border:1px solid var(--line);background:transparent;border-radius:7px;padding:7px 13px;font-size:12px;font-weight:700;text-decoration:none;white-space:nowrap}.button.primary{background:var(--ink);color:var(--white);border-color:var(--ink)}.progress{position:fixed;top:64px;left:0;height:2px;background:var(--green);width:0;z-index:25}
.layout{max-width:1512px;margin:auto;display:grid;grid-template-columns:248px minmax(0,1fr);gap:48px;padding:34px 40px 60px}.sidebar{position:sticky;top:94px;align-self:start;max-height:calc(100vh - 112px);overflow:auto;padding:0 16px 12px 0;scrollbar-width:thin}.nav-top{font-size:11px;letter-spacing:2px;font-weight:800;color:var(--muted);padding:4px 0 12px}.search-box{position:relative;margin-bottom:18px}.search-box input{width:100%;background:white;border:1px solid var(--line);border-radius:8px;font-size:12px;padding:10px 12px;color:var(--ink)}.nav-group{margin:20px 0 8px;font-size:10px;color:var(--muted);font-weight:800;letter-spacing:1px}.sidebar nav a{display:flex;align-items:center;gap:11px;text-decoration:none;font-size:12px;color:#526055;padding:6px 9px;border-radius:6px;line-height:1.6;margin:2px 0}.sidebar nav a span{font-size:10px;color:#84907f;font-variant-numeric:tabular-nums;min-width:17px}.sidebar nav a:hover,.sidebar nav a.active{background:#e6eddd;color:var(--green);font-weight:700}.sidebar-foot{border-top:1px solid var(--line);margin-top:24px;padding-top:14px;font-size:10px;color:var(--muted)}.sidebar-foot b{display:block;color:var(--ink)}main{min-width:0;max-width:1050px}.eyebrow{display:flex;align-items:center;gap:10px;color:var(--green);font-size:11px;letter-spacing:2px;font-weight:800}.eyebrow::before{content:"";width:7px;height:7px;border-radius:50%;background:#7c9e45}.hero{padding:14px 0 32px}.hero h1{margin:22px 0 16px;font-size:clamp(38px,4.8vw,66px);line-height:1.19;letter-spacing:-3px;font-weight:800}.hero h1 em{font-style:normal;color:var(--green)}.hero-desc{max-width:720px;font-size:16px;line-height:1.9;color:var(--muted);margin:0}.hero-meta{display:flex;flex-wrap:wrap;gap:10px 24px;margin-top:24px;font-size:11px;color:var(--muted)}.hero-meta b{color:var(--ink);margin-right:5px}
.thesis{background:var(--green);color:white;border-radius:14px;padding:29px 32px;position:relative;overflow:hidden;display:grid;grid-template-columns:1fr 130px;gap:25px}.thesis-label{font-size:10px;letter-spacing:2px;color:#c0d4b5;margin-bottom:12px}.thesis p{font-size:21px;line-height:1.65;margin:0;letter-spacing:-.8px;max-width:620px}.thesis p strong{color:var(--lime)}.thesis-side{border-left:1px solid #53725e;padding-left:24px;display:flex;flex-direction:column;justify-content:center;font-size:11px;color:#dae5d4}.thesis-side strong{font-size:44px;line-height:1.2;color:var(--lime);letter-spacing:-2px}.thesis-side small{margin-top:7px;font-size:10px}
.overview{display:grid;grid-template-columns:repeat(3,1fr);gap:12px;margin:18px 0 26px}.overview-card{background:white;border:1px solid var(--line);border-radius:10px;padding:20px}.overview-label{color:var(--muted);font-size:10px;letter-spacing:1px;font-weight:700}.overview-card strong{display:block;font-size:22px;letter-spacing:-.6px;margin:5px 0}.overview-card p{font-size:12px;color:var(--muted);line-height:1.7;margin:0}
.rubric{padding:24px 26px;border:1px solid var(--line);background:#fff;border-radius:12px;margin-bottom:22px}.block-label{display:flex;justify-content:space-between;align-items:center;margin:0 0 18px;font-size:13px;font-weight:800}.block-label small{font-weight:400;font-size:10px;color:var(--muted)}.score-bar{display:flex;height:12px;gap:4px;border-radius:4px;overflow:hidden}.score-bar span:nth-child(1){background:#244b36}.score-bar span:nth-child(2){background:#628060}.score-bar span:nth-child(3){background:#92a77c}.score-bar span:nth-child(4){background:#b2c78a}.score-bar span:nth-child(5){background:#d8e5ba}.score-bar span:nth-child(6){background:#edf1e3}.score-legend{display:grid;grid-template-columns:repeat(3,1fr);gap:9px 24px;margin-top:17px;font-size:11px}.score-legend span{display:flex;justify-content:space-between;gap:7px;color:var(--muted)}.score-legend b{color:var(--ink);font-variant-numeric:tabular-nums}
.notice{background:#f1efdf;border-left:3px solid #a99850;border-radius:0 7px 7px 0;padding:14px 18px;font-size:12px;color:#695d31;margin:22px 0}.notice strong{color:#4e4527}.meta-note{border:1px solid var(--line);border-radius:9px;background:#f9faf5;font-size:12px;color:var(--muted);padding:0 18px;margin-bottom:26px}.meta-note summary{cursor:pointer;padding:13px 0;font-weight:700;color:#536147}.meta-note p{margin:0 0 14px}.reader-tools{display:flex;align-items:center;justify-content:space-between;padding:12px 0 17px;border-bottom:1px solid var(--ink);margin-top:32px;gap:15px}.reader-tools strong{font-size:14px}.reader-tools small{font-size:11px;color:var(--muted);margin-left:7px}.reader-buttons{display:flex;gap:6px}.reader-buttons button{background:transparent;border:1px solid var(--line);padding:5px 10px;font-size:11px;border-radius:5px}.search-state{font-size:12px;color:var(--green);margin:14px 0}.empty{padding:36px;text-align:center;border:1px dashed var(--line);border-radius:10px;color:var(--muted);font-size:14px}
.chapter{scroll-margin-top:90px;border-bottom:1px solid #d3dbce;margin:0;padding:0}.chapter>summary{list-style:none;cursor:pointer;display:flex;gap:17px;align-items:center;padding:26px 0;min-width:0}.chapter>summary::-webkit-details-marker{display:none}.chapter-num{font-size:12px;font-weight:800;color:var(--green);background:#e8efdd;border-radius:6px;min-width:33px;height:33px;display:grid;place-items:center;font-variant-numeric:tabular-nums}.chapter h2{font-size:21px;line-height:1.5;letter-spacing:-.8px;margin:0;font-weight:750}.chevron{margin-left:auto;color:#6d7b66;font-size:24px;line-height:1;font-weight:400;padding:0 5px}.chapter[open] .chevron{transform:rotate(45deg)}.chapter-body{padding:0 0 28px 50px;font-size:14px;color:#374438}.chapter-body p{margin:0 0 17px}.chapter-body strong{color:#182c1e;font-weight:750}.chapter-body h3{font-size:16px;color:var(--green);margin:30px 0 15px}.chapter-body ul,.chapter-body ol{padding-left:23px;margin:15px 0 22px}.chapter-body li{margin:7px 0;padding-left:3px}.chapter-body li::marker{color:#6e8758}.source-link{color:#426b35;text-decoration:none;border-bottom:1px solid #acc89a;padding-bottom:1px;font-size:.94em}.source-link:hover{color:#172d1a;border-bottom-color:#244b36}.source-link span{font-size:.8em}.table-scroll{overflow:auto;margin:21px 0 24px;border:1px solid var(--line);border-radius:9px;background:white;scrollbar-width:thin}table{border-collapse:collapse;width:100%;font-size:12px;min-width:530px;line-height:1.8;text-align:left}th{background:#edf1e6;color:#405239;font-weight:750;padding:12px 15px;border-bottom:1px solid var(--line);white-space:nowrap}td{padding:13px 15px;border-bottom:1px solid #e8ece3;vertical-align:top}tr:last-child td{border-bottom:0}td:first-child{font-weight:650;color:#2e432c;min-width:105px}tbody tr:nth-child(even){background:#fbfcf8}code{font-family:Consolas,"Malgun Gothic",monospace;font-size:.88em;background:#e8ede0;color:#3b5534;padding:2px 5px;border-radius:4px;word-break:break-word}.code-block{margin:20px 0 24px;border:1px solid #cfd9c4;border-radius:9px;background:#edf1e7;overflow:hidden}.code-label{display:block;font-size:9px;letter-spacing:1.5px;color:#748064;padding:10px 16px;border-bottom:1px solid #d9e1ce;font-weight:800}pre{margin:0;padding:20px;overflow:auto;line-height:1.9;tab-size:2}pre code{padding:0;background:none;border-radius:0;font-size:12px;word-break:normal;white-space:pre}.footer{margin-top:35px;padding:22px 0;font-size:11px;display:flex;justify-content:space-between;gap:12px;color:var(--muted)}.footer a{color:var(--green)}[hidden]{display:none!important}.to-top{position:fixed;right:25px;bottom:24px;border:1px solid #bac8b0;background:var(--white);color:var(--green);border-radius:50%;width:42px;height:42px;font-size:18px;box-shadow:0 3px 14px #19271a0b}
@media(min-width:1500px){.hero h1{font-size:66px}}
@media(max-width:1100px){.layout{grid-template-columns:210px minmax(0,1fr);gap:26px;padding:28px 25px}.chapter-body{padding-left:0}.chapter h2{font-size:19px}.thesis{grid-template-columns:1fr 100px;padding:25px}.thesis-side{padding-left:18px}.thesis p{font-size:19px}.overview-card{padding:17px}.overview-card strong{font-size:19px}}
@media(max-width:800px){.topbar{padding:0 20px;height:60px}.top-sub{display:none}.progress{top:58px}.layout{display:block;padding:22px 20px 35px}.sidebar{position:relative;top:0;max-height:none;padding:0;overflow:visible;margin-bottom:16px}.nav-top,.sidebar nav,.sidebar-foot{display:none}.search-box{margin:0}.search-box input{font-size:13px}.hero{padding-top:10px}.hero h1{font-size:43px;letter-spacing:-2px}.hero-desc{font-size:14px}.hero-meta{gap:7px 16px}.thesis{padding:24px;grid-template-columns:1fr}.thesis-side{display:none}.overview{gap:8px}.overview-card{padding:14px 12px}.overview-card strong{font-size:17px}.overview-card p{font-size:11px}.overview-label{font-size:9px}.rubric{padding:20px}.score-legend{gap:8px 15px;font-size:10px}.chapter>summary{gap:12px}.chapter h2{font-size:18px}.chapter-body{font-size:13px}.reader-tools small{display:none}.footer{flex-direction:column}.top-actions .source-button{display:none}}
@media(max-width:420px){.topbar{padding:0 12px}.brand{font-size:14px;gap:6px}.brand-icon{width:24px;height:24px}.top-actions{gap:5px}.top-actions .button{font-size:10px;padding:6px 8px}.hero h1{font-size:38px}.overview{grid-template-columns:1fr}.overview-card{display:grid;grid-template-columns:105px 1fr;column-gap:10px}.overview-card .overview-label{grid-column:1}.overview-card strong{grid-column:1;margin:0}.overview-card p{grid-column:2;grid-row:1/3;align-self:center}.score-legend{grid-template-columns:repeat(2,1fr)}.chapter h2{font-size:16px}.reader-buttons button{padding:5px 7px}.button{padding:6px 10px}}
@media(prefers-reduced-motion:reduce){html{scroll-behavior:auto}}
@media print{@page{size:A4;margin:16mm 13mm}body{background:white;color:black;font-size:10pt}.topbar,.sidebar,.progress,.reader-tools,.search-state,.to-top,.empty{display:none!important}.layout{display:block;max-width:none;padding:0}main{max-width:none}.hero{padding:0 0 18px}.hero h1{font-size:31pt;letter-spacing:-1.5px}.hero-desc{font-size:11pt}.hero-meta{font-size:8pt}.thesis{border:1px solid #9ea992;background:#f0f4e9!important;color:#18231d;padding:18px;grid-template-columns:1fr 100px;print-color-adjust:exact}.thesis p{font-size:15pt}.thesis p strong,.thesis-side strong{color:#244b36}.thesis-label,.thesis-side{color:#526344}.thesis-side strong{font-size:27pt}.overview,.rubric,.notice,.meta-note{break-inside:avoid}.overview-card{padding:12px}.overview-card strong{font-size:14pt}.overview-card p{font-size:9pt}.chapter{break-inside:auto}.chapter>summary{padding:19px 0 12px;break-after:avoid}.chapter h2{font-size:16pt}.chapter-body{padding:0 0 15px;font-size:10pt}.chapter-body h3{break-after:avoid}.chevron{display:none}.table-scroll{overflow:visible;break-inside:auto}table{min-width:0;table-layout:auto;font-size:8.5pt}th,td{padding:7px 8px}thead{display:table-header-group}tr{break-inside:avoid}td:first-child{min-width:0}pre{white-space:pre-wrap;overflow:visible}pre code{white-space:pre-wrap;font-size:9pt}.code-block{break-inside:avoid}.source-link{color:#244b36;text-decoration:none}.score-bar,.chapter-num{print-color-adjust:exact}.chapter[hidden]{display:block!important}}
'''

JS = r'''
const chapters=[...document.querySelectorAll('.chapter')];
const navLinks=[...document.querySelectorAll('[data-section]')];
const search=document.querySelector('#search');
const state=document.querySelector('#search-state');
const empty=document.querySelector('#empty');
function filter(){const q=search.value.trim().toLocaleLowerCase();let n=0;chapters.forEach(c=>{const found=!q||c.textContent.toLocaleLowerCase().includes(q);c.hidden=!found;if(found){n++;if(q)c.open=true;}const link=document.querySelector('[href="#'+c.id+'"]');if(link)link.hidden=!found;});state.hidden=!q;state.textContent=q?'검색 결과 '+n+'개 섹션 · 전체 19개':'';empty.hidden=n!==0;updateProgress();}
search.addEventListener('input',filter);
search.addEventListener('keydown',e=>{if(e.key==='Escape'){search.value='';filter();}});
document.querySelector('#expand').addEventListener('click',()=>chapters.forEach(c=>c.open=true));
document.querySelector('#collapse').addEventListener('click',()=>chapters.forEach(c=>c.open=false));
function openHash(){const id=decodeURIComponent(location.hash.slice(1));const target=document.getElementById(id);if(target&&target.classList.contains('chapter')){if(target.hidden){search.value='';filter();}target.open=true;requestAnimationFrame(()=>target.scrollIntoView({block:'start'}));}}
navLinks.forEach(a=>a.addEventListener('click',()=>{const c=document.querySelector(a.getAttribute('href'));if(c)c.open=true;}));
window.addEventListener('hashchange',openHash);if(location.hash)openHash();
function updateProgress(){const max=document.documentElement.scrollHeight-window.innerHeight;document.querySelector('#progress').style.width=(max>0?Math.min(100,window.scrollY/max*100):0)+'%';}
window.addEventListener('scroll',updateProgress,{passive:true});window.addEventListener('resize',updateProgress);chapters.forEach(c=>c.addEventListener('toggle',updateProgress));
if('IntersectionObserver'in window){const observer=new IntersectionObserver(entries=>{const visible=entries.filter(e=>e.isIntersecting).sort((a,b)=>a.boundingClientRect.top-b.boundingClientRect.top);if(visible.length){const id=visible[0].target.id;navLinks.forEach(a=>{const active=a.getAttribute('href')==='#'+id;a.classList.toggle('active',active);if(active)a.setAttribute('aria-current','location');else a.removeAttribute('aria-current');});}},{rootMargin:'-85px 0px -65% 0px',threshold:0});chapters.forEach(c=>observer.observe(c));}
let printState=null;
function preparePrint(){if(printState)return;printState=chapters.map(c=>({open:c.open,hidden:c.hidden}));chapters.forEach(c=>{c.open=true;c.hidden=false;});document.querySelector('.meta-note').open=true;}
function restorePrint(){if(!printState)return;chapters.forEach((c,i)=>{c.open=printState[i].open;c.hidden=printState[i].hidden;});printState=null;}
window.addEventListener('beforeprint',preparePrint);window.addEventListener('afterprint',restorePrint);
document.querySelector('#print').addEventListener('click',()=>{preparePrint();window.print();});
document.querySelector('#top').addEventListener('click',()=>window.scrollTo({top:0,behavior:matchMedia('(prefers-reduced-motion: reduce)').matches?'instant':'smooth'}));
updateProgress();
'''

document = '''<!doctype html>
<html lang="ko"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><meta name="color-scheme" content="light"><meta name="description" content="청년비서 AI 해커톤 전략과 실행계획. 데이터 파이프라인, 기술 구조, 평가 실험, 일정과 발표 계획."><title>청년비서 · 무료 구성 실행계획</title><style>''' + CSS + '''</style></head><body>
<a class="skip" href="#main">본문으로 건너뛰기</a>
<header class="topbar"><a class="brand" href="#"><span class="brand-icon" aria-hidden="true">↗</span>청년비서<span class="top-sub">PROJECT BLUEPRINT</span></a><div class="top-actions"><a class="button source-button" href="''' + urllib.parse.quote(SOURCE.name) + '''" download>원문 Markdown</a><a class="button" href="청년비서_한장_구현계획서.html">한 장 구현계획</a><button class="button primary" id="print" type="button">인쇄 / PDF 저장</button></div></header><div class="progress" id="progress" aria-hidden="true"></div>
<div class="layout"><aside class="sidebar" aria-label="문서 탐색"><div class="nav-top">CONTENTS / 19 SECTIONS</div><div class="search-box"><label for="search" class="sr-only" style="position:absolute;width:1px;height:1px;overflow:hidden;clip-path:inset(50%)">문서 내용 검색</label><input id="search" type="search" placeholder="문서 검색 · 예: 데이터, 평가" autocomplete="off"></div><nav>''' + ''.join(nav) + '''</nav><div class="sidebar-foot"><b>2026 청년 CAREER FAIR</b>AI 해커톤 프로젝트 기획 문서<br>정책 조사 2026.11.13<br>무료 구성 개정 2026.11.14</div></aside>
<main id="main"><div class="hero"><div class="eyebrow">2026 AI HACKATHON · FREE-TIER EDITION</div><h1>청년비서,<br><em>신청 준비를 끝내다.</em></h1><p class="hero-desc">공식 공고의 조건을 사용자의 준비 상태와 연결하고,<br>지금 해야 할 일을 갱신하는 AI 에이전트.</p><div class="hero-meta"><span><b>DOCUMENT</b>무료 구성 · 상세 실행계획</span><span><b>BUDGET</b>추가 결제 0원 목표</span><span><b>UPDATED</b>2026.11.14 · 무료안</span></div></div>
<div class="thesis"><div><div class="thesis-label">THE CORE STRATEGY</div><p>검수한 소수의 정책으로<br><strong>처음부터 끝까지 작동하는 준비 경험.</strong><br>그 효과는 시간과 누락으로 증명한다.</p></div><div class="thesis-side">본선 핵심 배점<strong>45<span style="font-size:18px;letter-spacing:0">점</span></strong><small>AI 활용 25 + 구현 20<br>100점 중 배점 합계</small></div></div>
<div class="overview"><div class="overview-card"><span class="overview-label">FIRST USER</span><strong>취업 준비 청년</strong><p>응시료 지원의 조건 확인부터<br>서류 준비·최종 점검까지</p></div><div class="overview-card"><span class="overview-label">MVP SCOPE · 계획</span><strong>핵심 흐름 1개</strong><p>검수 자료 묶음 4~6개<br>변경·종료 사례 포함</p></div><div class="overview-card"><span class="overview-label">SUBMISSION · 공고 기준</span><strong>11.23 / 17:00</strong><p>11월 22일 완성·동결 목표<br>업로드 + 동일 자료 이메일</p></div></div>
<div class="rubric"><div class="block-label">본선 평가 기준<small>배점 기준 · 예상 획득 점수가 아님</small></div><div class="score-bar" aria-hidden="true"><span style="flex:25"></span><span style="flex:20"></span><span style="flex:15"></span><span style="flex:15"></span><span style="flex:15"></span><span style="flex:10"></span></div><div class="score-legend"><span>AI 활용 수준<b>25</b></span><span>기술 구현·완성도<b>20</b></span><span>문제 중요성·효과<b>15</b></span><span>혁신성·차별성<b>15</b></span><span>실제 활용·확장<b>15</b></span><span>발표·시연·Q&A<b>10</b></span></div></div>
<div class="notice"><strong>계획과 성과를 구분합니다.</strong> 무료 플랜의 한도 내에서 추가 API·호스팅 결제 0원을 목표로 합니다. 한도 소진 시 유료 전환 없이 중단하며, 무제한·무중단은 보장하지 않습니다. 무료 조건은 11월 14일 확인했고 정책 조사는 11월 13일 기준입니다. 성능 수치는 아직 검증할 목표입니다.</div>
<details class="meta-note"><summary>작성 전제와 검증 범위 보기</summary>''' + render(intro) + '''</details>
<div class="reader-tools"><div><strong>상세 실행계획</strong><small>전략부터 데이터·개발·검증·제출까지</small></div><div class="reader-buttons"><button id="expand" type="button">모두 펼치기</button><button id="collapse" type="button">모두 접기</button></div></div><p class="search-state" id="search-state" role="status" aria-live="polite" hidden></p><div class="empty" id="empty" hidden>일치하는 섹션이 없습니다. 다른 검색어를 입력하거나 Esc로 검색을 지워주세요.</div>
''' + '\n'.join(cards) + '''
<footer class="footer"><span>청년비서 · 2026 AI 해커톤 무료 실행계획<br>전체 19개 섹션 수록 · 공식 출처는 본문 링크 참조</span><a href="#main">문서 처음으로 ↑</a></footer></main></div><button id="top" class="to-top" type="button" aria-label="맨 위로 이동">↑</button>
<script>''' + JS + '''</script></body></html>'''

OUTPUT.write_text(document, encoding='utf-8')
print(f'Created: {OUTPUT.name} ({OUTPUT.stat().st_size:,} bytes); {len(sections)} sections')
