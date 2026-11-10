"""Rotinas que gravam uma linha JSON por execução.

  [log]
  arquivos = "logs/execucoes.jsonl"
  campo_hora = "hora"            # ISO 8601
  campo_erro = ["erro", "error"] # se preenchido, a rodada falhou
  campo_motivo = ["motivo"]      # texto mostrado
"""
import datetime as dt, glob, json


def coletar(agente, geral, agora):
    lg = agente["log"]
    ch = lg.get("campo_hora", "hora")
    ce = lg.get("campo_erro", ["erro", "error"])
    cm = lg.get("campo_motivo", ["motivo"])
    rodadas = []
    for arq in sorted(glob.glob(lg["arquivos"])):
        try:
            linhas = open(arq, encoding="utf-8", errors="replace").read().splitlines()[-3000:]
        except OSError:
            continue
        for ln in linhas:
            try:
                j = json.loads(ln)
                h = dt.datetime.fromisoformat(str(j[ch]).replace("Z", "+00:00"))
                if h.tzinfo:
                    h = h.astimezone().replace(tzinfo=None)
            except (ValueError, KeyError, TypeError):
                continue
            erro = next((j[c] for c in ce if j.get(c)), None)
            motivo = next((str(j[c]) for c in cm if j.get(c)), "")
            acao = j.get("acao")
            rodadas.append({"ini": h, "fim": h, "dur": None, "status": "falhou" if erro else "ok",
                            "motivo": str(erro)[:200] if erro else ((f"{acao}: " if acao else "") + (motivo or "ok")),
                            "trecho": ln[:600], "arquivo": arq, "volume": None, "manual": False})
    rodadas.sort(key=lambda r: r["ini"])
    return {"rodadas": rodadas}
