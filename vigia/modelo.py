"""Transforma o que as fontes leram em estados e números para a tela.

Estados do item (agora):  ok · late (atrasado) · er (falhou) · nr (não rodou) · off (desligado) · run (rodando) · none
Estado do dia (célula):   ok · late · er · pc (computador desligado) · none (nada esperado)
Regras de honestidade (do documento do projeto):
- ausência de sinal nunca é verde; fonte fora do ar = falha, não "ok";
- número sem fonte real não aparece;
- dia com o computador desligado não conta na meta (aparece hachurado à parte).
"""
import datetime as dt, statistics
from . import historico

N_DIAS = 30


def _pct(vs, q):
    if not vs:
        return None
    vs = sorted(vs)
    k = (len(vs) - 1) * q
    a, b = int(k), min(int(k) + 1, len(vs) - 1)
    return vs[a] + (vs[b] - vs[a]) * (k - a)


def dur_txt(s):
    if s is None:
        return "—"
    s = int(round(s))
    if s < 60:
        return f"{s} s"
    if s < 3600:
        return f"{s // 60} min" if s % 60 < 5 or s >= 600 else f"{s // 60} min {s % 60:02d} s"
    return f"{s // 3600}h{(s % 3600) // 60:02d}"


def gap_txt(minutos):
    if minutos is None:
        return "—"
    m = int(minutos)
    if m < 60:
        return f"{m} min"
    if m < 48 * 60:
        return f"{m // 60}h{m % 60:02d}"
    return f"{m // 1440} dias"


def hhmm(t):
    return t.strftime("%H:%M")


def quando_txt(t, agora):
    if t is None:
        return "—"
    d = (agora.date() - t.date()).days
    if d == 0:
        return hhmm(t)
    if d == 1:
        return "ontem " + hhmm(t)
    return t.strftime("%d/%m")


def _idx(agora, t):
    return (agora.date() - t.date()).days


# ---------------------------------------------------------------- rotinas (cron + log)
def item_rotina(a, col, geral, agora, vivos):
    cron = a["agenda"].get("_cron")
    margem = dt.timedelta(minutes=int(a["agenda"].get("margem_min", geral["margem_atraso_min"])))
    rodadas = col["rodadas"]
    ini_jan = agora - dt.timedelta(days=N_DIAS)
    desde = a["agenda"].get("desde")
    desde = dt.datetime.fromisoformat(desde) if desde else None
    if desde is None and rodadas:
        desde = rodadas[0]["ini"] - dt.timedelta(minutes=1)
    esperados = cron.entre(max(ini_jan, desde), agora) if (cron and desde) else []
    # janela para casar rodada com horário: até 2h, nunca maior que o espaço entre dois horários
    gaps = [(b - c).total_seconds() / 60 for c, b in zip(esperados, esperados[1:])]
    jan = dt.timedelta(minutes=min(120, (min(gaps) - 1) if gaps else 120))
    usadas, linhas = set(), []
    for t in esperados:
        achou = None
        for i, r in enumerate(rodadas):
            if i in usadas:
                continue
            if t - dt.timedelta(minutes=15) <= r["ini"] <= t + jan:
                achou = i
                break
        if achou is not None:
            usadas.add(achou)
            r = rodadas[achou]
            st = {"ok": "ok", "sem_novidade": "ok", "falhou": "er", "rodando": "run"}[r["status"]]
            linhas.append({"t": r["ini"], "st": st, "motivo": r["motivo"], "dur": r["dur"], "rod": r, "prog": t})
        elif agora - t <= margem:
            continue  # ainda dentro da margem: nem atrasado
        elif agora - t <= jan:
            linhas.append({"t": t, "st": "late", "motivo": f"Atrasada: devia ter rodado às {hhmm(t)}", "dur": None, "rod": None, "prog": t})
        elif vivos and t < vivos[0] - historico.JANELA_VIVO:
            continue  # antes de existir sinal de vida não dá para saber; não acusa
        elif not historico.ligado_em(vivos, t):
            linhas.append({"t": t, "st": "pc", "motivo": "Computador desligado no horário", "dur": None, "rod": None, "prog": t})
        else:
            linhas.append({"t": t, "st": "nr", "motivo": f"Não rodou no horário ({hhmm(t)})", "dur": None, "rod": None, "prog": t})
    desde_cfg = dt.datetime.fromisoformat(a["agenda"]["desde"]) if a["agenda"].get("desde") else None
    for i, r in enumerate(rodadas):  # rodadas à mão / fora de horário
        if i not in usadas and r["ini"] >= ini_jan and not (desde_cfg and r["ini"] < desde_cfg and r["status"] == "falhou"):
            st = {"ok": "ok", "sem_novidade": "ok", "falhou": "er", "rodando": "run"}[r["status"]]
            linhas.append({"t": r["ini"], "st": st, "motivo": r["motivo"] + (" (rodada à mão)" if r.get("manual") else ""),
                           "dur": r["dur"], "rod": r, "prog": None})
    linhas.sort(key=lambda x: x["t"])

    dias = ["none"] * N_DIAS
    vol = [0] * N_DIAS
    tem_volume = any(r.get("volume") is not None for r in rodadas)
    por_dia = {}
    for ln in linhas:
        i = _idx(agora, ln["t"])
        if 0 <= i < N_DIAS:
            por_dia.setdefault(i, []).append(ln)
            if ln["st"] == "ok":
                vol[i] += (ln["rod"].get("volume") or 0) if tem_volume else 1
    for i, ls in por_dia.items():
        agendadas = [x for x in ls if x["prog"] is not None]
        sts = {x["st"] for x in (agendadas or ls)}  # rodada à mão não suja o dia que teve rodada agendada
        if sts & {"er", "nr"}:
            dias[i] = "er"
        elif "late" in sts:
            dias[i] = "late"
        elif "ok" in sts or "run" in sts:
            dias[i] = "ok"
        elif "pc" in sts:
            dias[i] = "pc"

    reais = [x for x in linhas if x["st"] != "pc"]
    ult = reais[-1] if reais else (linhas[-1] if linhas else None)
    if ult is None:
        st, motivo = "none", "Ainda não rodou"
    else:
        st, motivo = ult["st"], ult["motivo"]
        if st == "pc":
            st = "none"
    seguidas = 0
    for x in reversed(reais):
        if x["st"] in ("er", "nr"):
            seguidas += 1
        elif x["st"] in ("ok",):
            break
    durs = [x["dur"] for x in linhas if x["dur"] is not None and x["st"] == "ok" and x["prog"] is not None]
    p25, p75 = _pct(durs[-28:], .25), _pct(durs[-28:], .75)
    prox = cron.proximo(agora) if cron else None

    acao = ""
    cmd = a["agenda"].get("comando")
    if cmd and geral.get("_crontab") is not None and cmd not in geral["_crontab"]:
        st, motivo = "nr", "Não está agendada no crontab"
        acao = (f"<b>Esta rotina não está no crontab</b>, então não vai rodar sozinha. "
                f"Falta uma linha com <code>{a['agenda'].get('cron', '')}</code> chamando <code>{cmd}</code>.")
    elif st in ("er", "nr", "late"):
        regra_acao = ""
        if ult and ult.get("rod"):
            for r in a.get("regras", []):
                import re
                if r.get("acao") and re.search(r["se"], ult["rod"]["trecho"] + "\n" + ult["rod"]["motivo"], re.I | re.S):
                    regra_acao = r["acao"]
                    break
        quando = quando_txt(ult["t"], agora)
        acao = f"<b>{ 'Falhou' if st == 'er' else 'Não rodou' if st == 'nr' else 'Atrasada' } {quando}: {motivo}.</b> "
        if regra_acao and not regra_acao.rstrip().endswith((".", "!", "?")):
            regra_acao = regra_acao.rstrip() + "."
        acao += regra_acao or (f"A próxima rodada é {quando_txt(prox, agora) if prox and prox.date() != agora.date() else 'às ' + hhmm(prox)}." if prox else "")
        if seguidas > 1:
            acao += f" São {seguidas} falhas seguidas."

    rods = {}
    for ln in linhas:
        i = _idx(agora, ln["t"])
        if 0 <= i < N_DIAS:
            rods.setdefault(i, []).append([hhmm(ln["t"]), ln["st"], ln["motivo"], dur_txt(ln["dur"]),
                                           (ln["rod"] or {}).get("trecho", ""), (ln["rod"] or {}).get("arquivo", "")])
    eventos = [[hhmm(x["t"]), a["id"], x["st"], a["nome"], x["motivo"]] for x in linhas if _idx(agora, x["t"]) == 0]
    mes = [x for x in linhas if x["t"].month == agora.month and x["t"].year == agora.year]
    ok_m = sum(1 for x in mes if x["st"] == "ok")
    ruim_m = sum(1 for x in mes if x["st"] in ("er", "nr"))
    tipo_rot = "rotina " + (a["agenda"].get("rotulo") or (cron.expr if cron else ""))
    nums = [
        [f"{100 * ok_m / (ok_m + ruim_m):.1f}%".replace(".", ",") if ok_m + ruim_m else "—", "sucesso no mês",
         f"{ok_m} de {ok_m + ruim_m} rodadas" if ok_m + ruim_m else "sem rodadas no mês"],
        [dur_txt(ult["dur"]) if ult else "—", "última duração",
         f"normal: {dur_txt(p25)} a {dur_txt(p75)}" if p25 is not None and len(durs) >= 3 else "pouca rodada medida"],
        [str(seguidas), "falhas seguidas" if seguidas != 1 else "falha seguida", "desde a última ok" if seguidas else "nenhuma"],
        [quando_txt(prox, agora) if prox else "—", "próxima rodada", a["agenda"].get("rotulo", "")],
    ]
    return {
        "k": a["id"], "nome": a["nome"], "area": a.get("area", ""), "tipo": tipo_rot.strip(), "fonte": a["fonte"],
        "st": st, "motivo": motivo, "ult": quando_txt(ult["t"], agora) if ult else "—", "oque": a.get("o_que", ""),
        "acao": acao, "dias": dias, "vol": vol, "volNome": a.get("volume_nome") or ("volume por dia" if tem_volume else "rodadas ok por dia"),
        "nums": nums, "rodadas": {str(k): v for k, v in rods.items()}, "durs": [round(d) for d in durs[-30:]],
        "ok_mes": ok_m, "ruim_mes": ruim_m, "prox": prox.isoformat() if prox else None,
    }, eventos, [x["t"] for x in linhas if x["rod"]]


# ---------------------------------------------------------------- agentes (banco)
def item_agente(a, col, geral, agora):
    dias = ["none"] * N_DIAS
    vol = [0] * N_DIAS
    lim = float(a.get("sql", {}).get("limite_erros_pct", 0)) / 100
    hist_n = {}  # dia da semana útil/fds -> volumes
    for i in range(N_DIAS):
        d = (agora - dt.timedelta(days=i)).date()
        r = col["dias"].get(d.isoformat())
        n = r["n"] if r else 0
        vol[i] = n
        if i > 0:
            hist_n.setdefault(d.weekday() >= 5, []).append(n)
    flag = col.get("flag")
    for i in range(N_DIAS):
        d = (agora - dt.timedelta(days=i)).date()
        r = col["dias"].get(d.isoformat())
        if r and r["n"] > 0:
            dias[i] = "er" if r["erros"] > lim * r["n"] and r["erros"] > 0 else "ok"
        elif r and r["erros"] > 0:
            dias[i] = "er"
        elif i > 0 and flag is not False and col.get("entrada") is not None:
            # dia inteiro calado só é falha se chegou trabalho naquele dia (sem essa prova, não acusa)
            dias[i] = "er" if col["entrada"].get(d.isoformat(), 0) > 0 else "none"
    evs = col["eventos"]
    ultima = evs[-1]["quando"] if evs else max((r["ultima"] for r in col["dias"].values() if isinstance(r.get("ultima"), dt.datetime)), default=None)
    # intervalo normal entre gravações durante o expediente (pausas de mais de 6h = noite/fim de semana, ficam de fora)
    gaps = [g for g in ((b["quando"] - c["quando"]).total_seconds() / 60 for c, b in zip(evs, evs[1:])) if g < 360]
    gap_normal = max(60.0, _pct(gaps, .95) or 0) if len(gaps) >= 10 else None
    sem = (agora - ultima).total_seconds() / 60 if ultima else None
    # costuma ter atividade nesta faixa de horário? (fração dos últimos 14 dias com gravação nas 2h antes de agora)
    dias_com = 0
    for k in range(1, 15):
        ini_f, fim_f = agora - dt.timedelta(days=k, hours=2), agora - dt.timedelta(days=k)
        if any(ini_f <= e["quando"] <= fim_f for e in evs):
            dias_com += 1
    costuma = dias_com >= 7
    dias_sem = (agora - ultima).days if ultima else None
    hoje = col["dias"].get(agora.date().isoformat(), {"n": 0, "erros": 0, "humano": 0})
    vols_uteis = hist_n.get(agora.weekday() >= 5, [])
    p25, p75 = _pct(vols_uteis, .25), _pct(vols_uteis, .75)

    if col.get("erro_fonte"):
        st, motivo = "er", "Não consegui ler o banco: " + col["erro_fonte"]
    elif flag is False and not (sem is not None and sem < 24 * 60):
        st, motivo = "off", "Flag desligada no PostHog"
    elif flag is True and (ultima is None or dias_sem >= 7):
        st, motivo = "nr", ("Flag ligada, mas nenhuma gravação nos últimos 30 dias" if ultima is None
                            else f"Flag ligada, mas sem gravação há {dias_sem} dias (última {ultima:%d/%m})")
    elif hoje["erros"] > 0 and hoje["erros"] > lim * max(hoje["n"], 1):
        st, motivo = "er", f"{hoje['erros']} {'gravação' if hoje['erros'] == 1 else 'gravações'} com erro hoje"
    elif col.get("alerta"):
        st, motivo = "late", col["alerta"]["texto"] or f"{col['alerta']['n']} itens parados"
    elif sem is not None and gap_normal and costuma and sem > max(gap_normal * 2, 120):
        st, motivo = "late", f"Sem atividade há {gap_txt(sem)} (normal: até {gap_txt(gap_normal)})"
    elif ultima is None:
        st, motivo = ("off" if flag is None else "nr"), "Nenhuma gravação nos últimos 30 dias"
    else:
        st, motivo = "ok", f"Última gravação {quando_txt(ultima, agora)}"
    acao = ""
    if st in ("er", "late", "nr"):
        acao = f"<b>{motivo}.</b> " + (a.get("acao_falha") or "")
    if flag is None and a.get("flag", {}).get("chave"):
        motivo += " · flag não lida"
    if flag is False and st != "off":
        motivo += " · a flag aparece desligada no PostHog, mas houve gravação nas últimas 24h"

    erros14 = sum(col["dias"].get((agora - dt.timedelta(days=i)).date().isoformat(), {}).get("erros", 0) for i in range(14))
    hum14 = sum(col["dias"].get((agora - dt.timedelta(days=i)).date().isoformat(), {}).get("humano", 0) for i in range(14))
    n14 = sum(vol[:14])
    rot = a.get("rotulos", {})
    nums = [
        [str(hoje["n"]), rot.get("volume", "gravações hoje"), f"normal: {round(p25)} a {round(p75)}" if p75 else "sem histórico"],
        [f"{erros14} de {n14}" if n14 else "0", rot.get("erros", "com erro"), "14 dias"],
        [f"{hum14} de {n14}" if n14 else "0", rot.get("humano", "revisados por pessoa"), "14 dias"] if "humano" in rot or hum14 else
        [("ligada" if flag else "desligada" if flag is False else "não lida"), "flag", a.get("flag", {}).get("chave", "sem flag")],
        [gap_txt(sem), "sem atividade", f"normal: até {gap_txt(gap_normal)}" if gap_normal else "pouco histórico"],
    ]
    # rodadas do dia = gravações agregadas por hora (agente grava centenas por dia)
    rods = {}
    for e in evs:
        i = _idx(agora, e["quando"])
        if 0 <= i < N_DIAS:
            h = e["quando"].strftime("%H:00")
            b = rods.setdefault(i, {}).setdefault(h, [0, 0, ""])
            b[0] += 1
            if not e["ok"]:
                b[1] += 1
                b[2] = e["texto"]
    rods_l = {}
    for i, hs in rods.items():
        rods_l[str(i)] = [[h, "er" if v[1] else "ok", f"{v[0]} {'gravação' if v[0] == 1 else 'gravações'}" + (f", {v[1]} com erro: {v[2]}" if v[1] else ""), "", "", ""]
                          for h, v in sorted(hs.items(), reverse=True)]
    for i in range(N_DIAS):
        if str(i) not in rods_l and vol[i]:
            r = col["dias"].get((agora - dt.timedelta(days=i)).date().isoformat())
            rods_l[str(i)] = [["dia", dias[i], f"{r['n']} gravações · {r['erros']} com erro · {r['humano']} com pessoa", "", "", ""]]
    eventos = [[h, a["id"], "er" if v[1] else "ok", a["nome"], f"{v[0]} {'gravação' if v[0] == 1 else 'gravações'}" + (f", {v[1]} com erro" if v[1] else "")]
               for h, v in rods.get(0, {}).items()]
    if st in ("late", "er") and col.get("alerta"):
        eventos.append([hhmm(agora), a["id"], "late", a["nome"], col["alerta"]["texto"]])
    mes_ok = sum(1 for i in range(N_DIAS) if (agora - dt.timedelta(days=i)).month == agora.month and dias[i] == "ok")
    mes_ruim = sum(1 for i in range(N_DIAS) if (agora - dt.timedelta(days=i)).month == agora.month and dias[i] == "er")
    return {
        "k": a["id"], "nome": a["nome"], "area": a.get("area", ""), "tipo": "agente", "fonte": a["fonte"],
        "st": st, "motivo": motivo, "ult": quando_txt(ultima, agora), "oque": a.get("o_que", ""), "acao": acao,
        "dias": dias, "vol": vol, "volNome": a.get("volume_nome", "gravações por dia"), "nums": nums,
        "rodadas": rods_l, "durs": [], "ok_mes": mes_ok, "ruim_mes": mes_ruim, "prox": None,
    }, eventos


# ---------------------------------------------------------------- tudo
ORDEM = {"er": 0, "nr": 1, "late": 2, "run": 3, "ok": 4, "none": 5, "off": 6}


def montar(geral, agentes, coletas, agora, versao, marcas=None):
    itens, eventos, carimbos = [], [], []
    for a in agentes:  # sinais de vida vêm de qualquer rodada registrada
        if a["fonte"] != "sql":
            carimbos += [r["ini"] for r in coletas[a["id"]]["rodadas"]]
    vivos = historico.vivos(geral, extras=carimbos)
    for a in agentes:
        col = coletas[a["id"]]
        if a["fonte"] == "sql":
            it, ev = item_agente(a, col, geral, agora)
        else:
            it, ev, _ = item_rotina(a, col, geral, agora, vivos)
        itens.append(it)
        eventos += ev
    salvos = historico.dias_salvos(geral)
    for it in itens:  # log apagado: usa o que o Vigia guardou
        for i in range(2, N_DIAS):
            if it["dias"][i] == "none":
                s = salvos.get((agora - dt.timedelta(days=i)).date().isoformat(), {}).get(it["k"])
                if s:
                    it["dias"][i] = s
    itens.sort(key=lambda x: (ORDEM.get(x["st"], 9), x["nome"].lower()))
    eventos.sort(key=lambda e: e[0], reverse=True)
    ok = sum(i["ok_mes"] for i in itens)
    ruim = sum(i["ruim_mes"] for i in itens)
    meta = geral["meta"]
    sucesso = ok / (ok + ruim) if ok + ruim else None
    folga_total = (ok + ruim) * (1 - meta)
    folga = (ruim / folga_total) if folga_total else None
    pc_dias = sum(1 for i in range(N_DIAS) if any(it["dias"][i] == "pc" for it in itens))
    return {
        "titulo": geral["titulo"], "subtitulo": geral.get("subtitulo", ""), "versao": versao,
        "gerado": agora.isoformat(), "intervalo_min": int(geral.get("intervalo_min", 15)),
        "meta": meta, "sucesso_mes": sucesso, "folga_usada": folga, "ok_mes": ok, "ruim_mes": ruim, "pc_dias": pc_dias,
        "itens": itens, "eventos": eventos[:80], "marcas": marcas or [], "repo": geral.get("repo", ""),
    }
