"""Aviso quando um item MUDA de estado (falhou/não rodou, ou voltou ao normal). Nunca repete a cada geração.

No vigia.toml:
  [notificar]
  comando = "python3 /caminho/enviar.py {arquivo}"   # {arquivo} = texto do aviso entre <!-- INICIO --> e <!-- FIM -->
  link = "http://localhost:8787"
  ao_voltar = true
Desligar só nesta execução: variável VIGIA_SEM_AVISO=1.

Computador desligado (12/11): rotina que perdeu o horário porque o PC estava desligado não muda o estado do item
(fica "pc" no dia), então antes ninguém era avisado. Agora, quando o PC volta, vai UM aviso com o que se perdeu
(hoje e ontem), uma vez só por horário (estado.json -> "pc_avisado").
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


def perdidas(dados):
    """-> {chave: (nome, data, hhmm)} dos horários de hoje e ontem perdidos com o PC desligado (célula "pc")."""
    gerado = dt.datetime.fromisoformat(dados["gerado"])
    out = {}
    for i in dados["itens"]:
        if i.get("st") == "pause":
            continue
        for idx in ("0", "1"):
            data = (gerado.date() - dt.timedelta(days=int(idx))).isoformat()
            for r in (i.get("rodadas") or {}).get(idx, []):
                if len(r) > 1 and r[1] == "pc":
                    out[f"{i['k']}|{data}|{r[0]}"] = (i["nome"], data, r[0])
    return out


def texto_pc(novas):
    por_item = {}
    for nome, data, hhmm in sorted(novas.values(), key=lambda x: (x[0], x[1], x[2])):
        por_item.setdefault(nome, []).append((data, hhmm))
    linhas = []
    for nome, hs in por_item.items():
        dia = lambda d: dt.date.fromisoformat(d).strftime("%d/%m")
        if len(hs) <= 3:
            quando = ", ".join(f"{dia(d)} {h}" for d, h in hs)
        else:
            quando = f"{len(hs)} horários, de {dia(hs[0][0])} {hs[0][1]} a {dia(hs[-1][0])} {hs[-1][1]}"
        linhas.append(f"• {nome}: {quando}")
    return ("**Computador desligado:** estas rotinas não rodaram no horário porque o PC estava desligado.\n"
            + "\n".join(linhas)
            + "\n**Sua ação:** rodar à mão as que importam hoje (botão Rodar no Vigia); as que repetem no dia voltam sozinhas.")


def texto(evs, dados, link, pc_novas=None):
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
    if pc_novas:
        blocos.append(texto_pc(pc_novas) + (f"\n{link}" if link else ""))
    return "\n\n".join(blocos)


def verificar(geral, dados):
    cfg = geral.get("notificar") or {}
    d = estado.ler(geral)
    evs, atual = mensagens(dados, d.get("notificado"))
    if not cfg.get("ao_voltar", True):
        evs = [e for e in evs if e[1] == "quebrou"]
    pc_atual = perdidas(dados)
    pc_antes = d.get("pc_avisado")
    pc_novas = {} if pc_antes is None else {k: v for k, v in pc_atual.items() if k not in set(pc_antes)}
    enviado = None
    if (evs or pc_novas) and cfg.get("comando") and os.environ.get("VIGIA_SEM_AVISO") != "1":
        f = tempfile.NamedTemporaryFile("w", suffix=".md", delete=False, encoding="utf-8")
        f.write("<!-- INICIO -->\n" + texto(evs, dados, cfg.get("link", ""), pc_novas) + "\n<!-- FIM -->\n")
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
            return {"eventos": len(evs), "pc": len(pc_novas), "enviado": False}  # não memoriza: tenta de novo
    d["notificado"] = atual
    d["pc_avisado"] = sorted(pc_atual)  # só hoje e ontem: a lista se limpa sozinha
    estado.gravar(geral, d)
    return {"eventos": len(evs), "pc": len(pc_novas), "enviado": enviado}
