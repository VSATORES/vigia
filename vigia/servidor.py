"""Serve o painel em http://127.0.0.1:<porta> e recebe as ações da página.

GET  /                         aba Aprovação (um slide por pedido; é a tela principal)
GET  /painel                   painel dos agentes (gerado em segundo plano quando passa de 60 s)
GET  /api/pedidos              pedidos pendentes + cartões de saúde dos agentes
POST /api/pedido/<ag>/<id>/<d> aprovar | recusar | adiar | outra  (corpo: {"opcao":0|1, "texto":"...", "horas":1})
GET  /api/anexos/<ag>/<id>     anexos buscados na hora pelo resolvedor do pedido (cache 6 h)
GET  /midia/<ag>/<arquivo>     anexo local do pedido (só dentro de pedidos/<ag>/)
GET  /api/execucoes/<id>       últimas execuções do item (com a saída, para o log ao vivo)
POST /api/<acao>/<id>          rodar | investigar | visto | pausar | retomar
As rotas /api exigem o cabeçalho X-Vigia-Token (chave aleatória desta instalação, em dados/token) e só
respondem para 127.0.0.1. "rodar" só executa o comando que está no toml do agente.
"""
import http.server, json, os, re, secrets, threading, time
from urllib.parse import unquote

_trava = threading.Lock()


def token(geral):
    os.makedirs(geral["dados"], exist_ok=True)
    p = os.path.join(geral["dados"], "token")
    if not os.path.exists(p):
        open(p, "w").write(secrets.token_urlsafe(24))
        os.chmod(p, 0o600)
    return open(p).read().strip()


def servir(geral, gerar, caminho_config):
    from . import acoes, config, estado, pedidos
    import mimetypes
    saida, porta = geral["saida"], geral["porta"]
    tok = token(geral)

    def regerar():
        if _trava.acquire(blocking=False):
            try:
                gerar()
            except Exception as e:
                print("erro ao gerar:", e)
            finally:
                _trava.release()

    def contexto(id_):
        try:
            d = json.load(open(os.path.join(geral["dados"], "ultimo.json"), encoding="utf-8"))
            it = next((i for i in d["itens"] if i["k"] == id_), {})
            rods = [r[:3] for k in sorted(it.get("rodadas", {}), key=int)[:3] for r in it["rodadas"][k]]
            return {"nome": it.get("nome"), "st": it.get("st"), "motivo": it.get("motivo"), "acao": it.get("acao"), "rodadas": rods}
        except (OSError, ValueError, StopIteration):
            return {}

    def saude():
        try:
            d = json.load(open(os.path.join(geral["dados"], "ultimo.json"), encoding="utf-8"))
        except (OSError, ValueError):
            return []
        out = []
        for it in d.get("itens", []):
            if it.get("st") in ("er", "nr", "late") and not it.get("visto"):
                out.append({"id": "saude-" + it["k"], "agente": "_saude", "k": it["k"], "agente_nome": it.get("nome"),
                            "risco": "saude", "titulo": f"{it.get('nome')}: {it.get('motivo')}",
                            "contexto": re.sub("<[^>]+>", "", it.get("acao") or "")[:400],
                            "acoes": it.get("acoes", []), "ult": it.get("ult"), "st": it.get("st")})
        return out

    class H(http.server.BaseHTTPRequestHandler):
        def _json(self, codigo, obj):
            corpo = json.dumps(obj, ensure_ascii=False, default=str).encode()
            self.send_response(codigo)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            self.wfile.write(corpo)

        def _autorizado(self):
            host = (self.headers.get("Host") or "").split(":")[0]
            return host in ("127.0.0.1", "localhost") and secrets.compare_digest(self.headers.get("X-Vigia-Token", ""), tok)

        def do_GET(self):
            rota = self.path.split("?")[0]
            m = re.fullmatch(r"/api/execucoes/([\w.-]+)", rota)
            if m:
                if not self._autorizado():
                    return self._json(403, {"erro": "sem permissão"})
                return self._json(200, {"execucoes": acoes.execucoes(geral, m.group(1), 5)})
            if rota == "/api/pedidos":
                if not self._autorizado():
                    return self._json(403, {"erro": "sem permissão"})
                _, ags, _ = config.carregar(caminho_config)
                _, prob = pedidos.ler(geral)
                return self._json(200, {"itens": pedidos.para_pagina(geral, ags, saude()),
                                        "resumo": pedidos.resumo(geral), "problemas": prob[:20],
                                        "fontes": geral.get("aprovacao", {}).get("fontes", {})})
            ma = re.fullmatch(r"/api/anexos/([\w.-]+)/([\w.-]+)", rota)
            if ma:
                if not self._autorizado():
                    return self._json(403, {"erro": "sem permissão"})
                try:
                    return self._json(200, {"anexos": pedidos.anexos(geral, ma.group(1), ma.group(2))})
                except LookupError as e:
                    return self._json(404, {"erro": str(e)})
                except PermissionError as e:
                    return self._json(403, {"erro": str(e)})
                except Exception as e:  # noqa: BLE001 — resolvedor externo
                    return self._json(502, {"erro": str(e)[:300]})
            m = re.fullmatch(r"/midia/([\w.-]+)/([\w./-]+)", rota)
            if m:
                arq = pedidos.midia_segura(geral, m.group(1), unquote(m.group(2)))
                if not arq:
                    self.send_response(404)
                    self.end_headers()
                    return
                corpo = open(arq, "rb").read()
                self.send_response(200)
                self.send_header("Content-Type", mimetypes.guess_type(arq)[0] or "application/octet-stream")
                self.send_header("Cache-Control", "private, max-age=300")
                self.end_headers()
                self.wfile.write(corpo)
                return
            if rota in ("/", "/aprovacao"):
                html = open(os.path.join(os.path.dirname(__file__), "pagina", "aprovacao.html"), encoding="utf-8").read()
                html = html.replace("const API=null;", "const API=" + json.dumps({"token": tok}) + ";", 1)
                corpo = html.encode()
                self.send_response(200)
                self.send_header("Content-Type", "text/html; charset=utf-8")
                self.send_header("Cache-Control", "no-store")
                self.end_headers()
                self.wfile.write(corpo)
                return
            if rota not in ("/painel", "/index.html"):
                self.send_response(404)
                self.end_headers()
                return
            if not os.path.exists(saida):
                regerar()
            elif time.time() - os.path.getmtime(saida) > 60:
                threading.Thread(target=regerar, daemon=True).start()
            try:
                html = open(saida, encoding="utf-8").read()
            except OSError as e:
                html = f"<h1>Painel ainda não foi gerado</h1><pre>{e}</pre>"
            # só a página servida aqui ganha os botões; a cópia em arquivo continua só leitura
            html = html.replace("const API=null;", "const API=" + json.dumps({"token": tok}) + ";", 1)
            corpo = html.encode()
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            self.wfile.write(corpo)

        def do_POST(self):
            mp = re.fullmatch(r"/api/pedido/([\w.-]+)/([\w.-]+)/(aprovar|recusar|adiar|outra)", self.path.split("?")[0])
            if mp:
                if not self._autorizado():
                    return self._json(403, {"erro": "sem permissão"})
                tam = int(self.headers.get("Content-Length") or 0)
                try:
                    corpo = json.loads(self.rfile.read(tam) or b"{}") if tam else {}
                except ValueError:
                    corpo = {}
                _, ags, _ = config.carregar(caminho_config)
                try:
                    ev = pedidos.decidir(geral, ags, mp.group(1), mp.group(2), mp.group(3), corpo.get("opcao", 0),
                                         corpo.get("texto"), corpo.get("horas", 1))
                except LookupError as e:
                    return self._json(404, {"erro": str(e)})
                except PermissionError as e:
                    return self._json(403, {"erro": str(e)})
                except (RuntimeError, ValueError) as e:
                    return self._json(409, {"erro": str(e)})
                return self._json(200, {"ok": True, "evento": ev})
            m = re.fullmatch(r"/api/(rodar|investigar|visto|pausar|retomar)/([\w.-]+)", self.path.split("?")[0])
            if not m:
                return self._json(404, {"erro": "rota desconhecida"})
            if not self._autorizado():
                return self._json(403, {"erro": "sem permissão"})
            acao, id_ = m.group(1), m.group(2)
            tam = int(self.headers.get("Content-Length") or 0)
            try:
                corpo = json.loads(self.rfile.read(tam) or b"{}") if tam else {}
            except ValueError:
                corpo = {}
            _, agentes, _ = config.carregar(caminho_config)
            ag = next((a for a in agentes if a["id"] == id_), None)
            if not ag:
                return self._json(404, {"erro": f"agente '{id_}' não existe na configuração"})
            try:
                if acao == "rodar":
                    info = acoes.rodar(geral, ag)
                    estado.registrar(geral, id_, "rodar", "rodada pedida no painel")
                elif acao == "investigar":
                    info = acoes.investigar(geral, ag, contexto(id_))
                    estado.registrar(geral, id_, "investigar", "investigação pedida no painel")
                else:
                    info = {}
                    estado.registrar(geral, id_, acao, unquote(str(corpo.get("texto", "")))[:200],
                                     st=contexto(id_).get("st", ""))
                    threading.Thread(target=regerar, daemon=True).start()
            except PermissionError as e:
                return self._json(403, {"erro": str(e)})
            except RuntimeError as e:
                return self._json(409, {"erro": str(e)})
            return self._json(200, {"ok": True, "acao": acao, "info": info})

        def log_message(self, *a):
            pass

    print(f"Vigia em http://127.0.0.1:{porta}")
    http.server.ThreadingHTTPServer(("127.0.0.1", porta), H).serve_forever()
