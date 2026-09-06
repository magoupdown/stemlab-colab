"""Servidor local de desenvolvimento: serve app.html com uma ponte HTTP que imita
google.colab.kernel.invokeFunction, chamando o backend real.
Use STEMLAB_MOCK=1 para simular a separação sem GPU/modelos (filtros do ffmpeg)."""
import sys, os, json, http.server, traceback
HERE = os.path.dirname(os.path.abspath(__file__))
src = open(os.path.join(HERE, 'backend.py'), encoding='utf-8').read().replace(
    "'/content/stemlab'", repr(os.path.join(HERE, 'stemlab_test').replace('\\', '/')))
ns = {'USER_EMAIL': 'emerson.teste@gmail.com'}
exec(compile(src, 'backend.py', 'exec'), ns)

BRIDGE = """<script>
window.__mockApi = async function(name, ...args){
  const r = await fetch('/api/' + name, {method:'POST', headers:{'Content-Type':'application/json'}, body: JSON.stringify(args)});
  return r.json();
};
</script>
"""

class H(http.server.BaseHTTPRequestHandler):
    def log_message(self, *a): pass
    def _send(self, code, body, ctype='text/html; charset=utf-8'):
        self.send_response(code); self.send_header('Content-Type', ctype); self.send_header('Content-Length', str(len(body))); self.end_headers(); self.wfile.write(body)
    def do_GET(self):
        if self.path in ('/', '/index.html'):
            html = open(os.path.join(HERE, 'app.html'), encoding='utf-8').read()
            page = '<!doctype html><html lang="pt-BR"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1"><title>StemLab dev</title></head><body style="margin:0;background:#fff;padding:16px">' + BRIDGE + html + '</body></html>'
            return self._send(200, page.encode('utf-8'))
        self._send(404, b'not found')
    def do_POST(self):
        n = int(self.headers.get('Content-Length') or 0)
        args = json.loads(self.rfile.read(n) or b'[]')
        name = self.path.split('/api/')[-1]
        fn = ns.get('cb_' + name)
        if not fn: return self._send(404, json.dumps({'ok': False, 'error': 'no such api ' + name}).encode(), 'application/json')
        try:
            res = fn(*args).data
        except Exception as e:
            res = {'ok': False, 'error': f'{e}\n{traceback.format_exc()}'}
        self._send(200, json.dumps(res, ensure_ascii=False).encode('utf-8'), 'application/json; charset=utf-8')

if __name__ == '__main__':
    port = int(sys.argv[1]) if len(sys.argv) > 1 else 8791
    print(f'dev server on http://127.0.0.1:{port}  (file server on {ns["FILE_PORT"]}, mock={ns["MOCK"]})', flush=True)
    http.server.ThreadingHTTPServer(('127.0.0.1', port), H).serve_forever()
