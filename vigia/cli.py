"""Linha de comando do Vigia.

  python3 -m vigia gerar         [--config vigia.toml]   gera o painel (e copia para `copiar_para`)
  python3 -m vigia servir        [--config vigia.toml]   abre em http://127.0.0.1:<porta>
  python3 -m vigia checar-config [--config vigia.toml]   valida vigia.toml e agentes.d/*.toml
  python3 -m vigia novo-agente <id> [--fonte log_texto|jsonl|sql]   cria agentes.d/<id>.toml de modelo
  python3 -m vigia versao
  python3 -m vigia atualizar                             baixa a versão nova (git pull) e mostra o que mudou
O --config também pode vir de VIGIA_CONFIG.
"""
import argparse, datetime as dt, json, os, shutil, subprocess, sys
from . import __version__, config, historico, modelo, pagina
from .fontes import COLETORES
from .fontes.sql import carregar_env

_RAIZ = os.path.normpath(os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))


def _cfg(args):
    return args.config or os.environ.get("VIGIA_CONFIG") or "vigia.toml"


def gerar(caminho, registrar=True, quieto=False):
    geral, agentes, erros = config.carregar(caminho)
    if erros:
        for e in erros:
            print("config:", e, file=sys.stderr)
    carregar_env(geral.get("env_arquivo"))
    try:  # para avisar rotina que não está agendada
        r = subprocess.run(["crontab", "-l"], capture_output=True, text=True, timeout=10)
        geral["_crontab"] = r.stdout if r.returncode == 0 else None
    except (OSError, subprocess.SubprocessError):
        geral["_crontab"] = None
    agora = dt.datetime.fromisoformat(geral["agora"]) if geral.get("agora") else dt.datetime.now().replace(microsecond=0)
    if registrar and not geral.get("agora"):
        historico.registrar_vivo(geral, agora)
    coletas = {}
    for a in agentes:
        try:
            coletas[a["id"]] = COLETORES[a["fonte"]](a, geral, agora)
        except Exception as e:  # um agente com problema não derruba o painel
            print(f"{a['id']}: {e}", file=sys.stderr)
            coletas[a["id"]] = {"rodadas": [], "dias": {}, "eventos": [], "erro_fonte": str(e)[:200]}
    marcas = []
    if os.path.exists(geral["marcas"]):
        try:
            marcas = json.load(open(geral["marcas"], encoding="utf-8"))
        except ValueError:
            print("marcas.json inválido, ignorado", file=sys.stderr)
    dados = modelo.montar(geral, agentes, coletas, agora, __version__, marcas)
    if registrar and not geral.get("agora"):
        historico.salvar_dias(geral, agora, dados["itens"])
    html = pagina.render(dados, geral)
    os.makedirs(os.path.dirname(geral["saida"]) or ".", exist_ok=True)
    open(geral["saida"], "w", encoding="utf-8").write(html)
    for destino in geral["copiar_para"]:
        try:
            shutil.copy(geral["saida"], destino)
        except OSError as e:
            print(f"não copiei para {destino}: {e}", file=sys.stderr)
    if not quieto:
        falhas = [i["nome"] for i in dados["itens"] if i["st"] in ("er", "nr")]
        print(f"{geral['saida']} · {len(dados['itens'])} itens · {len(falhas)} com falha" + (f": {', '.join(falhas)}" if falhas else ""))
    return dados


MODELOS = {
    "log_texto": '''# Rotina que grava log de texto. Depois de editar: python3 -m vigia checar-config
nome = "{nome}"
area = "Minha área"
o_que = "O que esta rotina faz, em uma frase."
fonte = "log_texto"

[agenda]
cron = "0 9 * * *"          # o mesmo horário do crontab
rotulo = "todo dia 9h"
# desde = "2026-11-10 09:00" # opcional: antes disso não cobra rodada

[log]
arquivos = "/caminho/dos/logs/*.txt"
fim_rodada = 'exit=\\d+'      # linha que fecha uma rodada

[[regras]]                    # a primeira que casar decide
se = "hit your .*limit"
status = "falhou"
motivo = "Limite de uso atingido"
acao = "Volta sozinha na próxima rodada."
''',
    "jsonl": '''nome = "{nome}"
area = "Minha área"
o_que = "O que esta rotina faz."
fonte = "jsonl"
[agenda]
cron = "57 * * * *"
rotulo = "de hora em hora"
[log]
arquivos = "/caminho/execucoes.jsonl"
campo_hora = "hora"
''',
    "sql": '''nome = "{nome}"
area = "Minha área"
o_que = "O que este agente faz."
fonte = "sql"
volume_nome = "gravações por dia"
[sql]
conexao = "banco"
limite_erros_pct = 0
por_dia = \'\'\'
SELECT (criado_em AT TIME ZONE 'America/Sao_Paulo')::date AS dia, count(*) AS n,
       count(*) FILTER (WHERE erro IS NOT NULL) AS erros, 0 AS humano
FROM minha_tabela WHERE criado_em > now() - interval '35 days' GROUP BY 1
\'\'\'
eventos = \'\'\'
SELECT criado_em AS quando, (erro IS NULL) AS ok, coalesce(erro,'') AS texto
FROM minha_tabela WHERE criado_em > now() - interval '14 days' ORDER BY criado_em DESC LIMIT 300
\'\'\'
[flag]
chave = ""
''',
}


def main(argv=None):
    p = argparse.ArgumentParser(prog="vigia", description="Painel de rotinas e agentes.")
    p.add_argument("comando", choices=["gerar", "servir", "checar-config", "novo-agente", "versao", "atualizar"])
    p.add_argument("nome", nargs="?")
    p.add_argument("--config")
    p.add_argument("--fonte", default="log_texto", choices=list(MODELOS))
    a = p.parse_args(argv)

    if a.comando == "versao":
        print(__version__)
        return
    if a.comando == "atualizar":
        antes = __version__
        r = subprocess.run(["git", "-C", _RAIZ, "pull", "--ff-only", "--tags"], capture_output=True, text=True)
        print(r.stdout or r.stderr)
        depois = open(os.path.join(_RAIZ, "VERSION")).read().strip()
        if depois != antes:
            print(f"Atualizado de {antes} para {depois}. O que mudou:")
            log = open(os.path.join(_RAIZ, "CHANGELOG.md"), encoding="utf-8").read()
            print(log.split(f"## {antes}")[0][:3000])
        else:
            print(f"Já está na versão mais nova ({antes}).")
        return
    caminho = _cfg(a)
    if a.comando == "novo-agente":
        if not a.nome:
            sys.exit("use: vigia novo-agente <id>")
        geral, _, _ = config.carregar(caminho)
        destino = os.path.join(geral["base"], "agentes.d", f"{a.nome}.toml")
        if os.path.exists(destino):
            sys.exit(f"já existe: {destino}")
        os.makedirs(os.path.dirname(destino), exist_ok=True)
        open(destino, "w", encoding="utf-8").write(MODELOS[a.fonte].format(nome=a.nome))
        print(f"criado {destino} — edite e rode: python3 -m vigia checar-config")
        return
    if a.comando == "checar-config":
        try:
            geral, agentes, erros = config.carregar(caminho)
        except config.ErroConfig as e:
            sys.exit(str(e))
        for ag in agentes:
            print(f"  {ag['id']:<22} {ag['fonte']:<10} {ag['nome']}")
        if erros:
            print("\nProblemas:")
            for e in erros:
                print("  -", e)
            sys.exit(1)
        print(f"\nok: {len(agentes)} agentes, meta {geral['meta']:.0%}, tema {geral['tema']}")
        return
    if a.comando == "gerar":
        gerar(caminho)
        return
    if a.comando == "servir":
        from .servidor import servir
        geral, _, _ = config.carregar(caminho)
        servir(geral, lambda: gerar(caminho, quieto=True))


if __name__ == "__main__":
    main()
