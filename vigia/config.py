"""Configuração do Vigia: `vigia.toml` (geral) + `agentes.d/*.toml` (um arquivo por agente).

Adicionar ou mudar um agente = editar/criar um .toml; nada de código. `vigia checar-config` valida tudo
e aponta o arquivo e o campo com problema. Caminhos relativos valem a partir da pasta do vigia.toml.
"""
import glob, os, re, tomllib
from .cronexpr import Cron

FONTES = ("log_texto", "jsonl", "sql")
STATUS_REGRA = ("ok", "falhou", "rodando", "sem_novidade")


class ErroConfig(Exception):
    pass


def _abs(base, p):
    if not p:
        return p
    p = os.path.expanduser(os.path.expandvars(p))
    return p if os.path.isabs(p) else os.path.normpath(os.path.join(base, p))


def carregar(caminho):
    """-> (geral: dict, agentes: list[dict], erros: list[str])"""
    caminho = os.path.abspath(caminho)
    base = os.path.dirname(caminho)
    erros = []
    try:
        with open(caminho, "rb") as f:
            g = tomllib.load(f)
    except FileNotFoundError:
        raise ErroConfig(f"não achei {caminho}")
    except tomllib.TOMLDecodeError as e:
        raise ErroConfig(f"{caminho}: TOML inválido ({e})")

    geral = {
        "base": base,
        "titulo": g.get("titulo", "Vigia"),
        "subtitulo": g.get("subtitulo", ""),
        "meta": float(g.get("meta", 0.95)),
        "margem_atraso_min": int(g.get("margem_atraso_min", 10)),
        "porta": int(g.get("porta", 8787)),
        "tema": g.get("tema", "neutro"),
        "copiar_para": [_abs(base, p) for p in g.get("copiar_para", [])],
        "saida": _abs(base, g.get("saida", "painel.html")),
        "historico": _abs(base, g.get("historico", "dados/historico")),
        "marcas": _abs(base, g.get("marcas", "marcas.json")),
        "vivo": [_abs(base, p) for p in g.get("vivo", {}).get("arquivos", [])],
        "conexoes": g.get("conexoes", {}),
        "env_arquivo": _abs(base, g.get("env_arquivo", "")),
        "agora": g.get("agora"),  # só para demo/teste: fixa o "agora"
        "repo": g.get("repo", ""),
        "avisos": g.get("avisos", []),
        "dados": _abs(base, g.get("dados", "dados")),
        "notificar": g.get("notificar", {}),
        "claude": g.get("claude", "claude"),
    }
    if not 0 < geral["meta"] <= 1:
        erros.append(f"vigia.toml: meta deve estar entre 0 e 1 (ex.: 0.95), veio {geral['meta']}")

    pasta = _abs(base, g.get("agentes", "agentes.d"))
    arquivos = sorted(glob.glob(os.path.join(pasta, "*.toml")))
    if not arquivos:
        erros.append(f"nenhum agente em {pasta}/*.toml")
    agentes, ids = [], set()
    for arq in arquivos:
        nome = os.path.basename(arq)
        try:
            with open(arq, "rb") as f:
                a = tomllib.load(f)
        except tomllib.TOMLDecodeError as e:
            erros.append(f"{nome}: TOML inválido ({e})")
            continue
        if a.get("ativo", True) is False:
            continue
        a["_arquivo"] = arq
        a.setdefault("id", os.path.splitext(nome)[0])
        for campo in ("nome", "fonte"):
            if not a.get(campo):
                erros.append(f"{nome}: falta o campo '{campo}'")
        if a.get("fonte") and a["fonte"] not in FONTES:
            erros.append(f"{nome}: fonte '{a['fonte']}' não existe (use {', '.join(FONTES)})")
        if a["id"] in ids:
            erros.append(f"{nome}: id '{a['id']}' repetido")
        ids.add(a["id"])
        a.setdefault("tipo", "agente" if a.get("fonte") == "sql" else "rotina")
        a.setdefault("area", "")
        a.setdefault("o_que", "")
        ag = a.setdefault("agenda", {})
        if ag.get("cron"):
            try:
                ag["_cron"] = Cron(ag["cron"])
            except ValueError as e:
                erros.append(f"{nome}: agenda.cron inválido — {e}")
        elif a.get("fonte") in ("log_texto", "jsonl"):
            erros.append(f"{nome}: rotina precisa de agenda.cron (ex.: '30 8 * * *')")
        if a.get("fonte") in ("log_texto", "jsonl"):
            lg = a.get("log", {})
            if not lg.get("arquivos"):
                erros.append(f"{nome}: falta log.arquivos (caminho ou padrão, ex.: 'logs/*.txt')")
            else:
                lg["arquivos"] = _abs(base, lg["arquivos"])
            for i, r in enumerate(a.get("regras", [])):
                if "se" not in r or "status" not in r:
                    erros.append(f"{nome}: regras[{i}] precisa de 'se' (texto/regex) e 'status'")
                elif r["status"] not in STATUS_REGRA:
                    erros.append(f"{nome}: regras[{i}].status '{r['status']}' inválido ({', '.join(STATUS_REGRA)})")
                else:
                    try:
                        re.compile(r["se"])
                    except re.error as e:
                        erros.append(f"{nome}: regras[{i}].se não é regex válida ({e})")
        ac = a.get("acoes", {})
        if ac and not isinstance(ac, dict):
            erros.append(f"{nome}: [acoes] precisa ser uma seção (rodar, instrucoes, ferramentas)")
        elif ac.get("rodar") is not None and not str(ac["rodar"]).strip():
            erros.append(f"{nome}: acoes.rodar vazio")
        elif ac.get("instrucoes"):
            ac["instrucoes"] = _abs(base, ac["instrucoes"])
        if a.get("fonte") == "sql":
            s = a.get("sql", {})
            if not s.get("conexao"):
                erros.append(f"{nome}: falta sql.conexao")
            elif s["conexao"] not in geral["conexoes"]:
                erros.append(f"{nome}: conexão '{s['conexao']}' não está em [conexoes] do vigia.toml")
            if not s.get("por_dia"):
                erros.append(f"{nome}: falta sql.por_dia (SELECT com colunas dia, n, erros)")
            for k in ("por_dia", "eventos"):
                q = s.get(k, "")
                if q and not re.match(r"\s*(with|select)\b", q, re.I):
                    erros.append(f"{nome}: sql.{k} precisa ser só leitura (começar com SELECT/WITH)")
        agentes.append(a)
    return geral, agentes, erros
