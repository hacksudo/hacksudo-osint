from flask import Flask, render_template, request, jsonify, send_file
from datetime import datetime
from concurrent.futures import ThreadPoolExecutor, as_completed
from urllib.parse import quote_plus, urlparse, urljoin, parse_qs
import hashlib, os, re, time, requests, io, html, json
from bs4 import BeautifulSoup

app=Flask(__name__); app.config['MAX_CONTENT_LENGTH']=8*1024*1024
UA='Mozilla/5.0 (compatible; OSINTX/6.0; authorized-public-source-research)'
HTTP=requests.Session(); HTTP.headers.update({'User-Agent':UA,'Accept-Language':'en-US,en;q=.8'})
PLATFORMS=['All public web','GitHub','Reddit']
SOCIAL={'github.com':'GitHub','reddit.com':'Reddit','youtube.com':'YouTube','youtu.be':'YouTube','instagram.com':'Instagram','facebook.com':'Facebook','linkedin.com':'LinkedIn','x.com':'X','twitter.com':'X','tiktok.com':'TikTok','pinterest.com':'Pinterest','medium.com':'Medium','dev.to':'DEV','stackoverflow.com':'Stack Overflow','threads.net':'Threads','docker.com':'Docker Hub','hub.docker.com':'Docker Hub','vulnhub.com':'VulnHub'}
SKIP_EXT=('.zip','.exe','.dmg','.iso','.apk','.pdf','.doc','.docx','.xls','.xlsx','.ppt','.pptx')
KEYS={'openai':'OPENAI_API_KEY','brave':'BRAVE_SEARCH_API_KEY','google':'GOOGLE_CSE_API_KEY','google_cx':'GOOGLE_CSE_CX','youtube':'YOUTUBE_API_KEY'}
CASES={}
try:
 import keyring
except Exception:
 keyring=None

def clean(v): return re.sub(r'\s+',' ',(v or '').strip())
def norm(v): return re.sub(r'[^a-z0-9]','',clean(v).lower())
def cid(name): return hashlib.sha256(f'{name}-{time.time_ns()}'.encode()).hexdigest()[:10].upper()
def domain(url):
 try:return urlparse(url).netloc.lower().removeprefix('www.')
 except:return ''
def get_secret(provider):
 env=KEYS.get(provider,''); v=os.getenv(env,'').strip()
 if v:return v
 if keyring:
  try:return (keyring.get_password('OSINTX',provider) or '').strip()
  except Exception:return ''
 return ''
def save_secret(provider,value):
 if provider not in KEYS:return False,'Unknown provider'
 if not value:return False,'Key cannot be empty'
 if not keyring:return False,'OS keyring unavailable. Set '+KEYS[provider]+' in your shell instead.'
 try:keyring.set_password('OSINTX',provider,value);return True,'Saved in OS credential store'
 except Exception as e:return False,str(e)[:120]
def key_status():return {p:{'configured':bool(get_secret(p)),'env':KEYS[p]} for p in KEYS}
def category(url,title='',desc=''):
 d=domain(url); txt=(title+' '+desc+' '+url).lower()
 if any(x in txt for x in ['youtube.com/watch','youtu.be/','youtube.com/shorts/','vimeo.com/','dailymotion.com/video',' video ']):return 'videos'
 if any(x in txt for x in ['news','article','blog','medium.com','substack','wordpress','writeup','walkthrough']):return 'news_blogs'
 if d in SOCIAL or any(h in d for h in SOCIAL):return 'social'
 return 'web'
def queries(t):
 n=t['name'];u=t.get('username');loc=t.get('location');email=t.get('email');phone=t.get('phone')
 q=[n,f'"{n}"']
 if loc:q += [f'"{n}" "{loc}"',f'{n} {loc}']
 if u:q += [u,f'"{u}"',f'"{n}" "{u}"']
 if email:q += [f'"{email}"']
 if phone:q += [f'"{phone}"']
 site_map={'Instagram':'instagram.com','LinkedIn':'linkedin.com','GitHub':'github.com','YouTube':'youtube.com','X / Twitter':'x.com','Facebook':'facebook.com','TikTok':'tiktok.com','Reddit':'reddit.com','Medium':'medium.com','Pinterest':'pinterest.com','Threads':'threads.net','Mastodon':'mastodon.social','Twitch':'twitch.tv','Vimeo':'vimeo.com'}
 for a in t.get('social_accounts',[]) or []:
  handle=clean(a.get('username'));platform=clean(a.get('platform'))
  if not handle:continue
  q += [handle,f'"{handle}"',f'"{n}" "{handle}"']
  if platform and platform!='Any platform':
   dom=site_map.get(platform)
   if dom:q += [f'site:{dom} "{handle}"',f'site:{dom} "{n}" "{handle}"']
   else:q += [f'"{platform}" "{handle}"']
 # broad vertical/site pivots
 pivot=u or n
 for d in ['github.com','reddit.com','youtube.com','instagram.com','x.com','linkedin.com','facebook.com','tiktok.com','medium.com','vulnhub.com','docker.com']:
  q.append(f'site:{d} "{pivot}"')
 return list(dict.fromkeys([x for x in q if x]))[:60]

def row(source,url,title='',desc='',query='',thumb='',cat=None):
 return {'source':source,'state':'found','category':cat or category(url,title,desc),'title':clean(title) or domain(url) or 'Public result','url':url,'description':clean(desc),'thumbnail':thumb or '','query':query,'domain':domain(url)}

def ddg_search(q,max_results=30):
 try:
  r=HTTP.get('https://html.duckduckgo.com/html/',params={'q':q},timeout=18);r.raise_for_status();soup=BeautifulSoup(r.text,'html.parser');out=[]
  for a in soup.select('.result__a')[:max_results]:
   href=a.get('href','');block=a.find_parent(class_='result');desc='';sn=block.select_one('.result__snippet') if block else None
   if sn:desc=sn.get_text(' ',strip=True)
   if 'duckduckgo.com/l/' in href:href=parse_qs(urlparse(href).query).get('uddg',[href])[0]
   if href.startswith('http'):out.append(row('No-key Web',href,a.get_text(' ',strip=True),desc,q))
  return out,'ok'
 except Exception as e:return [],'error:'+str(e)[:90]
def ddg_all(t):
 out=[];bad=0
 for q in queries(t)[:16]:
  r,s=ddg_search(q);out+=r;bad+=s!='ok'
 return out,[{'name':'No-key Web','status':'ok' if out else 'error','detail':f'{len(out)} raw results · {bad} failed queries'}]

def brave_req(endpoint,q,count,offset=0):
 key=get_secret('brave')
 if not key:return {},'needs_key'
 try:
  r=HTTP.get(f'https://api.search.brave.com/res/v1/{endpoint}/search',headers={'X-Subscription-Token':key,'Accept':'application/json'},params={'q':q,'count':count,'offset':offset,'safesearch':'moderate'},timeout=25)
  if r.status_code in (401,403):return {},'auth_error'
  if r.status_code==429:return {},'rate_limited'
  r.raise_for_status();return r.json(),'ok'
 except Exception as e:return {},'error:'+str(e)[:90]
def brave_all(t):
 out=[];health=[]; qs=queries(t); main=(t.get('username') or t['name'])
 # Web: page through high-value queries; stop when provider says there are no more results.
 raw=0;state='ok'
 for q in qs[:14]:
  for off in range(5):
   data,state=brave_req('web',q,20,off)
   if state!='ok':break
   rr=data.get('web',{}).get('results',[])
   for x in rr:out.append(row('Brave Web',x.get('url',''),x.get('title',''),x.get('description',''),q));raw+=1
   if not data.get('query',{}).get('more_results_available',False):break
  if state!='ok':break
 health.append({'name':'Brave Web','status':state if not raw else 'ok','detail':f'{raw} raw indexed results'})
 # Dedicated verticals. Images API can return large sets; query variants improve recall.
 for endpoint,cat,limit in [('images','images',200),('videos','videos',50),('news','news_blogs',50)]:
  n=0;last='ok'
  for q in list(dict.fromkeys([main,f'"{main}"',f'{main} {t.get("name","")}']))[:3]:
   data,last=brave_req(endpoint,q,limit,0)
   if last!='ok':break
   bucket=data.get(endpoint,{}) if isinstance(data.get(endpoint,{}),dict) else data
   for x in bucket.get('results',[]) or data.get('results',[]):
    props=x.get('properties') or {}; url=x.get('url') or x.get('page_url') or props.get('url') or x.get('source_url') or ''
    th=x.get('thumbnail') or x.get('thumbnail_url') or props.get('thumbnail') or ''
    if isinstance(th,dict):th=th.get('src') or th.get('url') or ''
    # For images, preserve the actual image URL as thumbnail while linking to source page when available.
    if endpoint=='images':
     th=th or props.get('url') or x.get('url') or ''
     url=x.get('source') or x.get('page_url') or x.get('url') or ''
     if isinstance(url,dict):url=url.get('url','')
    out.append(row('Brave '+endpoint.title(),url,x.get('title') or x.get('description') or 'Result',x.get('description') or '',q,th,cat));n+=1
  health.append({'name':'Brave '+endpoint.title(),'status':last if not n else 'ok','detail':f'{n} specialized results'})
 return out,health

def google_cse_all(t):
 key=get_secret('google'); cx=get_secret('google_cx')
 if not key or not cx:
  return [],[{'name':'Google Programmable Search','status':'needs_key','detail':'Optional: add Google API key + Search Engine ID (cx) in API Sources.'}]
 out=[]; health=[]; base='https://www.googleapis.com/customsearch/v1'; qs=queries(t); raw=0; state='ok'
 # Google JSON API returns at most 100 results per query, 10/page.
 for q in qs[:12]:
  for start in range(1,92,10):
   try:
    r=HTTP.get(base,params={'key':key,'cx':cx,'q':q,'num':10,'start':start,'safe':'active'},timeout=25)
    if r.status_code in (401,403): state='auth_error'; break
    if r.status_code==429: state='rate_limited'; break
    r.raise_for_status(); data=r.json(); items=data.get('items',[]) or []
    for x in items:
     out.append(row('Google Web',x.get('link',''),x.get('title',''),x.get('snippet',''),q)); raw+=1
    if len(items)<10: break
   except Exception as e: state='error'; break
  if state!='ok': break
 health.append({'name':'Google Web','status':state if not raw else 'ok','detail':f'{raw} indexed results'})
 # Dedicated Google image search, capped at 100/query by the API.
 n=0; img_state='ok'; pivot=t.get('username') or t['name']
 for q in list(dict.fromkeys([pivot,f'"{pivot}"',f'{pivot} {t.get("name","")}']))[:3]:
  for start in range(1,92,10):
   try:
    r=HTTP.get(base,params={'key':key,'cx':cx,'q':q,'num':10,'start':start,'searchType':'image','safe':'active'},timeout=25)
    if r.status_code in (401,403): img_state='auth_error'; break
    if r.status_code==429: img_state='rate_limited'; break
    r.raise_for_status(); items=(r.json().get('items') or [])
    for x in items:
     info=x.get('image') or {}; src=x.get('link',''); page=info.get('contextLink') or src
     out.append(row('Google Images',page,x.get('title','Google image'),x.get('snippet',''),q,src,'images')); n+=1
    if len(items)<10: break
   except Exception: img_state='error'; break
  if img_state!='ok': break
 health.append({'name':'Google Images','status':img_state if not n else 'ok','detail':f'{n} image results'})
 return out,health

def openai_search(t):
 key=get_secret('openai')
 if not key:return [],[{'name':'OpenAI Web Search','status':'needs_key','detail':'Optional: configure OpenAI in Settings.'}]
 model=os.getenv('OPENAI_MODEL','gpt-6-luna').strip() or 'gpt-6-luna'
 prompt='Authorized public-source discovery. Find public pages for this subject/alias across websites, profiles, blogs, articles, repositories and videos. Return broad source coverage; do not infer private data. Search terms: '+'; '.join(queries(t)[:16])
 payload={'model':model,'tools':[{'type':'web_search'}],'tool_choice':'auto','include':['web_search_call.action.sources'],'input':prompt,'store':False}
 try:
  r=HTTP.post('https://api.openai.com/v1/responses',headers={'Authorization':f'Bearer {key}','Content-Type':'application/json'},json=payload,timeout=90)
  if r.status_code in (401,403):return [],[{'name':'OpenAI Web Search','status':'auth_error','detail':'Check configured key.'}]
  if r.status_code==429:return [],[{'name':'OpenAI Web Search','status':'rate_limited','detail':'Rate limit reached.'}]
  r.raise_for_status();data=r.json();out=[];seen=set()
  for item in data.get('output',[]):
   if item.get('type')=='web_search_call':
    for s in (item.get('action') or {}).get('sources',[]) or []:
     u=s.get('url','')
     if u.startswith('http') and u not in seen:seen.add(u);out.append(row('OpenAI Web Search',u,s.get('title',''),'Public source returned by web search.'))
  return out,[{'name':'OpenAI Web Search','status':'ok','detail':f'{len(out)} source URLs · {model}'}]
 except Exception as e:return [],[{'name':'OpenAI Web Search','status':'error','detail':str(e)[:140]}]

def youtube_all(t):
 key=get_secret('youtube') or get_secret('google')
 if not key:
  return [],[{'name':'YouTube Videos','status':'needs_key','detail':'Optional: add YouTube API key (or Google key) for dedicated video search.'}]
 pivot=t.get('username') or t['name']
 yqs=list(dict.fromkeys([pivot,f'"{pivot}"',f'{pivot} tutorial',f'{pivot} walkthrough',f'{pivot} demo',f'{pivot} interview',f'{pivot} review',f'{pivot} cybersecurity']))
 out=[]; state='ok'; seen=set()
 try:
  # Multiple intent queries dramatically improve video recall. Keep a bounded budget.
  for q in yqs:
   token=None; pages=0
   while pages<3:
    params={'key':key,'part':'snippet','type':'video','q':q,'maxResults':50,'safeSearch':'moderate','order':'relevance'}
    if token:params['pageToken']=token
    r=HTTP.get('https://www.googleapis.com/youtube/v3/search',params=params,timeout=25)
    if r.status_code in (401,403):state='auth_error';break
    if r.status_code==429:state='rate_limited';break
    r.raise_for_status();data=r.json()
    for x in data.get('items',[]):
     vid=(x.get('id') or {}).get('videoId');sn=x.get('snippet') or {}
     if not vid or vid in seen:continue
     seen.add(vid)
     th=((sn.get('thumbnails') or {}).get('high') or (sn.get('thumbnails') or {}).get('medium') or {}).get('url','')
     out.append(row('YouTube API','https://www.youtube.com/watch?v='+vid,sn.get('title','YouTube video'),sn.get('description',''),q,th,'videos'))
    token=data.get('nextPageToken');pages+=1
    if not token:break
   if state!='ok':break
  return out,[{'name':'YouTube Videos','status':'ok' if out else state,'detail':f'{len(out)} dedicated video results · {len(yqs)} query intents'}]
 except Exception as e:
  return out,[{'name':'YouTube Videos','status':'error','detail':str(e)[:120]}]

def crawl_one(x,t):
 url=x.get('url','')
 if not url.startswith(('http://','https://')) or url.lower().endswith(SKIP_EXT):return []
 try:
  r=HTTP.get(url,timeout=10,allow_redirects=True);ct=r.headers.get('content-type','')
  if r.status_code!=200 or 'text/html' not in ct:return []
  soup=BeautifulSoup(r.text[:1_500_000],'html.parser');out=[];terms=[norm(t.get('name')),norm(t.get('username'))]
  text=norm((soup.title.get_text(' ',strip=True) if soup.title else '')+' '+soup.get_text(' ',strip=True)[:9000]);relevant=any(z and z in text for z in terms)
  if relevant:
   # OG/Twitter images + page images.
   for m in soup.select('meta[property="og:image"],meta[name="twitter:image"]')[:8]:
    src=urljoin(r.url,m.get('content',''))
    if src.startswith('http'):out.append(row('Page Media',r.url,'Page image','Image from relevant public page.',thumb=src,cat='images'))
   for im in soup.find_all('img',src=True)[:35]:
    src=urljoin(r.url,im.get('src'));alt=im.get('alt','')
    if src.startswith('http') and not src.startswith('data:'):out.append(row('Page Media',r.url,alt or 'Page image','Image from relevant public page.',thumb=src,cat='images'))
  for a in soup.find_all('a',href=True)[:400]:
   href=urljoin(r.url,a.get('href'));label=a.get_text(' ',strip=True);blob=norm(label+' '+href);d=domain(href)
   if href.startswith('http') and (d in SOCIAL or any(h in d for h in SOCIAL) or any(z and z in blob for z in terms)):
    out.append(row('Page Crawl',href,label or d,'Cross-link from '+domain(r.url)))
  return out[:120]
 except:return []
def deep_crawl(results,t):
 seeds=[x for x in results if x.get('category') in ('web','news_blogs','social') and x.get('url')][:40];out=[]
 with ThreadPoolExecutor(max_workers=10) as ex:
  for r in ex.map(lambda x:crawl_one(x,t),seeds):out+=r
 return out,[{'name':'Second-hop Crawl','status':'ok','detail':f'{len(seeds)} pages inspected · {len(out)} links/media extracted'}]
def score(x,t):
 p=0;sig=[]; title=norm(x.get('title')); desc=norm(x.get('description')); urln=norm(x.get('url'));
 for label,val,weights in [('alias',t.get('username'),(34,24,18)),('name',t.get('name'),(28,18,12)),('location',t.get('location'),(14,10,6))]:
  z=norm(val)
  if not z: continue
  if z in title:p+=weights[0];sig.append(f'{label} in title')
  elif z in desc:p+=weights[1];sig.append(f'{label} in snippet')
  elif z in urln:p+=weights[2];sig.append(f'{label} in URL')
 if x.get('source') in ('Brave Images','Brave Videos','Brave News','Google Images','YouTube API'):p+=10;sig.append('specialized index')
 # Dedicated video results with the exact pivot in title are strong topical matches.
 pivot=norm(t.get('username') or t.get('name'))
 if x.get('category')=='videos' and pivot and pivot in title:
  p+=20;sig.append('exact video-title match')
 if x.get('source')=='YouTube API':
  p+=8;sig.append('YouTube API verified')
 if x.get('source')=='Page Crawl':p+=4;sig.append('cross-linked page')
 for a in t.get('social_accounts',[]) or []:
  handle=norm(a.get('username'));platform=norm(a.get('platform'))
  if handle and (handle in title or handle in desc or handle in urln):
   p+=18;sig.append('known social handle match')
   if platform and platform!='any platform' and platform.split()[0] in norm(x.get('source','')+' '+x.get('domain','')+' '+x.get('url','')):
    p+=12;sig.append('expected social platform')
 x['confidence']=min(99,p);x['signals']=sig;x['conflicts']=[];x['classification']='high' if p>=70 else 'medium' if p>=45 else 'candidate';return x

def run(t):
 results=[];health=[]
 with ThreadPoolExecutor(max_workers=4) as ex:
  for f in as_completed([ex.submit(ddg_all,t),ex.submit(brave_all,t),ex.submit(google_cse_all,t),ex.submit(openai_search,t),ex.submit(youtube_all,t)]):
   try:r,h=f.result();results+=r;health+=h
   except Exception as e:health.append({'name':'Discovery','status':'error','detail':str(e)[:100]})
 seen=set();base=[]
 for x in results:
  # Images may share source page; include thumbnail in dedupe key.
  k=((x.get('url') or '').split('#')[0].rstrip('/').lower(),x.get('thumbnail','') if x.get('category')=='images' else '')
  if k[0] and k not in seen:seen.add(k);base.append(x)
 crawled,ch=deep_crawl(base,t);health+=ch
 for x in crawled:
  k=((x.get('url') or '').split('#')[0].rstrip('/').lower(),x.get('thumbnail','') if x.get('category')=='images' else '')
  if k[0] and k not in seen:seen.add(k);base.append(x)
 final=[score(x,t) for x in base];final.sort(key=lambda x:x.get('confidence',0),reverse=True);return final[:1200],health


def build_profile(t,results,excluded=None):
 excluded=excluded or set(); kept=[x for i,x in enumerate(results) if i not in excluded]
 domains={}
 cats={}
 for x in kept:
  domains[x.get('domain','unknown')]=domains.get(x.get('domain','unknown'),0)+1
  cats[x.get('category','web')]=cats.get(x.get('category','web'),0)+1
 social=sum(1 for x in kept if x.get('category')=='social')
 blogs=sum(1 for x in kept if x.get('category')=='news_blogs')
 # Evidence-based type suggestion, intentionally conservative.
 q=(t.get('name') or '').lower()
 company_terms=sum(1 for x in kept[:100] if any(w in (x.get('title','')+' '+x.get('description','')).lower() for w in ['company','official','pvt ltd','inc.','llc','brand']))
 person_terms=sum(1 for x in kept[:100] if any(w in (x.get('title','')+' '+x.get('description','')).lower() for w in ['profile','author','linkedin','github']))
 if company_terms>person_terms*1.4 and company_terms>=3: etype='Organization / Brand'
 elif person_terms>=4: etype='Person / Alias'
 elif t.get('location') and len(kept)<20: etype='Place / Local entity'
 else: etype='Alias / Project / Topic'
 avg=round(sum(x.get('confidence',0) for x in kept[:40])/max(1,min(40,len(kept))))
 topdomains=sorted(domains.items(),key=lambda z:z[1],reverse=True)[:12]
 return {'entity_type':etype,'confidence':min(95,max(15,avg+min(25,len(kept)//8))),'evidence_count':len(kept),'excluded_count':len(excluded),'category_counts':cats,'top_domains':[{'domain':d,'count':c} for d,c in topdomains]}

@app.post('/api/case/<case_id>/exclude')
def exclude_evidence(case_id):
 c=CASES.get(case_id)
 if not c:return jsonify({'error':'Case not found'}),404
 data=request.get_json(silent=True) or {}; idx=int(data.get('index',-1))
 if idx<0 or idx>=len(c['payload']['candidates']):return jsonify({'error':'Invalid evidence index'}),400
 if data.get('excluded',True):c['excluded'].add(idx)
 else:c['excluded'].discard(idx)
 c['payload']['profile']=build_profile(c['target'],c['payload']['candidates'],c['excluded'])
 return jsonify({'ok':True,'profile':c['payload']['profile'],'excluded':sorted(c['excluded'])})

@app.get('/api/case/<case_id>/export/<fmt>')
def export_case(case_id,fmt):
 c=CASES.get(case_id)
 if not c:return jsonify({'error':'Case not found'}),404
 p=c['payload']; excluded=c['excluded']; rows=[x for i,x in enumerate(p['candidates']) if i not in excluded]; prof=build_profile(c['target'],p['candidates'],excluded)
 if fmt=='html':
  cards=[]
  for x in rows:
   cards.append(f'''<article class="evidence"><div class="meta"><span>{html.escape(x.get("category","web").upper())}</span><b>{x.get("confidence",0)}% RELEVANCE</b></div><h3>{html.escape(x.get("title","Untitled"))}</h3><p>{html.escape((x.get("description") or "")[:900])}</p><div class="foot"><span>{html.escape(x.get("source",""))} · {html.escape(x.get("domain",""))}</span><a href="{html.escape(x.get("url",""))}">OPEN SOURCE ↗</a></div></article>''')
  report=f'''<!doctype html><html><head><meta charset="utf-8"><meta name="viewport" content="width=device-width"><title>HACKSUDO Evidence Profile — {html.escape(p["subject"])}</title><style>*{{box-sizing:border-box}}body{{margin:0;background:#060807;color:#edf2ee;font:14px system-ui,sans-serif}}.wrap{{max-width:1100px;margin:auto;padding:48px 28px}}header{{border-bottom:1px solid #29312c;padding-bottom:28px;margin-bottom:28px}}.brand{{color:#c8ff38;font:800 12px monospace;letter-spacing:.18em}}h1{{font-size:52px;margin:12px 0}}.summary{{display:grid;grid-template-columns:repeat(3,1fr);gap:10px;margin:24px 0}}.stat,.evidence{{border:1px solid #303833;background:#0b0f0c;padding:18px}}.evidence{{margin:10px 0}}.stat small,.meta,.foot{{color:#849088;font:10px monospace}}.stat b{{display:block;color:#c8ff38;font-size:25px;margin-top:7px}}.meta,.foot{{display:flex;justify-content:space-between;gap:12px}}.meta b,a{{color:#c8ff38}}h3{{font-size:18px;margin:12px 0 8px}}p{{color:#aab3ad;line-height:1.6}}a{{text-decoration:none}}footer{{border-top:1px solid #29312c;margin-top:35px;padding-top:18px;color:#657169;font:10px monospace}}@media(max-width:650px){{.summary{{grid-template-columns:1fr}}h1{{font-size:36px}}}}</style></head><body><div class="wrap"><header><div class="brand">OSINT — HACKSUDO / EVIDENCE PROFILE</div><h1>{html.escape(p["subject"])}</h1><p>Reviewable public-source intelligence report. Search hits are leads, not proof of identity.</p></header><section class="summary"><div class="stat"><small>SUGGESTED ENTITY TYPE</small><b>{html.escape(prof["entity_type"])}</b></div><div class="stat"><small>PROFILE CONFIDENCE</small><b>{prof["confidence"]}%</b></div><div class="stat"><small>ACCEPTED EVIDENCE</small><b>{len(rows)}</b></div></section><h2>Accepted evidence</h2>{"".join(cards)}<footer>© HACKSUDO · ALL RIGHTS RESERVED · VISHAL WAGHMARE · hacksudo.com</footer></div></body></html>'''
  return send_file(io.BytesIO(report.encode()),mimetype='text/html',as_attachment=True,download_name=f'{case_id}-profile.html')
 if fmt=='xlsx':
  from openpyxl import Workbook
  wb=Workbook();ws=wb.active;ws.title='Evidence'
  ws.append(['Title','Category','Source','Domain','Relevance %','URL','Description'])
  for x in rows:ws.append([x.get('title'),x.get('category'),x.get('source'),x.get('domain'),x.get('confidence'),x.get('url'),x.get('description')])
  ps=wb.create_sheet('Profile');ps.append(['Field','Value']);ps.append(['Entity type',prof['entity_type']]);ps.append(['Confidence',prof['confidence']]);ps.append(['Accepted evidence',len(rows)]);ps.append(['Excluded',len(excluded)])
  bio=io.BytesIO();wb.save(bio);bio.seek(0);return send_file(bio,mimetype='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',as_attachment=True,download_name=f'{case_id}-profile.xlsx')
 if fmt=='pdf':
  from reportlab.lib.pagesizes import A4
  from reportlab.platypus import SimpleDocTemplate,Paragraph,Spacer,Table,TableStyle
  from reportlab.lib.styles import getSampleStyleSheet,ParagraphStyle
  from reportlab.lib import colors
  bio=io.BytesIO();doc=SimpleDocTemplate(bio,pagesize=A4,rightMargin=38,leftMargin=38,topMargin=42,bottomMargin=42)
  st=getSampleStyleSheet();title=ParagraphStyle('HSTitle',parent=st['Title'],fontName='Helvetica-Bold',fontSize=28,leading=31,textColor=colors.HexColor('#101512'),spaceAfter=8);eye=ParagraphStyle('HSEye',parent=st['BodyText'],fontName='Courier-Bold',fontSize=8,textColor=colors.HexColor('#4f6b24'),spaceAfter=7);body=ParagraphStyle('HSBody',parent=st['BodyText'],fontSize=9.5,leading=14,textColor=colors.HexColor('#39423d'));h3=ParagraphStyle('HSH3',parent=st['Heading3'],fontSize=11,leading=14,textColor=colors.HexColor('#101512'),spaceAfter=4);link=ParagraphStyle('HSLink',parent=body,fontName='Courier',fontSize=7.5,textColor=colors.HexColor('#42621b'))
  story=[Paragraph('OSINT — HACKSUDO / EVIDENCE PROFILE',eye),Paragraph(html.escape(p['subject']),title),Paragraph('Reviewable public-source intelligence report. Search hits are leads and should be independently verified.',body),Spacer(1,16)]
  summary=[[Paragraph('<b>ENTITY TYPE</b>',body),Paragraph('<b>PROFILE CONFIDENCE</b>',body),Paragraph('<b>ACCEPTED EVIDENCE</b>',body)],[Paragraph(html.escape(prof['entity_type']),h3),Paragraph(f"{prof['confidence']}%",h3),Paragraph(str(len(rows)),h3)]]
  tbl=Table(summary,colWidths=[170,150,150],hAlign='LEFT');tbl.setStyle(TableStyle([('BACKGROUND',(0,0),(-1,-1),colors.HexColor('#F3F6F2')),('BOX',(0,0),(-1,-1),0.5,colors.HexColor('#C8D0CA')),('INNERGRID',(0,0),(-1,-1),0.25,colors.HexColor('#DDE3DE')),('VALIGN',(0,0),(-1,-1),'TOP'),('LEFTPADDING',(0,0),(-1,-1),10),('RIGHTPADDING',(0,0),(-1,-1),10),('TOPPADDING',(0,0),(-1,-1),8),('BOTTOMPADDING',(0,0),(-1,-1),8)]));story += [tbl,Spacer(1,20),Paragraph('ACCEPTED EVIDENCE',eye)]
  for i,x in enumerate(rows[:180],1):story += [Paragraph(f"{i:03d} · {html.escape(x.get('title','Untitled'))}",h3),Paragraph(html.escape((x.get('description') or 'No public snippet available.')[:850]),body),Paragraph(f"{html.escape(x.get('source',''))} · {x.get('confidence',0)}% relevance · {html.escape(x.get('url',''))}",link),Spacer(1,10)]
  story += [Spacer(1,12),Paragraph('© HACKSUDO · ALL RIGHTS RESERVED · VISHAL WAGHMARE · hacksudo.com',eye)]
  doc.build(story);bio.seek(0);return send_file(bio,mimetype='application/pdf',as_attachment=True,download_name=f'{case_id}-profile.pdf')
 return jsonify({'error':'Use html, xlsx or pdf'}),400

@app.get('/health')
def health():
 return jsonify({'status':'ok','service':'OSINT-HACKSUDO'}),200

@app.get('/')
def home():return render_template('index.html',platforms=PLATFORMS)
@app.get('/api/settings')
def settings():return jsonify(key_status())
@app.post('/api/settings/<provider>')
def settings_save(provider):
 value=clean((request.get_json(silent=True) or {}).get('key'))
 ok,msg=save_secret(provider,value);return jsonify({'ok':ok,'message':msg,'status':key_status().get(provider,{})}),200 if ok else 400
@app.post('/api/investigate')
def investigate():
 d=request.form;n=clean(d.get('name'))
 if not n:return jsonify({'error':'Name / search term is required.'}),400
 if d.get('authorized')!='on':return jsonify({'error':'Confirm authorized public-source use.'}),400
 t={k:clean(d.get(k)) for k in ['name','location','email','phone','username']}
 try:t['social_accounts']=json.loads(d.get('social_accounts') or '[]')
 except Exception:t['social_accounts']=[]
 t['social_accounts']=[{'platform':clean(x.get('platform')),'username':clean(x.get('username'))} for x in t['social_accounts'] if isinstance(x,dict) and clean(x.get('username'))][:20]
 results,health=run(t)
 cats={k:[] for k in ['all','social','web','news_blogs','images','videos']};cats['all']=results
 for x in results:cats.setdefault(x.get('category','web'),[]).append(x)
 case_id=cid(n)
 profile=build_profile(t,results)
 payload={'case_id':case_id,'subject':n,'created':datetime.now().isoformat(),'status':f'Completed · {len(results)} unique public leads','collectors':health,'categories':cats,'candidates':results,'profile':profile,'notice':'Public-source leads only. Review and exclude false positives before treating correlations as identity evidence.'}
 CASES[case_id]={'target':t,'payload':payload,'excluded':set()}
 return jsonify(payload)
if __name__=='__main__':app.run(host='127.0.0.1',port=8080,debug=True)
