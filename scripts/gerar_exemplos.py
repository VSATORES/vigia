#!/usr/bin/env python3
"""Gera os dados FICTÍCIOS da demonstração (exemplos/): logs, linhas JSON e respostas de banco.
Nada aqui vem de dado real. Determinístico: o mesmo resultado sempre (semente fixa).
Uso: python3 scripts/gerar_exemplos.py   (depois: python3 -m vigia gerar --config exemplos/vigia.toml → docs/index.html)
"""
import datetime as dt, json, os, random, shutil

R = random.Random(42)
AQUI = os.path.dirname(os.path.abspath(__file__))
EX = os.path.normpath(os.path.join(AQUI, "..", "exemplos"))
AGORA = dt.datetime(2026, 11, 10, 11, 10)
LOGS = os.path.join(EX, "logs")
shutil.rmtree(LOGS, ignore_errors=True)
for p in ("backup", "relatorio", "faturas"):
    os.makedirs(os.path.join(LOGS, p), exist_ok=True)
DATE = lambda t: t.strftime("%a %b %e %H:%M:%S -03 %Y")


def desligado(t):  # o computador da demo fica desligado de madrugada e no domingo
    return t.weekday() == 6 or t.hour < 7


# 1) backup noturno às 7h: quase sempre ok, uma falha de disco
for d in range(30, -1, -1):
    t = (AGORA - dt.timedelta(days=d)).replace(hour=7, minute=0)
    if t > AGORA or t.weekday() == 6:
        continue
    dur = R.randint(40, 95)
    ok = d != 12
    txt = (f"iniciando backup\n{R.randint(800, 1200)} arquivos copiados\n" if ok else "erro: disco cheio\n") + \
          f"exit={0 if ok else 2} {DATE(t + dt.timedelta(seconds=dur))}\n"
    open(os.path.join(LOGS, "backup", f"log-{t:%Y-%m-%d}.txt"), "w").write(txt)

# 2) relatório diário às 9h com IA: falha hoje por limite de uso
for d in range(20, -1, -1):
    t = (AGORA - dt.timedelta(days=d)).replace(hour=9, minute=0)
    if t.weekday() == 6:
        continue
    if d == 0:
        txt = "You've hit your 5-hour limit · resets 1:50pm (America/Sao_Paulo)\nclaude exit=1 " + DATE(t + dt.timedelta(seconds=8)) + "\n"
    else:
        txt = f"relatório gerado: {R.randint(12, 30)} itens\nclaude exit=0 {DATE(t + dt.timedelta(seconds=R.randint(150, 320)))}\n"
    open(os.path.join(LOGS, "relatorio", f"log-{t:%Y-%m-%d}.txt"), "w").write(txt)

# 3) sincronização de hora em hora (JSONL) — também é o sinal de "computador ligado"
with open(os.path.join(LOGS, "sync.jsonl"), "w") as f:
    t = (AGORA - dt.timedelta(days=30)).replace(minute=5, second=0)
    while t <= AGORA:
        if not desligado(t):
            erro = "timeout na API" if R.random() < 0.01 else None
            f.write(json.dumps({"hora": t.isoformat(), "acao": "sync", "motivo": f"{R.randint(0, 40)} registros", "erro": erro}) + "\n")
        t += dt.timedelta(hours=1)

# 4) agentes "por banco": respostas prontas no lugar de um banco de verdade
banco = {}
def por_dia(chave, base_util, base_fds, erro_pct=0.0, humano_pct=0.0, ultimo_dia=0, ultima_h=10):
    linhas, evs = [], []
    for d in range(30):
        dia = (AGORA - dt.timedelta(days=d)).date()
        if d < ultimo_dia:
            continue
        n = max(0, int(R.gauss(base_fds if dia.weekday() >= 5 else base_util, 3)))
        if d == 0:
            n = int(n * 0.45)
        e = sum(1 for _ in range(n) if R.random() < erro_pct)
        h = sum(1 for _ in range(n) if R.random() < humano_pct)
        if n:
            linhas.append({"dia": dia.isoformat(), "n": n, "erros": e, "humano": h})
        if d < 14:
            for k in range(n):
                hh = R.randint(8, 19) if d else R.randint(8, ultima_h)
                q = dt.datetime.combine(dia, dt.time(hh, R.randint(0, 59)))
                if q <= AGORA:
                    evs.append({"quando": q.isoformat(), "ok": R.random() > erro_pct, "texto": ""})
    banco[f"{chave}.por_dia"] = linhas
    banco[f"{chave}.eventos"] = sorted(evs, key=lambda x: x["quando"], reverse=True)

por_dia("classificador", 40, 9, humano_pct=0.04)
por_dia("revisor", 60, 6, erro_pct=0.03, humano_pct=0.1, ultima_h=8)   # calado desde 8h: vira "atrasado"
por_dia("triagem", 25, 5, ultimo_dia=9)                                 # parou há 9 dias, flag desligada
banco["classificador.entrada"] = [{"dia": l["dia"], "n": l["n"]} for l in banco["classificador.por_dia"]]
json.dump(banco, open(os.path.join(EX, "banco-exemplo.json"), "w"), ensure_ascii=False, indent=0)
json.dump({"flag_classificador": True, "flag_revisor": True, "flag_triagem": False},
          open(os.path.join(EX, "flags-exemplo.json"), "w"))
print("exemplos gerados em", EX)
