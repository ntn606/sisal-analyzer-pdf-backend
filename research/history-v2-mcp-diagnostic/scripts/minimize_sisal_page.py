"""Retain exact PDF anchor fragments, never full HTML with embedded service keys."""
from pathlib import Path
from datetime import datetime,timezone
import hashlib,json,re,ssl,urllib.request
import sys
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from history_v2_probe.publication_safety import validate_pdf_excerpt
PAGE='https://www.sisal.it/scommesse-matchpoint/foglio-quote'
PDF_URLS=[('https://landing.sisal.it/volantini/Scommesse_Sport/Quote/'+name).encode() for name in ('calcio%20base%20per%20data.pdf','calcio%20base%20per%20manifestazione.pdf','calcio%20base%20per%20manifestazione%20TOP.pdf')]
def retain_anchors(raw):
 anchors=[m.group() for m in re.finditer(rb'<a\b[^>]*>.*?</a\s*>',raw,re.I|re.S) if any(url in m.group() for url in PDF_URLS)]
 if len(anchors)!=3 or not all(any(url in anchor for anchor in anchors) for url in PDF_URLS):raise ValueError('official_pdf_links_missing_or_ambiguous')
 result=b'\n'.join(anchors)+b'\n'
 validate_pdf_excerpt(result)
 return result
class NoRedirect(urllib.request.HTTPRedirectHandler):
 def redirect_request(self,*args,**kwargs):return None

def get_page_excerpt(directory):
 directory=Path(directory);path=directory/'sisal-page-excerpt.html';metadata=directory/'sisal-page-excerpt.html.meta.json'
 if metadata.exists():return json.loads(metadata.read_text())
 now=lambda:datetime.now(timezone.utc).isoformat()
 meta={'source':PAGE,'request_started_at':now(),'http_status':None,'tls_verification_enabled':True,'state':'unavailable','quota':{}}
 try:
  opener=urllib.request.build_opener(NoRedirect(),urllib.request.HTTPSHandler(context=ssl.create_default_context()))
  with opener.open(urllib.request.Request(PAGE,headers={'Accept':'text/html'}),timeout=25) as response:
   meta.update(http_status=response.status,content_type=response.headers.get_content_type())
   raw=response.read(5_000_001)
  if len(raw)>5_000_000 or meta['content_type']!='text/html':raise ValueError('invalid_html_response')
  excerpt=retain_anchors(raw);path.write_bytes(excerpt)
  meta.update(state='retrieved',retention='exact_original_anchor_excerpt',source_document_sha256=hashlib.sha256(raw).hexdigest(),source_document_bytes=len(raw),retained_sha256=hashlib.sha256(excerpt).hexdigest(),bytes=len(excerpt))
 except Exception:meta.update(state='technical_error',error_category='official_page_unavailable_or_invalid')
 meta['response_completed_at']=now();metadata.write_text(json.dumps(meta,indent=2)+'\n');return meta
