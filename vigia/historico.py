"""Memória própria do Vigia (sobrevive a log apagado):
- vivo.txt: um carimbo por geração → buraco = computador desligado naquele intervalo;
- dias/AAAA-MM-DD.json: status de cada item naquele dia.
"""
import datetime as dt, glob, json, os

JANELA_VIVO = dt.timedelta(minutes=40)


def _pasta(geral, *p):
    d = os.path.join(geral["historico"], *p)
    os.makedirs(d if not os.path.splitext(d)[1] else os.path.dirname(d), exist_ok=True)
    return d


def registrar_vivo(geral, agora):
    arq = os.path.join(_pasta(geral), "vivo.txt")
    with open(arq, "a", encoding="utf-8") as f:
        f.write(agora.strftime("%Y-%m-%dT%H:%M:%S") + "\n")


def vivos(geral, extras=()):
    """carimbos de "o computador estava ligado": os do Vigia + arquivos extras configurados + o que vier de fora."""
    out = list(extras)
    arq = os.path.join(geral["historico"], "vivo.txt")
    for caminho in [arq] + list(geral.get("vivo", [])):
        for p in glob.glob(caminho):
            try:
                for ln in open(p, encoding="utf-8", errors="replace").read().splitlines()[-20000:]:
                    ln = ln.strip()
                    if not ln:
                        continue
                    if ln.startswith("{"):
                        try:
                            v = json.loads(ln).get("hora")
                        except ValueError:
                            continue
                    else:
                        v = ln
                    try:
                        t = dt.datetime.fromisoformat(str(v).replace("Z", "+00:00"))
                    except (ValueError, TypeError):
                        continue
                    if t.tzinfo:
                        t = t.astimezone().replace(tzinfo=None)
                    out.append(t)
            except OSError:
                pass
    return sorted(out)


def ligado_em(marcas, t):
    """True se há sinal de vida perto de t. Busca binária na lista ordenada."""
    import bisect
    i = bisect.bisect_left(marcas, t - JANELA_VIVO)
    return i < len(marcas) and marcas[i] <= t + JANELA_VIVO


def salvar_dias(geral, agora, itens):
    """guarda o status de hoje e de ontem de cada item (ontem fecha à meia-noite)."""
    for idx in (0, 1):
        d = (agora - dt.timedelta(days=idx)).date().isoformat()
        arq = os.path.join(_pasta(geral, "dias"), f"{d}.json")
        dados = {it["k"]: it["dias"][idx] for it in itens if it["dias"][idx] != "none"}
        if dados:
            json.dump(dados, open(arq, "w", encoding="utf-8"), ensure_ascii=False)


def dias_salvos(geral):
    out = {}
    for p in glob.glob(os.path.join(geral["historico"], "dias", "*.json")):
        try:
            out[os.path.basename(p)[:10]] = json.load(open(p, encoding="utf-8"))
        except (OSError, ValueError):
            pass
    return out
