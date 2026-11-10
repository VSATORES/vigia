"""Rotinas que escrevem log de texto (um arquivo por dia ou por rodada).

Configuração no agente (.toml):
  [log]
  arquivos = "logs/*.txt"                      # padrão glob
  data_no_nome = '(\\d{4}-\\d{2}-\\d{2})(?:-(\\d{2})h)?'   # opcional: data (e hora) no nome do arquivo
  fim_rodada = 'exit=\\d+'                     # linha que fecha uma rodada (várias rodadas no mesmo arquivo)
  volume = '(\\d+) ok'                         # opcional: número que a rodada produziu
  [[regras]]                                   # a primeira que casar decide; motivo aceita \\1
  se = "hit your .*limit"
  status = "falhou"
  motivo = "Limite de uso atingido"
Sem regra que case: usa o último exit=N (0 = ok).
"""
import datetime as dt, glob, os, re

MESES = {m: i for i, m in enumerate("Jan Feb Mar Apr May Jun Jul Aug Sep Oct Nov Dec".split(), 1)}
RE_DATE = re.compile(r"\b\w{3} (\w{3})\s+(\d{1,2}) (\d{2}):(\d{2}):(\d{2}) \S+ (\d{4})")
RE_ISO = re.compile(r"\b(\d{4}-\d{2}-\d{2})[T ](\d{2}:\d{2}:\d{2})")


def hora_no_texto(txt):
    """última data/hora escrita no texto (saída do `date` ou ISO)."""
    ms = list(RE_DATE.finditer(txt))
    if ms:
        mo, d, h, mi, s, y = ms[-1].groups()
        return dt.datetime(int(y), MESES.get(mo, 1), int(d), int(h), int(mi), int(s))
    ms = list(RE_ISO.finditer(txt))
    if ms:
        return dt.datetime.fromisoformat(f"{ms[-1].group(1)} {ms[-1].group(2)}")
    return None


def _pedacos(txt, fim_re):
    """divide o arquivo em rodadas: cada pedaço termina numa linha que casa fim_re."""
    if not fim_re:
        return [txt]
    linhas, atual, out = txt.splitlines(), [], []
    for ln in linhas:
        atual.append(ln)
        if re.search(fim_re, ln):
            out.append("\n".join(atual))
            atual = []
    if any(x.strip() for x in atual):
        out.append("\n".join(atual))
    return out or [txt]


def avaliar(texto, regras, fechou):
    for r in regras:
        m = re.search(r["se"], texto, re.I | re.S)
        if m:
            motivo = r.get("motivo") or r["se"]
            try:
                motivo = m.expand(motivo)
            except (re.error, IndexError):
                pass
            return r["status"], motivo.strip()
    ex = re.findall(r"exit=(\d+)", texto)
    if ex:
        return ("ok", "Terminou bem") if ex[-1] == "0" else ("falhou", f"Terminou com erro (exit={ex[-1]})")
    if not fechou:
        return "rodando", "Em andamento"
    return "ok", "Terminou"


def coletar(agente, geral, agora):
    lg = agente["log"]
    cron = agente["agenda"].get("_cron")
    regras = agente.get("regras", [])
    re_nome = lg.get("data_no_nome", r"(\d{4}-\d{2}-\d{2})(?:-(\d{2})h)?")
    fim_re = lg.get("fim_rodada", r"exit=\d+")
    dur_max = int(agente["agenda"].get("duracao_max_min", 90))
    rodadas = []
    for arq in sorted(glob.glob(lg["arquivos"])):
        try:
            txt = open(arq, encoding="utf-8", errors="replace").read()
        except OSError:
            continue
        mtime = dt.datetime.fromtimestamp(os.path.getmtime(arq))
        m = re.search(re_nome, os.path.basename(arq)) if re_nome else None
        dia_nome = hora_nome = None
        if m:
            try:
                dia_nome = dt.datetime.strptime(m.group(1), "%Y-%m-%d")
                if m.lastindex and m.lastindex >= 2 and m.group(2):
                    hora_nome = dia_nome.replace(hour=int(m.group(2)))
            except ValueError:
                pass
        for i, pedaco in enumerate(_pedacos(txt, fim_re)):
            fechou = bool(fim_re and re.search(fim_re, pedaco))
            fim = hora_no_texto(pedaco) if fechou else None
            manual = False
            if i == 0 and hora_nome:
                ini = hora_nome
            else:
                ref = fim or mtime
                prog = cron.anterior(ref) if cron else None
                # é rodada agendada só se terminou até `duracao_max_min` depois do horário; senão foi à mão
                if prog and i == 0 and (ref - prog) <= dt.timedelta(minutes=dur_max):
                    ini = prog
                else:
                    ini, manual = ref, True
            st, motivo = avaliar(pedaco, regras, fechou)
            if st == "rodando" and (agora - (fim or mtime)) > dt.timedelta(hours=3):
                st, motivo = "falhou", "Log terminou sem fechar a rodada (travou ou foi interrompida)"
            dur = None if manual else ((fim - ini).total_seconds() if fim and fim >= ini else None)
            vol = None
            if lg.get("volume"):
                vm = re.findall(lg["volume"], pedaco)
                if vm:
                    try:
                        vol = int(vm[-1] if isinstance(vm[-1], str) else vm[-1][0])
                    except ValueError:
                        pass
            rodadas.append({"ini": ini, "fim": fim, "dur": dur, "status": st, "motivo": motivo,
                            "trecho": "\n".join(pedaco.strip().splitlines()[-25:]), "arquivo": arq,
                            "volume": vol, "manual": manual})
    rodadas.sort(key=lambda r: r["ini"])
    return {"rodadas": rodadas}
