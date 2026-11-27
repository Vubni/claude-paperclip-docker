import json
from pathlib import Path
import shutil
import socket
import subprocess
import tempfile
import time
import uuid

GATEWAY = """
import asyncio, gzip, json, ssl, time
from pathlib import Path
from gateway import CountryDB, Gateway

class SyntheticGateway(Gateway):
    async def fetch(self, url, limit, timeout=8, headers=()):
        if not url.startswith('https://cloudflare-dns.com/dns-query?'):
            raise AssertionError()
        return json.dumps({'Status':0,'Answer':[{'type':1,'data':'1.1.1.1'}]}).encode()

    async def monitor(self):
        await asyncio.Future()

async def upstream(reader, writer):
    try:
        request = await reader.readuntil(b'\\r\\n\\r\\n')
        if request.split(b'\\r\\n', 1)[0] != b'CONNECT 1.1.1.1:443 HTTP/1.1':
            return
        writer.write(b'HTTP/1.1 200 OK\\r\\n\\r\\n')
        await writer.drain()
        while data := await reader.read(1024):
            writer.write(data)
            await writer.drain()
    finally:
        writer.close()

async def main():
    server_tls = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
    server_tls.load_cert_chain('/test/cert.pem','/test/key.pem')
    fixture = await asyncio.start_server(upstream, '127.0.0.1', 8443, ssl=server_tls)
    policy = {'proxy_host':'upstream.test','proxy_ipv4':'127.0.0.1','proxy_port':8443,'allow_hosts':['allowed.test']}
    gateway = SyntheticGateway(policy, 'workload', 8000)
    gateway.tls = ssl.create_default_context(cafile='/test/cert.pem')
    gateway.db = CountryDB(gzip.compress(b'1.1.1.1,1.1.1.1,US\\n'))
    gateway.until = time.monotonic() + 180
    Path('/tmp/mac-lease').write_text(str(gateway.until))
    async with fixture:
        await gateway.serve()

asyncio.run(main())
"""

PROBE = """
import socket, sys
from pathlib import Path

def tcp(host, port, timeout=2):
    return socket.create_connection((host, port), timeout)

def blocked(host, port):
    try:
        c = tcp(host, port)
    except OSError:
        return True
    c.close()
    return False

def emit(label, result):
    print(label, 'PASS' if result else 'FAIL', flush=True)

def dns_fixture(address):
    request = bytes.fromhex('beef01000001000000000000') + b'\\x10external-fixture\\x04test\\x00\\x00\\x01\\x00\\x01'
    with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as sock:
        sock.settimeout(1)
        try:
            sock.sendto(request, (address, 53))
            answer, _ = sock.recvfrom(512)
        except OSError:
            return False
        return answer[:2] == request[:2] and answer[6:8] == bytes.fromhex('0001')

if sys.argv[1] == 'dns-control':
    emit('uplink_dns_positive_control', dns_fixture(sys.argv[2]))
    sys.exit()

if sys.argv[1] == 'proxy':
    with tcp('region-gateway', 3128) as c:
        c.sendall(b'CONNECT allowed.test:443 HTTP/1.1\\r\\n\\r\\n')
        reply = c.recv(1024)
        assert reply.startswith(b'HTTP/1.1 200')
        c.sendall(b'echo')
        emit('proxy_tls_checked_and_payload_relays', c.recv(4) == b'echo')
        print('tunnel_active', flush=True)
        c.settimeout(15)
        try:
            emit('active_tunnel_revoked', c.recv(1) == b'')
        except ConnectionResetError:
            emit('active_tunnel_revoked', True)
        except TimeoutError:
            emit('active_tunnel_revoked', False)
    sys.exit()

for family, addr, port in (
    ('ipv4', sys.argv[2], int(sys.argv[4])),
    ('ipv6', sys.argv[3], int(sys.argv[4])),
):
    emit('direct_' + family + '_uplink_blocked', blocked(addr, port))

emit('ipv4_default_route_absent', not any(row.split()[1]=='00000000' for row in Path('/proc/net/route').read_text().splitlines()[1:]))
v6 = Path('/proc/net/ipv6_route')
emit('ipv6_default_route_absent', not v6.exists() or not any(row.split()[0]=='0'*32 and row.split()[1]=='00' and row.split()[-1]!='lo' for row in v6.read_text().splitlines()))
emit('host_alias_unreachable', blocked('host.docker.internal', int(sys.argv[5])))
try:
    socket.getaddrinfo('external-fixture.test',80)
    dns_denied = False
except socket.gaierror:
    dns_denied = True
emit('external_dns_name_unresolved', dns_denied)
emit('direct_uplink_dns_blocked', not dns_fixture(sys.argv[2]))
sys.exit()
"""

WORKLOAD = """
from http.server import BaseHTTPRequestHandler, HTTPServer
class Handler(BaseHTTPRequestHandler):
    def do_GET(self):
        self.send_response(200)
        self.end_headers()
        self.wfile.write(b'isolation-fixture-ok')
    def log_message(self, *args):
        pass
HTTPServer(('0.0.0.0',8000), Handler).serve_forever()
"""

UPLINK = """
import socket, threading

def dns():
    with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as server:
        server.bind(('0.0.0.0', 53))
        while True:
            request, peer = server.recvfrom(512)
            if request[12:] != b'\\x10external-fixture\\x04test\\x00\\x00\\x01\\x00\\x01':
                continue
            answer = request[:2] + bytes.fromhex('81800001000100000000') + request[12:] + bytes.fromhex('c00c000100010000001e0004c0000201')
            server.sendto(answer, peer)

threading.Thread(target=dns, daemon=True).start()
listener = socket.socket(socket.AF_INET6)
listener.setsockopt(socket.IPPROTO_IPV6, socket.IPV6_V6ONLY, 0)
listener.bind(('::',8123))
listener.listen()
while True:
    client, _ = listener.accept()
    client.close()
"""

def run():
    region = Path(__file__).resolve().parents[1] / 'region'
    project = 'regioncheck' + uuid.uuid4().hex[:10]
    with tempfile.TemporaryDirectory(prefix='codex-strict-fixture-') as root:
        folder = Path(root)
        for name in ('gateway.py','profile.py','countries.txt'):
            shutil.copyfile(region / name, folder / name)
        for name, code in [('fixture.py',GATEWAY),('probe.py',PROBE),('workload.py',WORKLOAD),('uplink.py',UPLINK)]:
            (folder / name).write_text(code)
        command = ['openssl','req','-new','-x509','-nodes','-newkey','rsa:2048','-days','1','-subj','/CN=upstream.test','-keyout',str(folder/'key.pem'),'-out',str(folder/'cert.pem')]
        subprocess.run(command,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL,check=True)
        image = 'python:3.12-slim-bookworm'
        base = {'image':image,'pull_policy':'never','read_only':True,'cap_drop':['ALL'],'security_opt':['no-new-privileges:true'],'volumes':[f'{folder}:/test:ro'],'tmpfs':['/tmp']}
        compose = {
          'services': {
            'workload':dict(base,command=['python','-B','/test/workload.py'],dns=['127.0.0.1'],networks=['workload']),
            'region-gateway':dict(base,command=['python','-B','/test/fixture.py'],ports=['127.0.0.1::8000'],networks={'uplink':{},'workload':{'aliases':['region-private']}}),
            'uplink-fixture':dict(base,command=['python','-B','/test/uplink.py'],networks=['uplink']),
          },
          'networks':{
            'workload':{'internal':True,'enable_ipv6':False,'driver_opts':{'com.docker.network.bridge.gateway_mode_ipv4':'isolated'}},
            'uplink':{'enable_ipv6':True},
          }
        }
        config = folder / 'compose.json'
        config.write_text(json.dumps(compose))
        dc = ['docker','compose','-p',project,'-f',str(config)]
        def docker(*args):
            result = subprocess.run([*dc,*args],stdout=subprocess.PIPE,stderr=subprocess.PIPE,text=True)
            if result.returncode:
                raise RuntimeError(f'compose step failed: {args[0]}')
            return result.stdout.strip()
        failures = []
        def record(message):
            for line in message.splitlines():
                if not line.endswith(' PASS'):
                    failures.append(line)
                print(line, flush=True)
        try:
            docker('up','-d','--no-build','--pull','never')
            bind = docker('port','region-gateway','8000')
            host, port = bind.rsplit(':',1)
            assert host == '127.0.0.1'
            record('host_bind_loopback_only PASS')
            identifier = docker('ps','-q','uplink-fixture')
            fmt = '{{range .NetworkSettings.Networks}}{{.IPAddress}} {{.GlobalIPv6Address}}{{end}}'
            addr4, addr6 = subprocess.check_output(['docker','inspect','--format',fmt,identifier],text=True,stderr=subprocess.DEVNULL).split()
            positive = False
            for _ in range(40):
                try:
                    with socket.create_connection((host,int(port)),timeout=0.3) as conn:
                        conn.sendall(b'GET / HTTP/1.0\r\n\r\n')
                        response = b''
                        while part := conn.recv(4096):
                            response += part
                        if response.endswith(b'isolation-fixture-ok'):
                            positive = True
                            break
                except OSError:
                    pass
                time.sleep(.15)
            record('host_loopback_ingress_reaches_workload ' + ('PASS' if positive else 'FAIL'))
            record(docker('exec','-T','region-gateway','python','-c',"import socket,sys; [socket.create_connection((h,8123),2).close() for h in sys.argv[1:]]; print('uplink_positive_control_ipv4_ipv6 PASS')",addr4,addr6))
            record(docker('exec','-T','region-gateway','python','-B','/test/probe.py','dns-control',addr4))
            record(docker('exec','-T','workload','python','-B','/test/probe.py','negative',addr4,addr6,'8123',port))
            with subprocess.Popen([*dc,'exec','-T','workload','python','-B','/test/probe.py','proxy'],stdout=subprocess.PIPE,stderr=subprocess.DEVNULL,text=True) as proc:
                for _ in range(2):
                    line = proc.stdout.readline().strip()
                    if line != 'tunnel_active':
                        record(line if line.startswith('proxy_tls_checked_and_payload_relays ') else 'proxy_setup FAIL')
                docker('exec','-T','region-gateway','python','-c',"from pathlib import Path; Path('/tmp/mac-lease').unlink()")
                remainder = proc.communicate(timeout=20)[0].strip()
                record(remainder if remainder.startswith('active_tunnel_revoked ') else 'active_tunnel_revoked FAIL')
            with socket.create_connection((host,int(port)),timeout=2) as conn:
                conn.sendall(b'GET / HTTP/1.0\r\n\r\n')
                try:
                    revoked = not conn.recv(1024)
                except ConnectionResetError:
                    revoked = True
                record('revoked_ingress_fails_closed ' + ('PASS' if revoked else 'FAIL'))
        finally:
            docker('down','--timeout','2')
            record('owned_fixture_cleanup PASS')
        if failures:
            raise SystemExit(1)

if __name__ == '__main__':
    run()
