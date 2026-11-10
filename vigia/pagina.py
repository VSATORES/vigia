"""Monta o HTML final: modelo da página + tema (cores, fonte, marca) + dados embutidos."""
import json, os

_AQUI = os.path.dirname(os.path.abspath(__file__))
_RAIZ = os.path.normpath(os.path.join(_AQUI, ".."))


def pasta_tema(geral):
    t = geral.get("tema", "neutro")
    for c in (t, os.path.join(geral["base"], t), os.path.join(_RAIZ, "temas", t)):
        if os.path.isdir(c) and os.path.exists(os.path.join(c, "tema.css")):
            return c
    return os.path.join(_RAIZ, "temas", "neutro")


def _ler(p, padrao=""):
    try:
        return open(p, encoding="utf-8").read()
    except OSError:
        return padrao


def render(dados, geral):
    tema = pasta_tema(geral)
    html = _ler(os.path.join(_AQUI, "pagina", "base.html"))
    js = json.dumps(dados, ensure_ascii=False, default=str).replace("</", "<\\/")
    titulo = (dados.get("titulo") or "Vigia").replace("<", "&lt;")
    return (html.replace("__TEMA_HEAD__", _ler(os.path.join(tema, "head.html")))
                .replace("__TEMA_CSS__", _ler(os.path.join(tema, "tema.css")))
                .replace("__MARCA__", _ler(os.path.join(tema, "marca.html")).strip())
                .replace("__TITULO__", titulo)
                .replace("__DADOS__", js))
