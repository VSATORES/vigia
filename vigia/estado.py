"""Estado que o Vigia guarda das ações da pessoa: "já vi", pausas e o último estado avisado.

dados/estado.json = {"visto": {id: {"em", "st"}}, "pausa": {id: {"em", "motivo"}}, "notificado": {id: st},
                     "historico": [{"em", "id", "acao", "texto"}]}
"""
import datetime as dt, json, os, threading

_trava = threading.Lock()


def _arq(geral):
    os.makedirs(geral["dados"], exist_ok=True)
    return os.path.join(geral["dados"], "estado.json")


def ler(geral):
    try:
        d = json.load(open(_arq(geral), encoding="utf-8"))
    except (OSError, ValueError):
        d = {}
    for k, v in (("visto", {}), ("pausa", {}), ("historico", [])):
        d.setdefault(k, v)
    return d


def gravar(geral, d):
    p = _arq(geral)
    tmp = p + ".tmp"
    json.dump(d, open(tmp, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    os.replace(tmp, p)


def registrar(geral, id_, acao, texto="", **campos):
    """aplica uma ação de estado e guarda no histórico (as últimas 300)."""
    with _trava:
        d = ler(geral)
        agora = dt.datetime.now().replace(microsecond=0).isoformat()
        if acao == "visto":
            d["visto"][id_] = {"em": agora, "st": campos.get("st", "")}
        elif acao == "pausar":
            d["pausa"][id_] = {"em": agora, "motivo": texto}
        elif acao == "retomar":
            d["pausa"].pop(id_, None)
        d["historico"] = (d["historico"] + [{"em": agora, "id": id_, "acao": acao, "texto": texto}])[-300:]
        gravar(geral, d)
        return d
