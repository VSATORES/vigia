"""Expressão cron mínima (minuto hora dia mês dia-da-semana) → horários esperados.

Suporta *, listas (1,2), faixas (8-18), passos (*/15, 8-18/2) e dia da semana 0-7 (0 e 7 = domingo).
Sem dependências. Usado para saber quando cada rotina deveria ter rodado.
"""
import datetime as dt

_LIMITES = [(0, 59), (0, 23), (1, 31), (1, 12), (0, 6)]


def _campo(txt, lo, hi, dow=False):
    out = set()
    for parte in txt.split(","):
        passo = 1
        if "/" in parte:
            parte, p = parte.split("/", 1)
            passo = int(p)
        if parte in ("*", ""):
            a, b = lo, hi
        elif "-" in parte:
            a, b = (int(x) for x in parte.split("-", 1))
        else:
            a = b = int(parte)
            if passo != 1:
                b = hi
        for v in range(a, b + 1, passo):
            out.add(0 if dow and v == 7 else v)
    for v in out:
        if not (lo <= v <= (7 if dow else hi)):
            raise ValueError(f"valor {v} fora do limite {lo}-{hi} em '{txt}'")
    return out


class Cron:
    def __init__(self, expr):
        partes = expr.split()
        if len(partes) != 5:
            raise ValueError(f"cron precisa de 5 campos (minuto hora dia mês semana): '{expr}'")
        self.expr = expr
        self.min, self.hora, self.dia, self.mes, self.sem = (
            _campo(p, lo, hi, dow=(i == 4)) for i, (p, (lo, hi)) in enumerate(zip(partes, _LIMITES)))
        self._dia_livre = partes[2] == "*"
        self._sem_livre = partes[4] == "*"

    def _bate_dia(self, d):
        sem = (d.weekday() + 1) % 7  # cron: 0 = domingo
        if self._dia_livre and self._sem_livre:
            return True
        if self._dia_livre:
            return sem in self.sem
        if self._sem_livre:
            return d.day in self.dia
        return d.day in self.dia or sem in self.sem  # regra clássica do cron

    def entre(self, ini, fim):
        """Lista de horários esperados com ini <= t <= fim."""
        out = []
        d = ini.replace(hour=0, minute=0, second=0, microsecond=0)
        while d <= fim:
            if d.month in self.mes and self._bate_dia(d):
                for h in sorted(self.hora):
                    for m in sorted(self.min):
                        t = d.replace(hour=h, minute=m)
                        if ini <= t <= fim:
                            out.append(t)
            d += dt.timedelta(days=1)
        return out

    def proximo(self, depois):
        c = self.entre(depois + dt.timedelta(seconds=1), depois + dt.timedelta(days=32))
        return c[0] if c else None

    def anterior(self, ate):
        c = self.entre(ate - dt.timedelta(days=32), ate)
        return c[-1] if c else None

    def por_dia(self):
        """Quantas vezes por dia (aprox., para rótulo)."""
        return len(self.hora) * len(self.min)
