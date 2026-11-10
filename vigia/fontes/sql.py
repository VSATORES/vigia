"""Agentes que não têm log de rodada: o sinal é a tabela onde eles gravam o que fizeram.

No agente (.toml):
  fonte = "sql"
  [sql]
  conexao = "banco"            # nome em [conexoes] do vigia.toml
  por_dia = '''SELECT dia, n, erros, humano FROM ...'''      # obrigatório: 1 linha por dia
  eventos = '''SELECT quando, ok, texto FROM ... LIMIT 200''' # opcional: últimas gravações (detecta silêncio)
  alerta  = '''SELECT n, texto FROM ...'''                    # opcional: n > 0 = atenção agora (ex.: fila presa)
  entrada_por_dia = '''SELECT dia, n FROM ...'''             # opcional: trabalho que chegou; dia calado com entrada = falha
  [flag]                                                      # opcional: chave da flag no PostHog
  chave = "minha_flag"

Conexões suportadas em [conexoes.<nome>]:
  tipo = "mcp_http"   url, ferramenta, argumento, cabecalhos = {Nome = "$VARIAVEL"}
  tipo = "posthog"    host, projeto ("@current"), token = "$VARIAVEL"
  tipo = "arquivo"    caminho para um JSON {consulta: linhas} (demo e testes)
Credenciais SEMPRE por variável de ambiente ($NOME); nunca no arquivo.
"""
import datetime as dt, json, os, re, urllib.request

_cache_flags = {}
_sessoes = {}


def _env(v):
    if isinstance(v, str) and v.startswith("$"):
        return os.environ.get(v[1:], "")
    return v


def carregar_env(arquivo):
    """lê KEY=valor de um .env sem imprimir nada (para rodar fora do shell interativo)."""
    if not arquivo or not os.path.exists(arquivo):
        return
    for ln in open(arquivo, encoding="utf-8"):
        ln = ln.strip()
        if not ln or ln.startswith("#") or "=" not in ln:
            continue
        k, v = ln.removeprefix("export ").split("=", 1)
        os.environ.setdefault(k.strip(), v.strip().strip('"').strip("'"))


def _mcp_http(cx, sql):
    h = {"Content-Type": "application/json", "Accept": "application/json, text/event-stream",
         "User-Agent": "vigia/1"}
    for k, v in cx.get("cabecalhos", {}).items():
        h[k] = _env(v)

    def post(corpo, sid=None):
        hh = dict(h)
        if sid:
            hh["Mcp-Session-Id"] = sid
        req = urllib.request.Request(cx["url"], data=json.dumps(corpo).encode(), headers=hh, method="POST")
        with urllib.request.urlopen(req, timeout=int(cx.get("timeout", 120))) as r:
            sid = r.headers.get("Mcp-Session-Id") or sid
            txt = r.read().decode()
        msgs = [json.loads(txt)] if txt.lstrip().startswith("{") else [
            json.loads(l[5:]) for l in txt.splitlines() if l.startswith("data:") and l[5:].strip()]
        return msgs, sid

    sid = _sessoes.get(cx["url"])
    if not sid:
        _, sid = post({"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {
            "protocolVersion": "2025-03-26", "capabilities": {}, "clientInfo": {"name": "vigia", "version": "1"}}})
        try:
            post({"jsonrpc": "2.0", "method": "notifications/initialized"}, sid)
        except Exception:
            pass
        _sessoes[cx["url"]] = sid
    msgs, _ = post({"jsonrpc": "2.0", "id": 2, "method": "tools/call", "params": {
        "name": cx.get("ferramenta", "consultar_banco"), "arguments": {cx.get("argumento", "query"): sql}}}, sid)
    for m in msgs:
        if m.get("id") == 2:
            if "error" in m:
                raise RuntimeError(str(m["error"])[:300])
            res = m.get("result", {})
            txt = "".join(c.get("text", "") for c in res.get("content", []) if c.get("type") == "text")
            if res.get("isError") or txt.startswith(("ERRO", "Erro", "Error")):
                raise RuntimeError(txt[:300])
            try:
                return json.loads(txt)
            except json.JSONDecodeError:
                raise RuntimeError("resposta não é JSON: " + txt[:200])
    raise RuntimeError("sem resposta da ferramenta")


def _arquivo(cx, nome_consulta):
    d = json.load(open(cx["caminho"], encoding="utf-8"))
    return d.get(nome_consulta, [])


def consultar(geral, nome_cx, sql, chave):
    cx = geral["conexoes"][nome_cx]
    if cx.get("tipo") == "arquivo":
        base = geral["base"]
        cam = cx["caminho"] if os.path.isabs(cx["caminho"]) else os.path.join(base, cx["caminho"])
        return _arquivo({**cx, "caminho": cam}, chave)
    if cx.get("tipo") == "mcp_http":
        # o filtro de segurança do servidor recusa palavras como update/delete em qualquer lugar
        return _mcp_http(cx, sql)
    raise RuntimeError(f"conexão {nome_cx}: tipo '{cx.get('tipo')}' não suportado")


def flag_ligada(geral, chave):
    """True/False, ou None se não deu para ler (não inventa)."""
    cx = next((c for c in geral["conexoes"].values() if c.get("tipo") == "posthog"), None)
    if not cx or not chave:
        return None
    if cx.get("tipo") == "posthog" and cx.get("arquivo"):
        d = json.load(open(os.path.join(geral["base"], cx["arquivo"]), encoding="utf-8"))
        return d.get(chave)
    if not _cache_flags:
        tok = _env(cx.get("token", ""))
        if not tok:
            return None
        auth = tok if tok.lower().startswith("bearer") else "Bearer " + tok
        url = f"{cx.get('host', 'https://us.posthog.com')}/api/projects/{cx.get('projeto', '@current')}/feature_flags/?limit=500"
        try:
            while url:
                d = json.load(urllib.request.urlopen(urllib.request.Request(url, headers={"Authorization": auth}), timeout=30))
                for f in d.get("results", []):
                    grupos = (f.get("filters") or {}).get("groups") or []
                    rollout = any((g.get("rollout_percentage") is None or g.get("rollout_percentage", 0) > 0) for g in grupos)
                    _cache_flags[f["key"]] = bool(f.get("active")) and (rollout or not grupos)
                url = d.get("next")
        except Exception:
            return None
    return _cache_flags.get(chave)


def _data(v):
    if v is None:
        return None
    if isinstance(v, (dt.date, dt.datetime)):
        return v
    s = str(v).replace("Z", "+00:00")
    try:
        d = dt.datetime.fromisoformat(s)
    except ValueError:
        try:
            return dt.date.fromisoformat(s[:10])
        except ValueError:
            return None
    if d.tzinfo:
        d = d.astimezone().replace(tzinfo=None)
    return d


def _int(v):
    try:
        return int(float(v))
    except (TypeError, ValueError):
        return 0


def coletar(agente, geral, agora):
    s = agente["sql"]
    out = {"dias": {}, "eventos": [], "alerta": None, "flag": None, "erro_fonte": None}
    try:
        for ln in consultar(geral, s["conexao"], s["por_dia"], f"{agente['id']}.por_dia") or []:
            try:  # a coluna dia é DATA: pega AAAA-MM-DD como veio, sem converter fuso
                d = dt.date.fromisoformat(str(ln.get("dia"))[:10])
            except ValueError:
                continue
            out["dias"][d.isoformat()] = {"n": _int(ln.get("n")), "erros": _int(ln.get("erros")),
                                          "humano": _int(ln.get("humano")), "ultima": _data(ln.get("ultima"))}
        if s.get("entrada_por_dia"):  # quanto trabalho chegou por dia (prova de que calar foi falha)
            out["entrada"] = {}
            for ln in consultar(geral, s["conexao"], s["entrada_por_dia"], f"{agente['id']}.entrada") or []:
                try:
                    out["entrada"][dt.date.fromisoformat(str(ln.get("dia"))[:10]).isoformat()] = _int(ln.get("n"))
                except ValueError:
                    pass
        if s.get("eventos"):
            for ln in consultar(geral, s["conexao"], s["eventos"], f"{agente['id']}.eventos") or []:
                q = _data(ln.get("quando"))
                if isinstance(q, dt.datetime):
                    ok = ln.get("ok")
                    out["eventos"].append({"quando": q, "ok": ok in (True, 1, "t", "true", "True", None),
                                           "texto": str(ln.get("texto") or "")[:200]})
            out["eventos"].sort(key=lambda e: e["quando"])
        if s.get("alerta"):
            linhas = consultar(geral, s["conexao"], s["alerta"], f"{agente['id']}.alerta") or []
            if linhas and _int(linhas[0].get("n")) > 0:
                out["alerta"] = {"n": _int(linhas[0].get("n")), "texto": str(linhas[0].get("texto") or "")}
    except Exception as e:  # fonte fora do ar não pode virar "tudo ok"
        out["erro_fonte"] = re.sub(r"\s+", " ", str(e))[:240]
    if agente.get("flag", {}).get("chave"):
        out["flag"] = flag_ligada(geral, agente["flag"]["chave"])
    return out
