"""Aparência da aba Aprovação: tema (cores, fonte, cantos) e papel de parede, escolhidos em [aparencia] no vigia.toml.

[aparencia]
tema = "oficina"          # um dos TEMAS abaixo
papel = "mar"             # nada | mar | por | folhas | grade | caminho de uma imagem local
forca = 22                # 0 a 60: quanto o papel de parede aparece atrás dos slides
"""
import os

TEMAS = {'oficina': {'nome': 'Oficina',
             'desc': 'O padrão: grafite, azulejo e a etiqueta amarela da ordem de serviço.',
             'fonte': 'Archivo',
             'escuro': False,
             'raio': '10px',
             'fundo': '#EEF2F1',
             'superficie': '#FFFFFF',
             'superficie2': '#F6F8F7',
             'linha': '#D9E0DE',
             'tinta': '#1A1F24',
             'tinta2': '#4A5560',
             'lateral': '#1C232B',
             'lateral_tinta': '#E8EDF0',
             'destaque': '#F4C430',
             'destaque_tinta': '#1A1F24',
             'ok': '#1F7A52',
             'alerta': '#B4462E',
             'ok_tinta': '#FFFFFF'},
 'noturno': {'nome': 'Noturno',
             'desc': 'Escuro de verdade, para quem aprova à noite ou passa o dia no terminal.',
             'fonte': 'Archivo',
             'escuro': True,
             'raio': '10px',
             'fundo': '#12171C',
             'superficie': '#1B2229',
             'superficie2': '#222B33',
             'linha': '#2E3842',
             'tinta': '#E6ECEF',
             'tinta2': '#9AA7B2',
             'lateral': '#0C1014',
             'lateral_tinta': '#C9D3DA',
             'destaque': '#F4C430',
             'destaque_tinta': '#12171C',
             'ok': '#4CC38A',
             'alerta': '#F07A5F',
             'ok_tinta': '#12171C'},
 'temporada': {'nome': 'Temporada',
               'desc': 'Areia, mar e sol: o assunto da casa (imóvel de temporada).',
               'fonte': 'Nunito Sans',
               'escuro': False,
               'raio': '16px',
               'fundo': '#F5EFE4',
               'superficie': '#FFFDF8',
               'superficie2': '#FBF5EA',
               'linha': '#E6DAC4',
               'tinta': '#1F2E35',
               'tinta2': '#5B6B70',
               'lateral': '#0E5E6F',
               'lateral_tinta': '#E3F2F1',
               'destaque': '#FF8A3D',
               'destaque_tinta': '#FFFFFF',
               'ok': '#1E8A6E',
               'alerta': '#C2412D',
               'ok_tinta': '#FFFFFF'},
 'prancheta': {'nome': 'Prancheta',
               'desc': 'Papel de projeto azul, linhas finas, cara de engenharia e manutenção.',
               'fonte': 'IBM Plex Sans',
               'escuro': False,
               'raio': '4px',
               'fundo': '#E9F0F8',
               'superficie': '#FFFFFF',
               'superficie2': '#F3F7FC',
               'linha': '#C5D5E8',
               'tinta': '#0F2A4A',
               'tinta2': '#4C6585',
               'lateral': '#123B6B',
               'lateral_tinta': '#DCE8F6',
               'destaque': '#2F7DE1',
               'destaque_tinta': '#FFFFFF',
               'ok': '#167A5B',
               'alerta': '#C2402F',
               'ok_tinta': '#FFFFFF'},
 'jardim': {'nome': 'Jardim',
            'desc': 'Verde musgo e papel, calmo para um dia cheio de decisões.',
            'fonte': 'Fraunces',
            'escuro': False,
            'raio': '12px',
            'fundo': '#EEF1E8',
            'superficie': '#FBFCF7',
            'superficie2': '#F3F6EC',
            'linha': '#D6DDC9',
            'tinta': '#1E2A1F',
            'tinta2': '#56644F',
            'lateral': '#2E4A33',
            'lateral_tinta': '#E5EEDD',
            'destaque': '#C9A227',
            'destaque_tinta': '#1E2A1F',
            'ok': '#2F7A3E',
            'alerta': '#B04A2F',
            'ok_tinta': '#FFFFFF'},
 'fliperama': {'nome': 'Fliperama',
               'desc': 'Roxo e neon, para quem quer que aprovar pareça jogo.',
               'fonte': 'Space Grotesk',
               'escuro': True,
               'raio': '14px',
               'fundo': '#17112B',
               'superficie': '#221A3D',
               'superficie2': '#2A2149',
               'linha': '#3A2F60',
               'tinta': '#F2EEFF',
               'tinta2': '#A99CD6',
               'lateral': '#0F0A1F',
               'lateral_tinta': '#D9D0FF',
               'destaque': '#3DF5C4',
               'destaque_tinta': '#17112B',
               'ok': '#3DF5C4',
               'alerta': '#FF5C93',
               'ok_tinta': '#17112B'},
 'cafe': {'nome': 'Café',
          'desc': 'Marrom quente e creme, aconchegante, sem cansar a vista.',
          'fonte': 'Archivo',
          'escuro': False,
          'raio': '10px',
          'fundo': '#F2EBE3',
          'superficie': '#FFFBF6',
          'superficie2': '#F8F1E8',
          'linha': '#E2D4C3',
          'tinta': '#2B1D14',
          'tinta2': '#6E5948',
          'lateral': '#3B2719',
          'lateral_tinta': '#F0E3D4',
          'destaque': '#D9822B',
          'destaque_tinta': '#FFFFFF',
          'ok': '#3F7D4E',
          'alerta': '#B23A2A',
          'ok_tinta': '#FFFFFF'},
 'papel': {'nome': 'Papel',
           'desc': 'Branco e preto, nada além do necessário.',
           'fonte': 'Inter Tight',
           'escuro': False,
           'raio': '6px',
           'fundo': '#FAFAFA',
           'superficie': '#FFFFFF',
           'superficie2': '#F4F4F4',
           'linha': '#E3E3E3',
           'tinta': '#111111',
           'tinta2': '#5E5E5E',
           'lateral': '#FFFFFF',
           'lateral_tinta': '#111111',
           'destaque': '#111111',
           'destaque_tinta': '#FFFFFF',
           'ok': '#1D7A48',
           'alerta': '#C0392B',
           'ok_tinta': '#FFFFFF'},
 'contraste': {'nome': 'Alto contraste',
               'desc': 'Contraste máximo e uma fonte feita para leitura fácil.',
               'fonte': 'Atkinson Hyperlegible',
               'escuro': True,
               'raio': '8px',
               'fundo': '#000000',
               'superficie': '#0D0D0D',
               'superficie2': '#1A1A1A',
               'linha': '#FFFFFF',
               'tinta': '#FFFFFF',
               'tinta2': '#F0F0F0',
               'lateral': '#000000',
               'lateral_tinta': '#FFFFFF',
               'destaque': '#FFE500',
               'destaque_tinta': '#000000',
               'ok': '#5CFF9D',
               'alerta': '#FF7A7A',
               'ok_tinta': '#000000'}}

PAPEIS = {
    "mar": "linear-gradient(180deg,#9ED8E6 0%,#5FB3C9 45%,#F2DDB3 46%,#EBCB95 100%)",
    "por": "linear-gradient(170deg,#2B2A5C 0%,#B5487A 45%,#F59E5B 75%,#F8D58A 100%)",
    "folhas": "radial-gradient(ellipse 60px 22px at 30% 30%,#4F7A52 98%,transparent) 0 0/140px 140px,radial-gradient(ellipse 70px 26px at 70% 75%,#4F7A52 98%,transparent) 0 0/140px 140px,#2E4A33",
    "grade": "linear-gradient(#5E8CC455 1px,transparent 1px) 0 0/48px 48px,linear-gradient(90deg,#5E8CC455 1px,transparent 1px) 0 0/48px 48px,#123B6B",
}


def _rgb(h):
    h = h.lstrip("#")
    return tuple(int(h[i:i + 2], 16) for i in (0, 2, 4))


def _claro(h):
    r, g, b = _rgb(h)
    return (0.299 * r + 0.587 * g + 0.114 * b) > 150


def foto(geral):
    """Caminho da imagem local usada como papel de parede (ou None)."""
    p = str((geral.get("aparencia") or {}).get("papel") or "")
    if p and p not in PAPEIS and p != "nada" and os.path.isfile(os.path.expanduser(p)):
        return os.path.expanduser(p)
    return None


def css(geral):
    """<style> para injetar na aba Aprovação. Vazio se não houver [aparencia]."""
    ap = geral.get("aparencia") or {}
    if not ap:
        return ""
    t = TEMAS.get(ap.get("tema", "oficina"), TEMAS["oficina"])
    palco = t["lateral"] if not _claro(t["lateral"]) else t["tinta"]
    v = {"noite": palco, "noite2": palco, "azulejo": t["fundo"], "rejunte": t["linha"], "tinta": t["tinta"],
         "tinta2": t["tinta2"], "tinta3": t["tinta2"], "etiqueta": t["destaque"], "etiqueta2": t["destaque"],
         "liberado": t["ok"], "recusa": t["alerta"]}
    regras = [":root{" + ";".join(f"--{k}:{c}" for k, c in v.items()) + "}"]
    fonte = t.get("fonte", "Archivo")
    regras.append(f"body,button,input,textarea{{font-family:'{fonte}',Archivo,system-ui,sans-serif}}")
    papel = str(ap.get("papel") or "nada")
    forca = max(0, min(60, int(ap.get("forca", 22)))) / 100
    imagem = PAPEIS.get(papel)
    if foto(geral):
        imagem = "url('/aparencia/papel') center/cover no-repeat"
    if imagem and papel != "nada":
        r, g, b = _rgb(palco)
        veu = f"rgba({r},{g},{b},{1 - forca:.2f})"
        regras.append(f"body{{background:linear-gradient({veu},{veu}),{imagem};background-attachment:fixed}}")
    link = ""
    if fonte != "Archivo":
        link = ('<link href="https://fonts.googleapis.com/css2?family=' + fonte.replace(" ", "+") +
                ':wght@400;600;700;800&display=swap" rel="stylesheet">')
    return link + '<style id="aparencia">' + "".join(regras) + "</style>"
