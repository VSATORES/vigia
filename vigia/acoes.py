"""Ações que o Vigia executa a pedido da pessoa (só pela página servida no localhost).

- rodar: executa o comando declarado no toml do agente ([acoes] rodar = "..."). Nunca comando livre.
- investigar: chama o Claude em modo só leitura com o log e a configuração do agente; grava o diagnóstico.
Cada execução vira dados/acoes/<id>/<AAAAmmdd-HHMMSS>-<acao>.log (+ .json com início/fim/saída).
A saída do comando fica no .log; a última linha "__vigia_exit=N" marca o fim.
"""
import datetime as dt, glob, json, os, re, shlex, subprocess, threading

RE_FIM = re.compile(r"__vigia_exit=(\d+)")


def _pasta(geral, id_):
    p = os.path.join(geral["dados"], "acoes", re.sub(r"[^\w.-]", "_", id_))
    os.makedirs(p, exist_ok=True)
    return p


def execucoes(geral, id_, n=8):
    out = []
    for js in sorted(glob.glob(os.path.join(_pasta(geral, id_), "*.json")), reverse=True)[:n]:
        try:
            e = json.load(open(js, encoding="utf-8"))
        except (OSError, ValueError):
            continue
        log = js[:-5] + ".log"
        txt = ""
        try:
            txt = open(log, encoding="utf-8", errors="replace").read()
        except OSError:
            pass
        m = RE_FIM.search(txt)
        e["rodando"] = m is None and _vivo(e.get("pid"))
        e["exit"] = int(m.group(1)) if m else (None if e["rodando"] else -1)
        e["fim"] = e.get("fim") or (dt.datetime.fromtimestamp(os.path.getmtime(log)).replace(microsecond=0).isoformat()
                                    if not e["rodando"] and os.path.exists(log) else None)
        e["saida"] = RE_FIM.sub("", txt)[-6000:]
        diag = js[:-5] + ".md"
        if os.path.exists(diag):
            e["diagnostico"] = open(diag, encoding="utf-8", errors="replace").read()[-8000:]
        out.append(e)
    return out


def _vivo(pid):
    if not pid:
        return False
    try:
        os.kill(int(pid), 0)
    except (OSError, ValueError):
        return False
    try:  # processo zumbi já terminou
        return open(f"/proc/{int(pid)}/stat").read().split(")")[-1].split()[0] != "Z"
    except OSError:
        return True


def rodando(geral, id_):
    return any(e["rodando"] for e in execucoes(geral, id_, 3))


def _base(geral, id_, acao):
    return os.path.join(_pasta(geral, id_), dt.datetime.now().strftime("%Y%m%d-%H%M%S") + "-" + acao)


def _disparar(geral, id_, acao, comando, extra=None, base=None):
    if rodando(geral, id_):
        raise RuntimeError("já tem uma ação deste agente em andamento")
    base = base or _base(geral, id_, acao)
    log = open(base + ".log", "w", encoding="utf-8")
    # o marcador de fim é escrito pelo próprio shell: sobrevive a reinício do servidor
    # subshell: um `exit` dentro do comando não pula o marcador de fim
    p = subprocess.Popen(["bash", "-c", f"( {comando}\n)\necho \"__vigia_exit=$?\""], stdout=log, stderr=subprocess.STDOUT,
                         stdin=subprocess.DEVNULL, start_new_session=True, cwd=geral["base"])
    threading.Thread(target=p.wait, daemon=True).start()  # recolhe o processo quando terminar (sem zumbi)
    info = {"id": id_, "acao": acao, "inicio": dt.datetime.now().replace(microsecond=0).isoformat(), "pid": p.pid,
            "comando": comando if acao == "rodar" else "claude -p (só leitura)", **(extra or {})}
    json.dump(info, open(base + ".json", "w", encoding="utf-8"), ensure_ascii=False)
    return info


def rodar(geral, agente):
    cmd = agente.get("acoes", {}).get("rodar")
    if not cmd:
        raise PermissionError("este agente não tem 'rodar' configurado no toml")
    return _disparar(geral, agente["id"], "rodar", cmd)


def investigar(geral, agente, contexto):
    """contexto: dict com nome, st, motivo, acao, rodadas recentes (do último painel gerado)."""
    ac = agente.get("acoes", {})
    ferramentas = ["Read", "Grep", "Glob"] + list(ac.get("ferramentas", []))
    lidos = [agente["_arquivo"]] + ([ac["instrucoes"]] if ac.get("instrucoes") else [])
    if agente.get("log", {}).get("arquivos"):
        logs = sorted(glob.glob(agente["log"]["arquivos"]))[-2:]
        lidos += logs
    sql = agente.get("sql", {})
    prompt = (
        "Você é o investigador do Vigia, um painel de monitoramento. Responda em português do Brasil, curto, "
        "sem jargão, em 3 blocos: **O que aconteceu**, **Causa provável** (diga se é certeza ou suspeita e a "
        "evidência), **O que fazer** (passos para a pessoa). NÃO altere nenhum arquivo, NÃO rode comandos que "
        "mudem algo, NÃO mande mensagem para ninguém.\n\n"
        f"Item: {contexto.get('nome')} · estado agora: {contexto.get('st')} · motivo: {contexto.get('motivo')}\n"
        f"Ação sugerida pelo painel: {re.sub('<[^>]+>', '', contexto.get('acao') or '')}\n"
        f"Últimas rodadas (hora, estado, motivo): {json.dumps(contexto.get('rodadas', [])[:8], ensure_ascii=False)}\n\n"
        "Leia estes arquivos antes de concluir:\n" + "\n".join(f"- {p}" for p in lidos) +
        ("\n\nO agente grava num banco; as consultas que o painel usa estão no arquivo de configuração acima"
         + (" e você pode rodar SELECTs com a ferramenta de banco disponível." if ac.get("ferramentas") else ".")
         if sql else "")
    )
    base = _base(geral, agente["id"], "investigar")
    destino = base + ".md"
    claude = ac.get("claude", geral.get("claude", "claude"))
    cmd = (f"{shlex.quote(claude)} -p {shlex.quote(prompt)} --allowedTools {shlex.quote(','.join(ferramentas))} "
           f"> {shlex.quote(destino)} 2>&1; echo 'diagnóstico gravado'")
    return _disparar(geral, agente["id"], "investigar", cmd, {"diagnostico_em": destino}, base=base)
