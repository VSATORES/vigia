"""Aviso quando um item MUDA de estado (falhou/não rodou, ou voltou ao normal). Nunca repete a cada geração.

No vigia.toml:
  [notificar]
  comando = "python3 /caminho/enviar.py {arquivo}"   # {arquivo} = texto do aviso entre <!-- INICIO --> e <!-- FIM -->
  link = "http://localhost:8787"
  ao_voltar = true
Desligar só nesta execução: variável VIGIA_SEM_AVISO=1.
"""
import datetime as dt, os, shlex, subprocess, tempfile
from . import estado

RUIM = ("er", "nr")


def mensagens(dados, anterior):
    """-> (lista de (id, texto), novo mapa id->st). Primeira vez (anterior None) só memoriza."""
    atual = {i["k"]: i["st"] for i in dados["itens"]}
    if anterior is None:
        return [], atual
    out = []
    for i in dados["itens"]:
        antes, agora = anterior.get(i["k"]), i["st"]
        if agora in RUIM and antes not in RUIM:
            out.append((i["k"], "quebrou", i))
        elif antes in RUIM and agora in ("ok", "off", "none", "pause"):
            out.append((i["k"], "voltou", i))
    return out, atual


def texto(evs, dados, link):
    hora = dt.datetime.fromisoformat(dados["gerado"]).strftime("%d/%m %Hh%M")
    blocos = [f"**{dados.get('titulo', 'Vigia')} · {hora}**"]
    for _, tipo, i in evs:
        if tipo == "quebrou":
            acao = (i.get("acao") or "").replace("<b>", "").replace("</b>", "").replace("<code>", "`").replace("</code>", "`")
            blocos.append(f"**Problema:** {i['nome']} — {i['motivo']}\n**Contexto:** {i.get('area', '')} · última {i.get('ult', '—')}\n"
                          f"**Resolução:** nenhuma ainda (o Vigia só avisou)\n**Sua ação:** {acao or 'abrir o painel e ver o registro'}"
                          + (f"\n{link}#agentes/{i['k']}" if link else ""))
        else:
            blocos.append(f"**Voltou ao normal:** {i['nome']} — {i['motivo']}\n**Sua ação:** nenhuma")
    return "\n\n".join(blocos)


def verificar(geral, dados):
    cfg = geral.get("notificar") or {}
    d = estado.ler(geral)
    evs, atual = mensagens(dados, d.get("notificado"))
    if not cfg.get("ao_voltar", True):
        evs = [e for e in evs if e[1] == "quebrou"]
    enviado = None
    if evs and cfg.get("comando") and os.environ.get("VIGIA_SEM_AVISO") != "1":
        f = tempfile.NamedTemporaryFile("w", suffix=".md", delete=False, encoding="utf-8")
        f.write("<!-- INICIO -->\n" + texto(evs, dados, cfg.get("link", "")) + "\n<!-- FIM -->\n")
        f.close()
        cmd = cfg["comando"].replace("{arquivo}", shlex.quote(f.name))
        try:
            r = subprocess.run(["bash", "-c", cmd], capture_output=True, text=True, timeout=120)
            enviado = r.returncode == 0
        except subprocess.SubprocessError:
            enviado = False
        finally:
            os.unlink(f.name)
        if not enviado:
            return {"eventos": len(evs), "enviado": False}  # não memoriza: tenta de novo na próxima geração
    d["notificado"] = atual
    estado.gravar(geral, d)
    return {"eventos": len(evs), "enviado": enviado}
