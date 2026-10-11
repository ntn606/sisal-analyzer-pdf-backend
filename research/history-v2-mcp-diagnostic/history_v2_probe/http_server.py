"""Authenticated cache-only ASGI Streamable HTTP; mcp==1.30.0.

Static Bearer header clients are supported. This is NOT an OAuth issuer.
Public healthcheck is minimal and restricted to configured Host/Origin.
"""
from dataclasses import dataclass,field
import asyncio,hashlib,hmac,json,os,re,importlib.metadata
from typing import Any
from urllib.parse import urlsplit
from pydantic import TypeAdapter
from mcp import types
from mcp.server.transport_security import TransportSecuritySettings
from starlette.responses import JSONResponse
from .mcp_server import create_server
from .revisions import RevisionStore,RevisionProbe

CLIENT_REQUEST=TypeAdapter(types.ClientRequest)
CLIENT_NOTIFICATION=TypeAdapter(types.ClientNotification)

@dataclass(frozen=True)
class HTTPConfig:
    token:str=field(repr=False)
    hosts:tuple[str,...]=()
    origins:tuple[str,...]=()
    health_hosts:tuple[str,...]=('healthcheck.railway.app',)
    max_body:int=16_384
    max_concurrency:int=4
    timeout_seconds:float=20
    def __post_init__(self):
        if not isinstance(self.token,str) or not re.fullmatch(r'[A-Za-z0-9_-]{43,256}',self.token):raise ValueError('invalid_http_configuration')
        if not self.hosts or any(not re.fullmatch(r'(?:[a-z0-9](?:[a-z0-9.-]*[a-z0-9])?)(?::[1-9][0-9]{0,4})?',h) or '*' in h for h in (*self.hosts,*self.health_hosts)):
            raise ValueError('invalid_http_configuration')
        for origin in self.origins:
            parsed=urlsplit(origin)
            if parsed.scheme not in ('https','http') or parsed.netloc not in self.hosts or parsed.path or parsed.query or parsed.fragment or parsed.username or (parsed.scheme=='http' and parsed.hostname not in ('localhost','127.0.0.1')):
                raise ValueError('invalid_http_configuration')
        if not 1024<=self.max_body<=65536 or not 1<=self.max_concurrency<=16 or not 1<=self.timeout_seconds<=60:
            raise ValueError('invalid_http_configuration')
    @classmethod
    def from_env(cls):
        split=lambda n:tuple(x.strip() for x in os.environ.get(n,'').split(',') if x.strip())
        return cls(token=os.environ.get('HISTORY_V2_MCP_TOKEN',''),hosts=split('HISTORY_V2_ALLOWED_HOSTS'),origins=split('HISTORY_V2_ALLOWED_ORIGINS'))

class SecurityBoundary:
    """Bound bodies/concurrency before parsing; safe errors and aggregate counters.

No supplied paths, arguments, headers or exception messages enter logs/metrics.
Host and Origin checks precede SDK logging. Forwarded headers are never trusted.
"""
    def __init__(self,app,config,store):
        self.app,self.config,self.store=app,config,store
        self._token_digest=hashlib.sha256(config.token.encode()).digest()
        self.inflight=0;self.metrics={}
    async def reject(self,scope,receive,send,status,code,headers=None):
        self.metrics[code]=self.metrics.get(code,0)+1
        await JSONResponse({'error':code},status_code=status,headers={'Cache-Control':'no-store','X-Content-Type-Options':'nosniff',**(headers or {})})(scope,receive,send)
    async def __call__(self,scope,receive,send):
        if scope['type']!='http':return await self.app(scope,receive,send)
        headers={}
        for name,value in scope['headers']:
            key=name.lower()
            if key in headers:return await self.reject(scope,receive,send,400,'duplicate_header')
            headers[key]=value
        config=self.config;path=scope['path'];host=headers.get(b'host',b'').decode('latin1');origin=headers.get(b'origin')
        if path not in ('/mcp','/healthz') or scope.get('query_string'):
            return await self.reject(scope,receive,send,404,'route_not_found')
        allowed=config.hosts+(config.health_hosts if path=='/healthz' else ())
        if host not in allowed:return await self.reject(scope,receive,send,421,'host_not_allowed')
        if origin is not None and origin.decode('latin1') not in config.origins:
            return await self.reject(scope,receive,send,403,'origin_not_allowed')
        if path=='/healthz':
            if scope['method']!='GET':return await self.reject(scope,receive,send,405,'method_not_allowed')
            try:self.store.capture()
            except Exception:return await self.reject(scope,receive,send,503,'evidence_not_ready')
            return await JSONResponse({'status':'ok','diagnostic_only':True,'cache_only':True},headers={'Cache-Control':'no-store'})(scope,receive,send)
        auth=headers.get(b'authorization',b'')
        authorized=False
        if len(auth)<=263 and auth.startswith(b'Bearer '):
            authorized=hmac.compare_digest(hashlib.sha256(auth[7:]).digest(),self._token_digest)
        if not authorized:return await self.reject(scope,receive,send,401,'unauthorized',{'WWW-Authenticate':'Bearer'})
        if scope['method']!='POST':return await self.reject(scope,receive,send,405,'method_not_allowed')
        if headers.get(b'content-encoding',b'identity')!=b'identity':return await self.reject(scope,receive,send,415,'encoding_not_supported')
        if headers.get(b'content-type',b'').split(b';')[0].strip().lower()!=b'application/json':
            return await self.reject(scope,receive,send,415,'json_required')
        length=headers.get(b'content-length')
        if length is not None:
            if not re.fullmatch(rb'[0-9]{1,10}',length):return await self.reject(scope,receive,send,400,'invalid_content_length')
            if int(length)>config.max_body:return await self.reject(scope,receive,send,413,'request_too_large')
        # No queue; acquire before body ingestion. Same event loop, no await race.
        if self.inflight>=config.max_concurrency:
            return await self.reject(scope,receive,send,429,'concurrency_limit',{'Retry-After':'1'})
        self.inflight+=1;started=False
        async def safe_send(message):
            nonlocal started
            if message['type']=='http.response.start':
                started=True
                message={**message,'headers':[*message.get('headers',[]),(b'cache-control',b'no-store'),(b'x-content-type-options',b'nosniff')]}
            await send(message)
        try:
            async with asyncio.timeout(config.timeout_seconds):
                body=bytearray()
                while True:
                    message=await receive()
                    if message['type']=='http.disconnect':return
                    body.extend(message.get('body',b''))
                    if len(body)>config.max_body:return await self.reject(scope,receive,safe_send,413,'request_too_large')
                    if not message.get('more_body',False):break
                try:
                    from .service import strict_object
                    data=json.loads(body,object_pairs_hook=strict_object)
                    if not isinstance(data,dict) or data.get('jsonrpc')!='2.0':raise ValueError
                    method=data.get('method')
                    if method not in ('initialize','notifications/initialized','ping','tools/list','tools/call'):raise ValueError
                    if 'id' in data and not (type(data['id']) is int or isinstance(data['id'],str) and re.fullmatch('[a-zA-Z0-9_-]{1,64}',data['id'])):raise ValueError
                    adapter=CLIENT_REQUEST if 'id' in data else CLIENT_NOTIFICATION
                    adapter.validate_python(data)
                    if method=='tools/call':
                        params=data['params'];arguments=params['arguments']
                        if params['name']!='football_history_v2_probe' or set(arguments)!={'palinsesto','avvenimento','match_date'}:raise ValueError
                        if not all(isinstance(arguments[k],str) and re.fullmatch('[0-9]{1,20}',arguments[k]) for k in ('palinsesto','avvenimento')) or not isinstance(arguments['match_date'],str) or not re.fullmatch('[0-9]{4}-[0-9]{2}-[0-9]{2}',arguments['match_date']):raise ValueError
                    if method=='tools/list' and data.get('params',{}).get('cursor'):raise ValueError
                except Exception:return await self.reject(scope,receive,safe_send,400,'invalid_mcp_request')
                delivered=False
                async def replay():
                    nonlocal delivered
                    if not delivered:delivered=True;return {'type':'http.request','body':bytes(body),'more_body':False}
                    return await receive()
                await self.app(scope,replay,safe_send)
                self.metrics['completed']=self.metrics.get('completed',0)+1
        except TimeoutError:
            if not started:await self.reject(scope,receive,safe_send,504,'request_timeout')
        except Exception:
            if not started:await self.reject(scope,receive,safe_send,500,'internal_error')
        finally:self.inflight-=1

def create_http_app(config=None,store=None):
    if importlib.metadata.version('mcp')!='1.30.0':raise ValueError('unsupported_mcp_version')
    config=config or HTTPConfig.from_env()
    if store is None:
        revision_root=os.environ.get('HISTORY_V2_REVISION_ROOT')
        if not revision_root:raise ValueError('revision_root_required')
        store=RevisionStore(revision_root)
    store.capture()  # Fail closed before binding/listening, also without secret.
    server=create_server(service=RevisionProbe(store),host='0.0.0.0',streamable_http_path='/mcp',json_response=True,stateless_http=True,max_request_body_size=config.max_body,
        transport_security=TransportSecuritySettings(enable_dns_rebinding_protection=True,allowed_hosts=list(config.hosts),allowed_origins=list(config.origins)))
    return SecurityBoundary(server.streamable_http_app(),config,store)

def main():
    import uvicorn
    try:
        port=int(os.environ.get('PORT','8000'))
        if not 1<=port<=65535:raise ValueError
        app=create_http_app()
    except Exception:raise SystemExit('secure_http_startup_failed') from None
    # No request/header logs, trusted proxy headers disabled. TLS at service edge.
    uvicorn.run(app,host='0.0.0.0',port=port,workers=1,access_log=False,log_level='critical',proxy_headers=False,timeout_keep_alive=5,limit_concurrency=32)
if __name__=='__main__':main()
