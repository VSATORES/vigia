"""Rotinas que escrevem log de texto (um arquivo por dia ou por rodada).

Configuração no agente (.toml):
  [log]
  arquivos = "logs/*.txt"                      # padrão glob
  data_no_nome = '(\\d{4}-\\d{2}-\\d{2})(?:-(\\d{2})h)?'   # opcional: data (e hora) no nome do arquivo
  fim_rodada = 'exit=\\d+'                     # linha que fecha uma rodada (várias rodadas no mesmo arquivo)
  volume = '(\\d+) ok'                         # opcional: número que a rodada produziu
  postou = '"ok":\\s*true'                     # opcional: prova de que a rodada entregou algo (ver abaixo)
  [[regras]]                                   # a primeira que casar decide; motivo aceita \\1
  se = "hit your .*limit"
  status = "falhou"
  motivo = "Limite de uso atingido"
Sem regra que case: usa o último exit=N (0 = ok).

Leitura de cada rodada:
- fim_rodada e regras valem linha a linha: '^' e '$' casam no começo/fim de cada linha (não precisa de (?m)).
- Hora: saída do `date`, ISO (AAAA-MM-DD HH:MM:SS) ou só HH:MM[:SS] no começo ou no fim da linha; a hora sem
  data ganha a data do nome do arquivo (ou a do arquivo). Carimbo depois da última gravação do arquivo
  (ex.: validade de login dentro de uma mensagem) não é hora de rodada e é ignorado.
- Começo: carimbo numa das 2 primeiras linhas da rodada (linha com exit=N não conta). Com começo, a rodada é do
  cron se começou até min(10 min, metade do intervalo) depois de um horário; sem começo, se terminou até
  `duracao_max_min` depois de um horário ainda não usado (e não antes da hora do nome do arquivo). Senão, à mão.
- Regra com status "sem_novidade" não vale se a rodada postou (casou `postou`; padrão: resposta de envio com
  "successful": true). Use postou = "" para desligar.
"""
import datetime as dt, glob, os, re

MESES = {m: i for i, m in enumerate("Jan Feb Mar Apr May Jun Jul Aug Sep Oct Nov Dec".split(), 1)}
RE_DATE = re.compile(r"\b\w{3} (\w{3})\s+(\d{1,2}) (\d{2}):(\d{2}):(\d{2}) \S+ (\d{4})")
RE_ISO = re.compile(r"\b(\d{4}-\d{2}-\d{2})[T ](\d{2}:\d{2}:\d{2})")
RE_HORA_INI = re.compile(r"^\s*\[?([01]\d|2[0-3]):([0-5]\d)(?::([0-5]\d))?\]?(?=\s|$)")
RE_HORA_FIM = re.compile(r"(?<![\d:/.\-])([01]\d|2[0-3]):([0-5]\d)(?::([0-5]\d))?\s*$")
RE_EXIT = re.compile(r"\bexit=\d")
POSTOU_PADRAO = r'"successful":\s*true'
FOLGA = dt.timedelta(minutes=2)  # relógio: carimbo até 2 min depois do mtime ainda vale


def _completas(ln):
    """datas completas na linha, na ordem em que aparecem."""
    out = []
    for m in RE_DATE.finditer(ln):
        mo, d, h, mi, s, y = m.groups()
        try:
            out.append((m.start(), dt.datetime(int(y), MESES.get(mo, 1), int(d), int(h), int(mi), int(s))))
        except ValueError:
            pass
    for m in RE_ISO.finditer(ln):
        try:
            out.append((m.start(), dt.datetime.fromisoformat(f"{m.group(1)} {m.group(2)}")))
        except ValueError:
            pass
    return [t for _, t in sorted(out)]


def _so_hora(m, dia):
    return dt.datetime.combine(dia, dt.time(int(m.group(1)), int(m.group(2)), int(m.group(3) or 0)))


def carimbos(ln, dia=None, limite=None, fim_de_linha=True):
    """horas escritas na linha, válidas (não depois de `limite`). Hora sem data usa `dia`."""
    ok = lambda t: limite is None or t <= limite + FOLGA  # noqa: E731
    out = [t for t in _completas(ln) if ok(t)]
    if not out and dia is not None:
        for rx in ((RE_HORA_INI, RE_HORA_FIM) if fim_de_linha else (RE_HORA_INI,)):
            m = rx.search(ln)
            if m:
                t = _so_hora(m, dia)
                if ok(t):
                    out.append(t)
                break
    return out


def hora_no_texto(txt, dia=None, limite=None):
    """última data/hora completa escrita no texto (saída do `date` ou ISO). Hora solta (HH:MM) no meio do texto
    pode ser conteúdo (ex.: "08:30 card aberto"), então só vale na linha de fim ou no começo da rodada."""
    ok = lambda t: limite is None or t <= limite + FOLGA  # noqa: E731
    for ln in reversed(txt.splitlines()):
        c = [t for t in _completas(ln) if ok(t)]
        if c:
            return max(c)
    return None


def _pedacos(txt, fim_re, mtime=None, dia=None):
    """divide o arquivo em rodadas -> [(texto, linha_de_fim ou None)]. Cada rodada termina numa linha que casa
    fim_re (linha a linha). Linhas que sobram logo depois do fim (ex.: "copiado para Downloads") são da rodada
    anterior, não uma rodada nova: o arquivo não foi mexido mais de 10 min depois do último fim."""
    if not fim_re:
        return [(txt, None)]
    rx = re.compile(fim_re, re.M)
    atual, out = [], []
    for ln in txt.splitlines():
        atual.append(ln)
        if rx.search(ln):
            out.append(["\n".join(atual), ln])
            atual = []
    if any(x.strip() for x in atual):
        resto = "\n".join(atual)
        fim_ant = hora_no_texto(out[-1][0], dia, mtime) if out else None
        if out and fim_ant and mtime and (mtime - fim_ant) <= dt.timedelta(minutes=10) \
                and not hora_no_texto(resto, dia, mtime):
            out[-1][0] += "\n" + resto
        else:
            out.append([resto, None])
    return [tuple(p) for p in out] or [(txt, None)]


def _inicio(texto, dia, limite):
    n = 0
    for ln in texto.splitlines():
        if not ln.strip():
            continue
        n += 1
        if n > 2:
            break
        if RE_EXIT.search(ln):
            continue
        c = carimbos(ln, dia, limite, fim_de_linha=False)
        if c:
            return c[0]
    return None


def _fim(texto, linha_fim, dia, limite):
    """-> (hora de fim, veio da própria linha de fim?)"""
    c = carimbos(linha_fim, dia, limite)
    return (max(c), True) if c else (hora_no_texto(texto, dia, limite), False)  # a mais recente; a outra é referência


_TOL = {}


def _tolerancia(cron, prog):
    chave = (cron.expr, prog)
    if chave not in _TOL:
        _TOL[chave] = _tol(cron, prog)
    return _TOL[chave]


def _tol(cron, prog):
    prox = cron.proximo(prog)
    gap = (prox - prog) if prox else dt.timedelta(days=1)
    return min(dt.timedelta(minutes=10), gap / 2)


def avaliar(texto, regras, fechou, postou=POSTOU_PADRAO):
    postou_ok = bool(postou) and re.search(postou, texto, re.I) is not None
    for r in regras:
        if r["status"] == "sem_novidade" and postou_ok:
            continue  # rodada que entregou algo nunca é "sem novidade"
        m = re.search(r["se"], texto, re.I | re.S | re.M)
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
    postou = lg.get("postou", POSTOU_PADRAO)
    dur_max = dt.timedelta(minutes=int(agente["agenda"].get("duracao_max_min", 90)))
    rodadas, usados = [], set()  # usados: horários do cron já atribuídos a uma rodada
    for arq in sorted(glob.glob(lg["arquivos"])):
        try:
            with open(arq, encoding="utf-8", errors="replace") as f:
                txt = f.read()
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
            except (ValueError, IndexError):
                pass
        dia = (dia_nome or mtime).date()
        for pedaco, linha_fim in _pedacos(txt, fim_re, mtime, dia):
            fechou = linha_fim is not None
            fim, fim_na_linha = _fim(pedaco, linha_fim, dia, mtime) if fechou else (None, False)
            inicio = _inicio(pedaco, dia, mtime)
            if inicio and fim and inicio > fim:
                inicio = None
            manual, prog = False, None
            if cron:
                if inicio:
                    prog = cron.anterior(inicio)
                    agendada = prog is not None and inicio - prog <= _tolerancia(cron, prog)
                else:
                    ref = fim or mtime
                    prog = cron.anterior(ref)
                    agendada = prog is not None and ref - prog <= dur_max \
                        and not (hora_nome and prog < hora_nome)
                if agendada and dia_nome and prog.date() != dia_nome.date():
                    agendada = False  # arquivo de outro dia (ex.: mexido depois) não ocupa horário de hoje
                if agendada and prog in usados:
                    agendada = False
                if agendada:
                    usados.add(prog)
                manual = not agendada
            if inicio:
                ini = inicio
            elif cron and not manual:
                ini = prog
            else:
                ini = fim or mtime
            st, motivo = avaliar(pedaco, regras, fechou, postou)
            if st == "rodando" and (agora - (fim or mtime)) > dt.timedelta(hours=3):
                st, motivo = "falhou", "Log terminou sem fechar a rodada (travou ou foi interrompida)"
            sabe_ini = inicio is not None or (cron and not manual)
            dur = (fim - ini).total_seconds() if (fim and sabe_ini and fim >= ini) else None
            if dur == 0 and inicio and not fim_na_linha:
                dur = None  # só um carimbo (o de começo): não dá para saber quanto durou
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
