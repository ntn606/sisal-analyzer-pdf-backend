"""Instrument child Python test processes only; no production import path."""
import json,os,socket
_audit=os.environ.get('HISTORY_V2_OFFLINE_AUDIT')
if _audit:
    def record(code):
        fd=os.open(_audit,os.O_WRONLY|os.O_CREAT|os.O_APPEND,0o600)
        try:os.write(fd,(json.dumps({'event':code})+'\n').encode())
        finally:os.close(fd)
    record('guard_installed')
    def guard(function):
        def invoke(sock,address):
            if sock.family==socket.AF_UNIX:return function(sock,address)
            if not isinstance(address,tuple) or address[0] not in ('127.0.0.1','::1','localhost'):
                record('external_socket_denied');raise AssertionError('Child offline test forbids external sockets')
            return function(sock,address)
        return invoke
    socket.socket.connect=guard(socket.socket.connect);socket.socket.connect_ex=guard(socket.socket.connect_ex)
    _dns=socket.getaddrinfo
    def dns(host,*args,**kwargs):
        if host not in ('localhost','127.0.0.1','::1',None):record('external_dns_denied');raise AssertionError('Child offline test forbids external DNS')
        return _dns(host,*args,**kwargs)
    socket.getaddrinfo=dns
