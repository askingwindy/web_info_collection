"""TLS diagnostic regressions: mocked I/O and one local self-signed server."""
from email.message import Message
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
import ssl
import subprocess
import sys
import tempfile
import threading
import unittest
from unittest.mock import Mock, patch
from urllib.error import HTTPError, URLError
from urllib.request import ProxyHandler, Request, build_opener

REPO=Path(__file__).resolve().parents[3]
sys.path[:0]=[str(REPO/'projects/site-planner')]
from site_planner.pipeline import fetch_public
from site_planner.entry_access import fetch_status, RedirectBlocked
from webcollect.collect import verify_public_url


class FakeResponse:
    status=200
    url='https://example.org/'
    def __init__(self,body=b'<html></html>'):
        self.body=body;self.offset=0;self.reads=0
        self.headers=Message();self.headers['Content-Type']='text/html;charset=utf-8'
    def __enter__(self):return self
    def __exit__(self,*args):return False
    def read1(self,size):
        self.reads+=1;part=self.body[self.offset:self.offset+size];self.offset+=len(part);return part


class TLSFetchGuards(unittest.TestCase):
    def test_entry_get_uses_final_redirect_status_and_does_not_read_html(self):
        start, final = 'https://example.org/start','https://www.example.org/final'
        response=FakeResponse()
        response.geturl=lambda:final
        def opener(redirect):
            def follow(request, timeout):
                forwarded=redirect.redirect_request(request,None,302,'redirect',{},final)
                self.assertEqual((request.get_method(),forwarded.get_method()),('GET','GET'))
                if response.status==404:
                    raise HTTPError(final,404,'controlled missing',{},None)
                return response
            return Mock(open=follow)
        with patch('site_planner.pipeline.build_opener',side_effect=opener):
            for code in (200,404):
                response.status=code; metrics={}
                self.assertEqual(fetch_status(start,10,metrics,'real',None),(code,final))
                self.assertEqual(metrics['redirects'],[{'from':start,'to':final,'status':302}])
        self.assertEqual(response.reads,0)

    def test_entry_redirect_does_not_dispatch_to_an_unrelated_application(self):
        def opener(redirect):
            def follow(request, timeout):
                redirect.redirect_request(request,None,302,'redirect',{},'https://other.example.net/')
                self.fail('foreign redirect should stop before dispatch')
            return Mock(open=follow)
        with patch('site_planner.pipeline.build_opener',side_effect=opener):
            with self.assertRaises(RedirectBlocked): fetch_status('https://example.org/',10,{},'real',None)

    def test_initial_private_url_rejected_before_dispatch(self):
        with patch('site_planner.pipeline.build_opener') as opener:
            with self.assertRaises(ValueError):fetch_public('https://127.0.0.1/')
            opener.assert_not_called()

    def test_redirect_to_private_url_rejected_before_following(self):
        captured=[]
        def build(*handlers):
            captured.extend(handlers)
            return Mock(open=Mock(return_value=FakeResponse()))
        metrics={}
        with patch('site_planner.pipeline.build_opener',side_effect=build):
            fetch_public('https://example.org/',metrics=metrics)
        with self.assertRaises(ValueError):
            captured[0].redirect_request(Request('https://example.org/'),None,302,'Found',{},'https://10.0.0.1/secret')
        self.assertNotIn('redirects',metrics)

    def test_tls_eof_is_retained_without_hidden_retry(self):
        error=URLError(ssl.SSLEOFError(8,'controlled EOF'))
        opener=Mock();opener.open.side_effect=error;metrics={}
        with patch('site_planner.pipeline.build_opener',return_value=opener):
            with self.assertRaises(URLError) as caught:fetch_public('https://example.org/',metrics=metrics)
        self.assertIs(caught.exception,error)
        self.assertEqual(opener.open.call_count,1)
        self.assertNotIn('response_status',metrics)

    def test_oversized_html_rejected(self):
        response=FakeResponse(b'x'*2_000_001)
        with patch('site_planner.pipeline.build_opener',return_value=Mock(open=Mock(return_value=response))):
            with self.assertRaisesRegex(ValueError,'bounded HTML size'):fetch_public('https://example.org/')
        self.assertEqual(response.offset,2_000_001)

    def test_whole_fetch_deadline_prevents_body_read(self):
        response=FakeResponse()
        with patch('site_planner.pipeline.build_opener',return_value=Mock(open=Mock(return_value=response))), \
             patch('site_planner.pipeline.time.monotonic',side_effect=[0,2]):
            with self.assertRaisesRegex(TimeoutError,'total deadline'):fetch_public('https://example.org/',timeout=1)
        self.assertEqual(response.reads,0)

    def test_self_signed_certificate_is_rejected(self):
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp)
            subprocess.run(['openssl','req','-x509','-newkey','rsa:2048','-nodes','-keyout',str(root/'key.pem'),
                '-out',str(root/'cert.pem'),'-days','1','-subj','/CN=localhost'],check=True,capture_output=True)
            class Handler(BaseHTTPRequestHandler):
                def do_GET(self):
                    self.send_response(200);self.send_header('Content-Type','text/html');self.end_headers();self.wfile.write(b'<html>fixture</html>')
                def log_message(self,*args):pass
            server=ThreadingHTTPServer(('127.0.0.1',0),Handler)
            context=ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
            context.load_cert_chain(root/'cert.pem',root/'key.pem')
            server.socket=context.wrap_socket(server.socket,server_side=True)
            thread=threading.Thread(target=server.serve_forever,daemon=True);thread.start()
            uri=f'https://127.0.0.1:{server.server_port}/'
            def allow_fixture(value):
                if value==uri:return '127.0.0.1'
                return verify_public_url(value)
            try:
                with patch('site_planner.pipeline.verify_public_url',side_effect=allow_fixture), \
                     patch('site_planner.pipeline.build_opener',side_effect=lambda *handlers:build_opener(ProxyHandler({}),*handlers)):
                    with self.assertRaises(URLError) as caught:fetch_public(uri,timeout=3)
                self.assertIsInstance(caught.exception.reason,ssl.SSLCertVerificationError)
            finally:
                server.shutdown();server.server_close();thread.join()


if __name__=='__main__':unittest.main()
