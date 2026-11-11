"""Pedidos de aprovação: o agente escreve, a pessoa decide, o Vigia executa.

Contrato: um arquivo por decisão em <pedidos>/<agente>/<id>.json (campos em docs/pedido.schema.json).
O agente NUNCA executa. Quem executa é o Vigia, depois do clique, e só o executor declarado no toml do agente:

    [executores]
    liberar_card = "/caminho/liberar.py {pedido}"

O estado de cada pedido (aprovado, recusado, adiado, executado, falhou) fica em <dados>/decisoes.jsonl, uma linha
por evento, só acrescentada. O arquivo do pedido não é reescrito. Um pedido aprovado nunca executa duas vezes.
"""
import datetime as dt, glob, json, os, re, shlex, subprocess, threading

OBRIGATORIOS = ("id", "agente", "titulo", "risco", "proposta")
RISCOS = ("producao", "envio_externo", "dinheiro", "interno", "saude")
DECISOES = ("aprovar", "recusar", "adiar")
FINAIS = ("aprovado", "recusado", "executado", "falhou", "executando")
_trava = threading.Lock()
RE_ID = re.compile(r"^[\w.-]{1,80}$")


def agora():
    return dt.datetime.now().replace(microsecond=0)


def _arq_decisoes(geral):
    os.makedirs(geral["dados"], exist_ok=True)
    return os.path.join(geral["dados"], "decisoes.jsonl")


def eventos(geral):
    """Todas as linhas de decisoes.jsonl, na ordem."""
    out = []
    try:
        with open(_arq_decisoes(geral), encoding="utf-8") as f:
            for linha in f:
                linha = linha.strip()
                if linha:
                    try:
                        out.append(json.loads(linha))
                    except ValueError:
                        continue
    except FileNotFoundError:
        pass
    return out


def _registrar(geral, ev):
    ev = {"em": agora().isoformat(), **ev}
    with _trava, open(_arq_decisoes(geral), "a", encoding="utf-8") as f:
        f.write(json.dumps(ev, ensure_ascii=False) + "\n")
    return ev


def _reservar(geral, ev):
    """Confere e registra na mesma trava: se o pedido já tem estado final, recusa (dois cliques não executam 2x)."""
    ev = {"em": agora().isoformat(), **ev}
    with _trava:
        ultimo = None
        for e in eventos(geral):
            if e.get("agente") == ev["agente"] and e.get("id") == ev["id"]:
                ultimo = e
        if ultimo and ultimo.get("estado") in FINAIS:
            raise RuntimeError(f"esse pedido já foi decidido ({ultimo['estado']})")
        with open(_arq_decisoes(geral), "a", encoding="utf-8") as f:
            f.write(json.dumps(ev, ensure_ascii=False) + "\n")
    return ev


def estados(geral):
    """-> {(agente, id): último evento}"""
    est = {}
    for ev in eventos(geral):
        est[(ev.get("agente"), ev.get("id"))] = ev
    return est


def validar(p):
    """-> lista de problemas (vazia = válido)."""
    erros = [f"falta '{c}'" for c in OBRIGATORIOS if not p.get(c)]
    if p.get("risco") and p["risco"] not in RISCOS:
        erros.append(f"risco '{p['risco']}' inválido")
    if p.get("id") and not RE_ID.match(str(p["id"])):
        erros.append("id com caractere inválido")
    for k in ("proposta", "alternativa"):
        a = p.get(k)
        if a is not None and (not isinstance(a, dict) or not a.get("acao") or not a.get("rotulo") or "previa" not in a):
            erros.append(f"{k} precisa de acao, rotulo e previa")
    return erros


def ler(geral):
    """-> (pedidos válidos, problemas). Cada pedido ganha _arquivo e _pasta."""
    raiz = geral.get("pedidos")
    if not raiz or not os.path.isdir(raiz):
        return [], []
    out, prob = [], []
    for arq in sorted(glob.glob(os.path.join(raiz, "*", "*.json"))):
        try:
            p = json.load(open(arq, encoding="utf-8"))
        except (OSError, ValueError) as e:
            prob.append(f"{arq}: JSON inválido ({e})")
            continue
        p.setdefault("agente", os.path.basename(os.path.dirname(arq)))
        e = validar(p)
        if e:
            prob.append(f"{arq}: " + "; ".join(e))
            continue
        p["_arquivo"], p["_pasta"] = arq, os.path.dirname(arq)
        out.append(p)
    return out, prob


def pendentes(geral, quando=None):
    """Pedidos que esperam a pessoa: sem decisão, ou adiados cujo prazo já passou."""
    quando = quando or agora()
    est = estados(geral)
    lista, _ = ler(geral)
    out = []
    for p in lista:
        ev = est.get((p["agente"], p["id"]))
        if ev:
            if ev.get("estado") in FINAIS:
                continue
            if ev.get("estado") == "adiado" and ev.get("ate") and dt.datetime.fromisoformat(ev["ate"]) > quando:
                continue
        out.append(p)
    ordem = {"dinheiro": 0, "producao": 1, "envio_externo": 2, "saude": 3, "interno": 4}
    out.sort(key=lambda p: (p.get("prazo") or "9999", ordem.get(p["risco"], 9), p.get("criado_em", "")))
    return out


def resumo(geral):
    """Contagem para o topo e para o aviso curto: {esperando, decididos_hoje}."""
    hoje = agora().date().isoformat()
    dec = {(e["agente"], e["id"]) for e in eventos(geral)
           if e.get("estado") in ("aprovado", "recusado") and str(e.get("em", "")).startswith(hoje)}
    return {"esperando": len(pendentes(geral)), "decididos_hoje": len(dec)}


def _achar(geral, agente, id_):
    lista, _ = ler(geral)
    return next((p for p in lista if p["agente"] == agente and str(p["id"]) == str(id_)), None)


def decidir(geral, agentes, agente, id_, decisao, opcao=0, texto=None, horas=1, quem="painel"):
    """Registra a decisão e, se aprovada, dispara o executor. Erros: LookupError (404), PermissionError (403),
    RuntimeError (409, já decidido)."""
    if decisao not in DECISOES:
        raise ValueError(f"decisão '{decisao}' inválida")
    if not RE_ID.match(str(agente)) or not RE_ID.match(str(id_)):
        raise LookupError("pedido inválido")
    p = _achar(geral, agente, id_)
    if not p:
        raise LookupError(f"pedido {agente}/{id_} não existe")
    if decisao == "recusar":
        return _reservar(geral, {"agente": agente, "id": str(id_), "estado": "recusado", "quem": quem,
                                  "titulo": p["titulo"], "texto": (texto or "")[:500]})
    if decisao == "adiar":
        ate = agora() + dt.timedelta(hours=max(0.25, min(float(horas), 72)))
        return _reservar(geral, {"agente": agente, "id": str(id_), "estado": "adiado", "ate": ate.isoformat(),
                                  "quem": quem, "titulo": p["titulo"]})
    acao = p["proposta"] if int(opcao or 0) == 0 else p.get("alternativa")
    if not acao:
        raise LookupError("esse pedido não tem alternativa")
    cfg = next((a for a in agentes if a["id"] == agente), None)
    cmd = ((cfg or {}).get("executores") or {}).get(acao["acao"])
    if not cmd:
        raise PermissionError(f"o executor '{acao['acao']}' não está declarado em [executores] do agente '{agente}'")
    efetivo = dict(acao)
    editado = texto is not None and texto != acao.get("previa")
    if editado:
        efetivo["previa"] = texto
    ev = _reservar(geral, {"agente": agente, "id": str(id_), "estado": "executando", "quem": quem,
                            "titulo": p["titulo"], "acao": acao["acao"], "opcao": int(opcao or 0),
                            "editado": editado, "previa": efetivo.get("previa", "")[:2000]})
    _executar(geral, p, efetivo, cmd)
    return ev


def _executar(geral, p, acao, cmd):
    """Grava o pedido efetivo (com o texto editado) e roda o executor em segundo plano."""
    pasta = os.path.join(geral["dados"], "execucoes", p["agente"])
    os.makedirs(pasta, exist_ok=True)
    base = os.path.join(pasta, agora().strftime("%Y%m%d-%H%M%S") + "-" + re.sub(r"[^\w.-]", "_", str(p["id"])))
    efetivo = {k: v for k, v in p.items() if not k.startswith("_")}
    efetivo["executar"] = acao
    json.dump(efetivo, open(base + ".json", "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    linha = cmd.replace("{pedido}", shlex.quote(base + ".json"))
    env = {**os.environ, "VIGIA_PEDIDO": base + ".json", "CLAUDE_ROTINA": "1"}

    def rodar():
        try:
            with open(base + ".log", "w", encoding="utf-8") as log:
                r = subprocess.run(["bash", "-c", linha], stdout=log, stderr=subprocess.STDOUT, stdin=subprocess.DEVNULL,
                                   cwd=geral["base"], env=env, timeout=600)
            ok = r.returncode == 0
            saida = open(base + ".log", encoding="utf-8", errors="replace").read()[-600:]
        except Exception as e:  # noqa: BLE001 — qualquer falha vira "falhou" no registro
            ok, saida = False, str(e)
        _registrar(geral, {"agente": p["agente"], "id": str(p["id"]), "estado": "executado" if ok else "falhou",
                           "titulo": p["titulo"], "acao": acao["acao"], "log": base + ".log", "saida": saida})

    threading.Thread(target=rodar, daemon=True).start()


def midia_segura(geral, agente, nome):
    """Caminho de um anexo local do pedido, só dentro de <pedidos>/<agente>/ (ou None)."""
    raiz = os.path.realpath(os.path.join(geral["pedidos"], agente))
    alvo = os.path.realpath(os.path.join(raiz, nome))
    if not alvo.startswith(raiz + os.sep) or not os.path.isfile(alvo):
        return None
    return alvo


def para_pagina(geral, agentes, saude=()):
    """Lista pronta para a página: pendentes + cartões de saúde dos agentes."""
    def link(p, m):
        u = m.get("url", "")
        if re.match(r"^(https?:|data:)", u):
            return u
        return f"/midia/{p['agente']}/{u}"
    out = []
    for p in pendentes(geral):
        q = {k: v for k, v in p.items() if not k.startswith("_")}
        q["midia"] = [{**m, "url": link(p, m)} for m in p.get("midia", [])]
        cfg = next((a for a in agentes if a["id"] == p["agente"]), {})
        q["agente_nome"] = cfg.get("nome") or p["agente"]
        out.append(q)
    return out + list(saude)
