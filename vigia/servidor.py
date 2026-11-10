"""Serve o painel em http://127.0.0.1:<porta>.
Responde na hora com a última versão gerada e, se ela tiver mais de 60 s, gera outra em segundo plano
(consultas a banco podem levar alguns segundos; a página nunca fica esperando)."""
import http.server, os, threading, time

_trava = threading.Lock()


def servir(geral, gerar):
    saida, porta = geral["saida"], geral["porta"]

    def regerar():
        if _trava.acquire(blocking=False):
            try:
                gerar()
            except Exception as e:
                print("erro ao gerar:", e)
            finally:
                _trava.release()

    class H(http.server.BaseHTTPRequestHandler):
        def do_GET(self):
            if self.path.split("?")[0] not in ("/", "/index.html"):
                self.send_response(404)
                self.end_headers()
                return
            if not os.path.exists(saida):
                regerar()
            elif time.time() - os.path.getmtime(saida) > 60:
                threading.Thread(target=regerar, daemon=True).start()
            try:
                corpo = open(saida, "rb").read()
            except OSError as e:
                corpo = f"<h1>Painel ainda não foi gerado</h1><pre>{e}</pre>".encode()
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            self.wfile.write(corpo)

        def log_message(self, *a):
            pass

    print(f"Vigia em http://127.0.0.1:{porta}")
    http.server.ThreadingHTTPServer(("127.0.0.1", porta), H).serve_forever()
