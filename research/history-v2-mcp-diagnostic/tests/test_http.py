"""Real SDK over loopback HTTP, synthetic auth, saved real evidence. No egress."""
from contextlib import ExitStack
from datetime import datetime,timedelta,timezone
from pathlib import Path
import asyncio,json,secrets,socket,tempfile,unittest
from unittest.mock import patch
import httpx,uvicorn
from mcp import ClientSession
from mcp.client.streamable_http import streamable_http_client
from history_v2_probe.http_server import HTTPConfig,create_http_app,SecurityBoundary
from history_v2_probe.revisions import RevisionStore,publish
from test_revisions import ROOT,STAMP,source,mutate

class HTTPTests(unittest.IsolatedAsyncioTestCase):
    data_origin='real_saved_evidence_native_mcp_http_frozen_clock_synthetic_auth_no_provider_traffic'
    async def asyncSetUp(self):
        self.temp=tempfile.TemporaryDirectory();self.root=Path(self.temp.name)
        self.source=source(self.root/'source');self.store_path=self.root/'store';publish(self.source,self.store_path)
        self.clock=STAMP;self.store=RevisionStore(self.store_path,clock=lambda:self.clock)
        self.http_exchanges=[]
        self.token=secrets.token_urlsafe(32)
        sock=socket.socket();sock.bind(('127.0.0.1',0));sock.listen(128);sock.setblocking(False)
        self.port=sock.getsockname()[1];self.host=f'127.0.0.1:{self.port}';self.base=f'http://{self.host}'
        self.config=HTTPConfig(token=self.token,hosts=(self.host,'diagnostic.example.up.railway.app'),origins=(self.base,'https://diagnostic.example.up.railway.app'))
        self.app=create_http_app(self.config,self.store)
        self.server=uvicorn.Server(uvicorn.Config(self.app,log_level='critical',access_log=False,proxy_headers=False,lifespan='on'))
        self.task=asyncio.create_task(self.server.serve(sockets=[sock]))
        for _ in range(200):
            if self.server.started:break
            await asyncio.sleep(.01)
        self.assertTrue(self.server.started)
        self.egress=[];self.local_connections=0;original=socket.socket.connect
        def guarded(sock,address):
            if not isinstance(address,tuple) or address[0] not in ('127.0.0.1','::1'):
                self.egress.append('non_loopback');raise AssertionError('External network forbidden')
            self.local_connections+=1;return original(sock,address)
        self.guard=patch.object(socket.socket,'connect',guarded);self.guard.start()
        self.client=httpx.AsyncClient(base_url=self.base,trust_env=False,timeout=10)
    async def asyncTearDown(self):
        await self.client.aclose();self.server.should_exit=True
        await asyncio.wait_for(self.task,10);self.guard.stop()
        self.assertEqual(self.egress,[], 'No API-Football, football-data.org or Sisal sockets')
        if self.store._current:self.store._current.private_copy.cleanup()
        self.temp.cleanup()
    def auth(self,**extra):return {'Authorization':'Bearer '+self.token,**extra}
    def init(self):return {'jsonrpc':'2.0','id':1,'method':'initialize','params':{'protocolVersion':'2025-11-25','capabilities':{},'clientInfo':{'name':'offline-test','version':'1'}}}
    async def sdk_probe(self,avv='1885'):
        async def observed(response):
            self.http_exchanges.append({'method':response.request.method,'path':response.request.url.path,'http_status':response.status_code})
        async with httpx.AsyncClient(headers=self.auth(),trust_env=False,timeout=15,event_hooks={'response':[observed]}) as client:
            async with streamable_http_client(self.base+'/mcp',http_client=client) as (reader,writer,_):
                async with ClientSession(reader,writer) as session:
                    initialized=await session.initialize();tools=await session.list_tools()
                    self.assertEqual([t.name for t in tools.tools],['football_history_v2_probe'])
                    self.assertEqual(set(tools.tools[0].inputSchema['properties']),{'palinsesto','avvenimento','match_date'})
                    call=await session.call_tool('football_history_v2_probe',{'palinsesto':'36411','avvenimento':avv,'match_date':'2026-10-12'})
                    self.assertFalse(call.isError);return call.structuredContent
    async def test_real_sdk_authenticated_initialize_list_and_both_calls(self):
        outputs=[]
        for avv in ('1885','2282'):
            result=await self.sdk_probe(avv);self.assertEqual(result['status'],'diagnostic_available')
            self.assertTrue(result['diagnostic_only'])
            for flag in ('ready_for_analysis','ready_for_quant','statistics_usable_in_production'):self.assertFalse(result[flag])
            self.assertEqual([h['counts']['selected_results'] for h in result['histories'].values()],[5,5])
            self.assertEqual(result['provenance']['new_api_requests'],0);self.assertNotIn(self.token,json.dumps(result));outputs.append(result)
        self.assertGreater(self.local_connections,0)
        self.assertTrue(all(item['http_status'] in (200,202) for item in self.http_exchanges))
        report={'data_origin':self.data_origin,'transport':'mcp==1.30.0 Streamable HTTP over real loopback TCP','credentials':'synthetic_ephemeral_not_retained','http_exchanges':self.http_exchanges,'external_socket_attempts':self.egress,'verified_at_frozen_replay':STAMP.isoformat(),'outputs':outputs}
        (ROOT/'reports/http-authenticated-evidence.json').write_text(json.dumps(report,indent=2)+'\n')
    async def test_missing_and_wrong_token_return_401(self):
        for headers in ({},{'Authorization':'Bearer '+secrets.token_urlsafe(32)}):
            response=await self.client.post('/mcp',json=self.init(),headers=headers)
            self.assertEqual(response.status_code,401);self.assertEqual(response.json(),{'error':'unauthorized'});self.assertEqual(response.headers['www-authenticate'],'Bearer')
    async def test_real_sdk_unauthorized_initialize_fails(self):
        async with httpx.AsyncClient(trust_env=False,timeout=5) as client:
            with self.assertRaises(BaseExceptionGroup):
                async with streamable_http_client(self.base+'/mcp',http_client=client) as (reader,writer,_):
                    async with ClientSession(reader,writer) as session:await session.initialize()
    async def test_missing_secret_and_bad_allowlist_fail_before_listen(self):
        for token in ('','short'):
            with self.assertRaisesRegex(ValueError,'invalid_http_configuration'):HTTPConfig(token=token,hosts=(self.host,))
        with patch.dict('os.environ',{'HISTORY_V2_MCP_TOKEN':''},clear=False):
            with self.assertRaises(ValueError):create_http_app(store=self.store)
        for host in ('*.railway.app','diagnostic.example.up.railway.app.evil','user@domain','https://host'):
            # A syntactically valid counterfeit host only fails at request time;
            # configuration is operator-owned and cannot know domain ownership.
            if host.endswith('.evil'):continue
            with self.assertRaises(ValueError):HTTPConfig(token=self.token,hosts=(host,))
    async def test_dns_rebinding_hosts_rejected_including_forwarded_headers(self):
        for host in ('evil.example','diagnostic.example.up.railway.app.evil','healthcheck.railway.app',self.host+'@evil.example'):
            response=await self.client.post('/mcp',json=self.init(),headers=self.auth(Host=host,**{'X-Forwarded-Host':self.host}))
            self.assertEqual(response.status_code,421);self.assertNotIn(host,response.text)
        self.assertTrue(self.app.app.state is not None)
    async def test_origin_null_foreign_and_encoded_rejected(self):
        for origin in ('null','https://evil.example',self.base+'/','https://diagnostic.example.up.railway.app.evil'):
            response=await self.client.post('/mcp',json=self.init(),headers=self.auth(Origin=origin))
            self.assertEqual(response.status_code,403);self.assertNotIn(origin,response.text)
        response=await self.client.post('/mcp',json=self.init(),headers=self.auth(Origin=self.base,Accept='application/json, text/event-stream'))
        self.assertEqual(response.status_code,200)
    async def test_railway_health_host_health_only_and_no_token(self):
        response=await self.client.get('/healthz',headers={'Host':'healthcheck.railway.app'})
        self.assertEqual(response.status_code,200);self.assertEqual(set(response.json()),{'status','diagnostic_only','cache_only'})
        response=await self.client.get('/healthz',headers={'Host':'evil.example'})
        self.assertEqual(response.status_code,421)
        response=await self.client.get('/healthz',headers={'Host':'healthcheck.railway.app','Origin':'https://evil.example'})
        self.assertEqual(response.status_code,403)
    async def test_missing_revision_fail_start_and_health(self):
        with self.assertRaises(Exception):create_http_app(self.config,RevisionStore(self.root/'absent'))
        (self.store_path/'ACTIVE.json').write_text('{}')
        response=await self.client.get('/healthz');self.assertEqual(response.status_code,503);self.assertNotIn('Traceback',response.text)
    async def test_body_limit_and_encoding(self):
        for body,extra,code in ((b'x'*20000,{},413),(b'{}',{'Content-Encoding':'gzip'},415)):
            response=await self.client.post('/mcp',content=body,headers=self.auth(**{'Content-Type':'application/json',**extra}))
            self.assertEqual(response.status_code,code)
    async def test_chunked_body_limit(self):
        async def chunks():
            yield b'x'*10000;yield b'x'*10000
        response=await self.client.post('/mcp',content=chunks(),headers=self.auth(**{'Content-Type':'application/json'}))
        self.assertEqual(response.status_code,413)
    async def test_malformed_and_sensitive_arguments_not_echoed(self):
        sentinel='synthetic-sensitive-do-not-echo'
        for payload in ({'jsonrpc':'2.0','id':sentinel,'method':'evil'}, {'jsonrpc':'2.0','id':1,'method':'tools/call','params':{'name':'football_history_v2_probe','arguments':{'palinsesto':sentinel,'avvenimento':'1885','match_date':'2026-10-12'}}}):
            response=await self.client.post('/mcp',json=payload,headers=self.auth());self.assertEqual(response.status_code,400);self.assertNotIn(sentinel,response.text)
    async def test_query_token_cors_and_unknown_route_refused(self):
        for route in ('/mcp?token=synthetic','/mcp/','/metrics'):
            response=await self.client.post(route,json=self.init(),headers=self.auth());self.assertEqual(response.status_code,404)
        response=await self.client.options('/mcp',headers=self.auth(Origin=self.base));self.assertEqual(response.status_code,405)
    async def test_at_and_after_kickoff_real_sdk_blocks_history(self):
        for now in (datetime(2026,10,12,19,tzinfo=timezone.utc),datetime(2026,10,12,19,1,tzinfo=timezone.utc)):
            self.clock=now;result=await self.sdk_probe();self.assertEqual(result['status'],'temporal_unverified');self.assertEqual(result['histories'],{})
    async def test_real_sdk_stale_and_unknown_identity(self):
        result=await self.sdk_probe('9999');self.assertEqual(result['status'],'identity_unverified')
        self.clock=STAMP+timedelta(hours=2);result=await self.sdk_probe();self.assertEqual(result['status'],'source_stale')
    async def test_safe_internal_error_and_concurrency_limit(self):
        entered=asyncio.Event();release=asyncio.Event()
        async def slow(scope,receive,send):
            entered.set();await release.wait();raise RuntimeError('synthetic-sensitive-stack')
        boundary=SecurityBoundary(slow,HTTPConfig(token=self.token,hosts=('testserver',),max_concurrency=1),self.store)
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=boundary),base_url='http://testserver') as client:
            first=asyncio.create_task(client.post('/mcp',json=self.init(),headers=self.auth()));await entered.wait()
            denied=await client.post('/mcp',json=self.init(),headers=self.auth());self.assertEqual(denied.status_code,429);self.assertEqual(denied.headers['retry-after'],'1')
            release.set();failed=await first;self.assertEqual(failed.status_code,500);self.assertNotIn('synthetic-sensitive-stack',failed.text);self.assertEqual(boundary.inflight,0)
    async def test_body_timeout_is_safe(self):
        async def forever(scope,receive,send):await asyncio.Event().wait()
        boundary=SecurityBoundary(forever,HTTPConfig(token=self.token,hosts=('testserver',),timeout_seconds=1),self.store)
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=boundary),base_url='http://testserver') as client:
            response=await client.post('/mcp',json=self.init(),headers=self.auth());self.assertEqual(response.status_code,504);self.assertEqual(boundary.inflight,0)
    async def test_http_concurrent_calls_during_atomic_activation(self):
        import threading
        old=self.store.capture();entered=threading.Event();release=threading.Event();original=old.service.football_history_v2_probe
        def pause(*args):entered.set();release.wait(10);return original(*args)
        old.service.football_history_v2_probe=pause
        before_task=asyncio.create_task(self.sdk_probe())
        self.assertTrue(await asyncio.to_thread(entered.wait,10))
        mutate(self.source,'cases/coventry-newcastle/request-diagnostic.json',lambda x:x['football_data'].update(state='unavailable'))
        new_id=await asyncio.to_thread(publish,self.source,self.store_path)
        after=await self.sdk_probe();release.set();before=await before_task
        self.assertEqual(before['status'],'diagnostic_available');self.assertEqual(after['status'],'provider_unavailable')
        self.assertEqual(before['provenance']['catalog_revision'],old.revision_id);self.assertEqual(after['provenance']['catalog_revision'],new_id)
    async def test_duplicate_auth_headers_and_oversized_header(self):
        headers=[('Authorization','Bearer '+self.token),('Authorization','Bearer '+self.token)]
        response=await self.client.post('/mcp',json=self.init(),headers=headers)
        self.assertEqual(response.status_code,400);self.assertEqual(response.json(),{'error':'duplicate_header'})
        response=await self.client.post('/mcp',json=self.init(),headers={'Authorization':'Bearer '+'x'*300})
        self.assertEqual(response.status_code,401)
    async def test_token_never_appears_in_repr_or_counters(self):
        self.assertNotIn(self.token,repr(self.config))
        await self.client.post('/mcp',json=self.init(),headers={'Authorization':'Bearer '+secrets.token_urlsafe(32)})
        self.assertNotIn(self.token,json.dumps(self.app.metrics))
    async def test_entrypoint_port_bind_and_logging_contract(self):
        from history_v2_probe.http_server import main
        with patch.dict('os.environ',{'PORT':'9123'}),patch('history_v2_probe.http_server.create_http_app',return_value=self.app),patch('uvicorn.run') as run:
            main();self.assertEqual(run.call_args.kwargs['host'],'0.0.0.0');self.assertEqual(run.call_args.kwargs['port'],9123)
            self.assertFalse(run.call_args.kwargs['access_log']);self.assertFalse(run.call_args.kwargs['proxy_headers'])
        with patch.dict('os.environ',{'PORT':'invalid'}):
            with self.assertRaisesRegex(SystemExit,'secure_http_startup_failed'):main()
    async def test_unsupported_sdk_version_fail_closed(self):
        with patch('history_v2_probe.http_server.importlib.metadata.version',return_value='2.0.0'):
            with self.assertRaisesRegex(ValueError,'unsupported_mcp_version'):create_http_app(self.config,self.store)
    async def test_origin_and_host_config_strict(self):
        for origin in ('https://evil.example','null',self.base+'/',self.base+'?token=x','https://user@diagnostic.example.up.railway.app','http://diagnostic.example.up.railway.app'):
            with self.assertRaises(ValueError):HTTPConfig(token=self.token,hosts=self.config.hosts,origins=(origin,))
    async def test_sdk_security_settings_explicitly_enabled(self):
        from history_v2_probe.mcp_server import create_server
        with patch('history_v2_probe.http_server.create_server',wraps=create_server) as factory:
            app=create_http_app(self.config,self.store)
        settings=factory.call_args.kwargs['transport_security']
        self.assertTrue(settings.enable_dns_rebinding_protection);self.assertEqual(settings.allowed_hosts,list(self.config.hosts))
        self.assertNotIn('healthcheck.railway.app',settings.allowed_hosts)
