"""Conservative publication scanner. Report rule/path only, never matched values.

Known patterns plus contextual assignments; not a guarantee against unknown
formats. HTML excerpts additionally use structural allowlisting.
"""
import html,re
from urllib.parse import unquote
PATTERNS={
    'private_key':r'-----BEGIN (?:[A-Z ]+ )?PRIVATE KEY-----',
    'jwt':r'\beyJ[A-Za-z0-9_-]{8,}\.[A-Za-z0-9_-]{8,}\.[A-Za-z0-9_-]{8,}',
    'github_token':r'\b(?:gh[pousr]_[A-Za-z0-9]{20,}|github_pat_[A-Za-z0-9_]{30,})\b',
    'aws_access_id':r'\b(?:AKIA|ASIA)[A-Z0-9]{16}\b',
    'cloud_key':r'\b(?:AIza[A-Za-z0-9_-]{30,}|sk-(?:proj-)?[A-Za-z0-9_-]{24,}|xox[baprs]-[A-Za-z0-9-]{20,})\b',
    'azure_function_key':r'(?<![A-Za-z0-9_-])[A-Za-z0-9_-]{40,256}AZFu[A-Za-z0-9_-]{0,32}',
    'bearer_value':r'(?i)\bbearer\s+[A-Za-z0-9_./+=-]{20,}',
    'credential_url':r'(?i)https?://[^\s/<>"\']+:[^\s/@<>"\']+@',
    'credential_assignment':r'''(?ix)(?:["']?\b(?:api[_-]?key|access[_-]?token|auth[_-]?token|client[_-]?secret|password|secret[_-]?key|x-auth-token|x-apisports-key|authorization|sas[_-]?token)["']?)\s*[:=]\s*["']?[A-Za-z0-9_./+%=-]{20,}''',
    'credential_query':r'(?i)[?&](?:code|sig|signature|token|key|api_key|access_token|auth|password|secret|credential)=[^\s<>"\'&]{8,}',
}
COMPILED={rule:re.compile(pattern) for rule,pattern in PATTERNS.items()}
def findings(raw):
    if isinstance(raw,bytes):value=raw.decode('utf-8',errors='replace')
    else:value=raw
    variants={value,html.unescape(value),unquote(html.unescape(value))}
    # Dedupe decoded forms and bound Azure runs; scanning binary PDF streams
    # must not introduce quadratic backtracking on long encoded text.
    return sorted({rule for rule,pattern in COMPILED.items() if any(pattern.search(v) for v in variants)})

from html.parser import HTMLParser
PDF_URLS=[('https://landing.sisal.it/volantini/Scommesse_Sport/Quote/'+name).encode() for name in ('calcio%20base%20per%20data.pdf','calcio%20base%20per%20manifestazione.pdf','calcio%20base%20per%20manifestazione%20TOP.pdf')]
def validate_pdf_excerpt(result):
 # Preserve exact bytes only after structural allowlisting. Unknown attributes,
 # nested markup, encoded href variants and arbitrary text can carry secrets.
 class Anchor(HTMLParser):
  def __init__(self):super().__init__(convert_charrefs=True);self.tags=[];self.text=[];self.href=None
  def handle_starttag(self,tag,attrs):
   if tag!='a' or self.tags or len(attrs)!=len(dict(attrs)) or set(dict(attrs))-{'href','target'}:raise ValueError('unexpected_sensitive_html_fragment')
   attributes=dict(attrs)
   if attributes.get('href','').encode() not in PDF_URLS or attributes.get('target','_blank')!='_blank':raise ValueError('unexpected_sensitive_html_fragment')
   self.href=attributes['href'];self.tags.append('open')
  def handle_endtag(self,tag):
   if tag!='a' or self.tags!=['open']:raise ValueError('unexpected_sensitive_html_fragment')
   self.tags.append('closed')
  def handle_data(self,data):self.text.append(data)
  def handle_comment(self,data):raise ValueError('unexpected_sensitive_html_fragment')
 labels=('Calcio Base per Data','Calcio Base per Manifestazione','Calcio Base per Manifestazione TOP')
 seen=set()
 anchors=re.findall(rb'<a\b[^>]*>.*?</a\s*>',result,re.I|re.S)
 if len(anchors)!=3 or b'\n'.join(anchors)+b'\n'!=result:raise ValueError('unexpected_sensitive_html_fragment')
 for anchor in anchors:
  parser=Anchor();parser.feed(anchor.decode('utf-8'));parser.close()
  # A generic document label contains no metadata. This helper alone does
  # not certify authenticity; reviewed provider/PDF evidence is also required.
  if parser.tags!=['open','closed'] or ''.join(parser.text).strip() not in (*labels,'document') or parser.href in seen or findings(anchor):raise ValueError('unexpected_sensitive_html_fragment')
  seen.add(parser.href)
 return result
