"""Web UI siswa: backup/restore MikroTik ke folder sendiri.  python server.py

Nama siswa dan router diambil dari .env (NAMA_SISWA, MT_HOST, MT_USER, MT_PASS).
"""
import contextlib
import html
import io
import urllib.parse
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from string import Template

import mikrotik as m

PORT = int(m.E.get("PORT", 3000))
PAGE = Template(open(f"{m.DIR}/index.html", encoding="utf-8").read())
last_log = ""
esc = html.escape


def render():
    files = []
    for o in (m.objects() if m.NAMA else []):
        fname = o["Key"].rsplit("/", 1)[-1]
        restore = ""
        if fname.endswith(m.EXTS):
            warn = ("Konfigurasi router akan ditimpa dan router reboot." if fname.endswith(".backup") else
                    "Router akan di-RESET kosong (user tetap), reboot, lalu menjalankan file ini.")
            restore = (f'<form method="post" action="/restore" onsubmit="return confirm(\'Restore {esc(fname)} ke router? '
                       f'{warn}\')"><input type="hidden" name="file" value="{esc(fname)}">'
                       f'<button>Restore</button></form>')
        files.append(f'<tr><td>{esc(fname)}</td><td>{o["Size"] / 1024:.1f} KB</td>'
                     f'<td>{o["LastModified"].astimezone():%Y-%m-%d %H:%M}</td><td>{restore}</td></tr>')

    return PAGE.substitute(
        nama=esc(m.NAMA or "(NAMA_SISWA belum diisi di .env)"),
        router=esc(f'{m.E.get("MT_USER", "")}@{m.E.get("MT_HOST", "")}'),
        log=esc(last_log),
        file_rows="".join(files) or '<tr><td colspan="4">Belum ada backup</td></tr>',
    )


class Handler(BaseHTTPRequestHandler):
    def send(self, code, body, ctype="text/html; charset=utf-8", headers=()):
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        for k, v in headers:
            self.send_header(k, v)
        self.end_headers()
        self.wfile.write(body.encode())

    def do_GET(self):
        if self.path != "/":
            return self.send(404, "not found", "text/plain")
        try:
            self.send(200, render())
        except Exception as e:
            self.send(500, f"Gagal membaca bucket: {e}", "text/plain; charset=utf-8")

    def do_POST(self):
        global last_log
        # tolak POST dari website lain (CSRF), hanya halaman ini sendiri
        if self.headers.get("Origin") != f"http://{self.headers.get('Host')}":
            return self.send(403, "forbidden", "text/plain")
        form = urllib.parse.parse_qs(self.rfile.read(int(self.headers.get("Content-Length", 0))).decode())
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            try:
                if self.path == "/backup":
                    m.backup(m.router_from_env())
                elif self.path == "/restore":
                    m.restore(form.get("file", [""])[0], m.router_from_env())
                else:
                    return self.send(404, "not found", "text/plain")
            except Exception as e:
                print(f"ERROR: {e}")
        last_log = buf.getvalue()
        self.send(303, "", headers=[("Location", "/")])


if __name__ == "__main__":
    print(f"Buka http://localhost:{PORT}")
    try:
        ThreadingHTTPServer(("127.0.0.1", PORT), Handler).serve_forever()
    except KeyboardInterrupt:
        print("Server dihentikan")
