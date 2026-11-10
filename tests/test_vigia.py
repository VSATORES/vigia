import datetime as dt, json, os, re, shutil, sys, tempfile, unittest

RAIZ = os.path.normpath(os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, RAIZ)
from vigia import config, modelo, pagina, historico  # noqa: E402
from vigia.cronexpr import Cron  # noqa: E402
from vigia.fontes import log_texto, sql  # noqa: E402
from vigia.cli import gerar  # noqa: E402

T = dt.datetime


class TestCron(unittest.TestCase):
    def test_passos_e_faixas(self):
        c = Cron("0 8-18/2 * * *")
        h = c.entre(T(2026, 11, 10, 0, 0), T(2026, 11, 10, 23, 59))
        self.assertEqual([x.hour for x in h], [8, 10, 12, 14, 16, 18])

    def test_dia_da_semana(self):
        c = Cron("0 12 * * 4")  # quinta
        h = c.entre(T(2026, 11, 1), T(2026, 11, 30))
        self.assertTrue(all(x.weekday() == 3 for x in h))
        self.assertEqual(len(h), 4)

    def test_domingo_7(self):
        self.assertEqual(Cron("0 9 * * 7").proximo(T(2026, 11, 10)).weekday(), 6)

    def test_invalido(self):
        with self.assertRaises(ValueError):
            Cron("0 25 * * *")


class TestLog(unittest.TestCase):
    def setUp(self):
        self.d = tempfile.mkdtemp()

    def tearDown(self):
        shutil.rmtree(self.d)

    def agente(self, regras=None, **agenda):
        return {"id": "x", "nome": "X", "fonte": "log_texto", "agenda": {"_cron": Cron("0 9 * * *"), **agenda},
                "log": {"arquivos": os.path.join(self.d, "log-*.txt"), "fim_rodada": r"exit=\d+"}, "regras": regras or []}

    def test_regra_limite_e_hora(self):
        open(os.path.join(self.d, "log-2026-11-09.txt"), "w").write(
            "You've hit your 5-hour limit · resets 1:50pm (America/Sao_Paulo)\nexit=1 Mon Nov  9 09:00:08 -03 2026\n")
        a = self.agente([{"se": r"hit your .*?limit.*?resets ([^\n(]+?)\s*\(", "status": "falhou", "motivo": r"Limite (\1)"}])
        r = log_texto.coletar(a, {}, T(2026, 11, 9, 12))["rodadas"]
        self.assertEqual(len(r), 1)
        self.assertEqual(r[0]["status"], "falhou")
        self.assertEqual(r[0]["motivo"], "Limite (1:50pm)")
        self.assertEqual(r[0]["ini"], T(2026, 11, 9, 9, 0))
        self.assertEqual(r[0]["dur"], 8)

    def test_varias_rodadas_no_mesmo_arquivo(self):
        open(os.path.join(self.d, "log-2026-11-09.txt"), "w").write(
            "a\nexit=0 Mon Nov  9 09:01:00 -03 2026\nb\nexit=1 Mon Nov  9 15:00:00 -03 2026\n")
        r = log_texto.coletar(self.agente(), {}, T(2026, 11, 9, 16))["rodadas"]
        self.assertEqual([x["status"] for x in r], ["ok", "falhou"])
        self.assertTrue(r[1]["manual"])
        self.assertIsNone(r[1]["dur"])

    def test_linha_depois_do_fim_e_da_mesma_rodada(self):
        p = os.path.join(self.d, "log-2026-11-10.txt")
        open(p, "w").write("rodou\nexit=0 Tue Nov 10 09:05:22 -03 2026\ncopiado para Downloads\n")
        os.utime(p, (T(2026, 11, 10, 9, 5, 23).timestamp(),) * 2)
        r = log_texto.coletar(self.agente(), {}, T(2026, 11, 10, 12))["rodadas"]
        self.assertEqual(len(r), 1)
        self.assertEqual(r[0]["status"], "ok")

    def test_log_sem_fim_antigo_e_falha(self):
        open(os.path.join(self.d, "log-2026-11-08.txt"), "w").write("começou\n")
        os.utime(os.path.join(self.d, "log-2026-11-08.txt"), (T(2026, 11, 8, 9).timestamp(),) * 2)
        r = log_texto.coletar(self.agente(), {}, T(2026, 11, 9, 16))["rodadas"]
        self.assertEqual(r[0]["status"], "falhou")


def geral_base(tmp):
    return {"base": tmp, "historico": os.path.join(tmp, "h"), "vivo": [], "margem_atraso_min": 10, "meta": .95,
            "conexoes": {}, "titulo": "Vigia", "_crontab": None}


class TestModeloRotina(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.g = geral_base(self.tmp)

    def tearDown(self):
        shutil.rmtree(self.tmp)

    def rodada(self, t, st="ok"):
        return {"ini": t, "fim": t + dt.timedelta(minutes=2), "dur": 120, "status": st, "motivo": st, "trecho": "",
                "arquivo": "", "volume": None, "manual": False}

    def item(self, rodadas, vivos, agora, **agenda):
        a = {"id": "r", "nome": "R", "fonte": "log_texto", "agenda": {"_cron": Cron("0 9 * * *"), "cron": "0 9 * * *", **agenda}, "regras": []}
        it, _, _ = modelo.item_rotina(a, {"rodadas": rodadas}, self.g, agora, vivos)
        return it

    def test_nao_rodou_com_pc_ligado(self):
        agora = T(2026, 11, 10, 12)
        r = [self.rodada(T(2026, 11, 8, 9))]
        vivos = [T(2026, 11, 9, 9, 5), T(2026, 11, 10, 9, 5)]
        it = self.item(r, vivos, agora)
        self.assertEqual(it["st"], "nr")
        self.assertEqual(it["dias"][0], "er")  # hoje 9h não rodou
        self.assertEqual(it["dias"][1], "er")

    def test_pc_desligado_nao_e_falha(self):
        agora = T(2026, 11, 10, 12)
        r = [self.rodada(T(2026, 11, 8, 9)), self.rodada(T(2026, 11, 10, 9))]
        vivos = [T(2026, 11, 8, 9), T(2026, 11, 10, 9)]  # 09/11 sem sinal de vida
        it = self.item(r, vivos, agora)
        self.assertEqual(it["dias"][1], "pc")
        self.assertEqual(it["st"], "ok")
        self.assertEqual(it["ruim_mes"], 0)

    def test_atrasado_dentro_da_janela(self):
        agora = T(2026, 11, 10, 9, 30)
        it = self.item([self.rodada(T(2026, 11, 9, 9))], [T(2026, 11, 10, 9, 20)], agora)
        self.assertEqual(it["st"], "late")

    def test_fora_do_crontab(self):
        self.g["_crontab"] = "0 8 * * * /outra/coisa.sh\n"
        it = self.item([self.rodada(T(2026, 11, 10, 9))], [], T(2026, 11, 10, 12), comando="minha-rotina.sh")
        self.assertEqual(it["st"], "nr")
        self.assertIn("crontab", it["motivo"])


class TestModeloAgente(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.g = geral_base(self.tmp)

    def tearDown(self):
        shutil.rmtree(self.tmp)

    def item(self, dias, eventos=(), flag=None, entrada=None, erro_fonte=None, agora=T(2026, 11, 10, 15)):
        a = {"id": "a", "nome": "A", "fonte": "sql", "sql": {}, "flag": {"chave": "f"} if flag is not None else {}}
        col = {"dias": dias, "eventos": list(eventos), "alerta": None, "flag": flag, "erro_fonte": erro_fonte}
        if entrada is not None:
            col["entrada"] = entrada
        it, _ = modelo.item_agente(a, col, self.g, agora)
        return it

    def test_fonte_fora_do_ar_nunca_e_verde(self):
        self.assertEqual(self.item({}, erro_fonte="timeout")["st"], "er")

    def test_flag_ligada_e_calado_7_dias(self):
        it = self.item({"2026-11-01": {"n": 5, "erros": 0, "humano": 0, "ultima": T(2026, 11, 1, 10)}}, flag=True)
        self.assertEqual(it["st"], "nr")

    def test_dia_calado_so_e_falha_com_entrada(self):
        dias = {"2026-11-10": {"n": 3, "erros": 0, "humano": 0, "ultima": T(2026, 11, 10, 14)}}
        sem = self.item(dias)
        com = self.item(dias, entrada={"2026-11-09": 12})
        self.assertEqual(sem["dias"][1], "none")
        self.assertEqual(com["dias"][1], "er")

    def test_silencio_so_onde_costuma_ter_atividade(self):
        agora = T(2026, 11, 10, 15)
        evs = []
        for k in range(1, 15):  # todo dia, atividade de 8h às 18h a cada 20 min
            for m in range(0, 600, 20):
                evs.append({"quando": T(2026, 11, 10 - k if 10 - k > 0 else 1, 8) + dt.timedelta(minutes=m) if 10 - k > 0
                            else T(2026, 10, 31 + (10 - k), 8) + dt.timedelta(minutes=m), "ok": True, "texto": ""})
        evs.append({"quando": T(2026, 11, 10, 9), "ok": True, "texto": ""})
        evs.sort(key=lambda e: e["quando"])
        dias = {"2026-11-10": {"n": 1, "erros": 0, "humano": 0, "ultima": T(2026, 11, 10, 9)}}
        self.assertEqual(self.item(dias, evs, agora=agora)["st"], "late")
        madrugada = T(2026, 11, 11, 3)
        self.assertEqual(self.item(dias, evs, agora=madrugada)["st"], "ok")


class TestConfig(unittest.TestCase):
    def test_erros_claros(self):
        tmp = tempfile.mkdtemp()
        os.makedirs(os.path.join(tmp, "agentes.d"))
        open(os.path.join(tmp, "vigia.toml"), "w").write('meta = 95\n')
        open(os.path.join(tmp, "agentes.d", "ruim.toml"), "w").write('nome = "R"\nfonte = "log_texto"\n[sql]\npor_dia="DELETE"\n')
        _, _, erros = config.carregar(os.path.join(tmp, "vigia.toml"))
        texto = " ".join(erros)
        self.assertIn("meta", texto)
        self.assertIn("agenda.cron", texto)
        self.assertIn("log.arquivos", texto)
        shutil.rmtree(tmp)

    def test_sql_so_leitura(self):
        tmp = tempfile.mkdtemp()
        os.makedirs(os.path.join(tmp, "agentes.d"))
        open(os.path.join(tmp, "vigia.toml"), "w").write('[conexoes.b]\ntipo="arquivo"\ncaminho="x.json"\n')
        open(os.path.join(tmp, "agentes.d", "a.toml"), "w").write('nome = "A"\nfonte = "sql"\n[sql]\nconexao="b"\npor_dia="DELETE FROM t"\n')
        _, _, erros = config.carregar(os.path.join(tmp, "vigia.toml"))
        self.assertTrue(any("só leitura" in e for e in erros))
        shutil.rmtree(tmp)


class TestDemoPublica(unittest.TestCase):
    """A demonstração gera sem erro e o repositório não carrega marca nem dado de ninguém."""

    def test_demo_gera(self):
        dados = gerar(os.path.join(RAIZ, "exemplos", "vigia.toml"), registrar=False, quieto=True)
        sts = {i["k"]: i["st"] for i in dados["itens"]}
        self.assertEqual(sts["relatorio"], "er")
        self.assertEqual(sts["triagem"], "off")
        self.assertEqual(sts["revisor"], "late")
        html = open(os.path.join(RAIZ, "docs", "index.html"), encoding="utf-8").read()
        self.assertIn("const D=", html)

    def test_sem_marca_no_repositorio(self):
        proibido = re.compile("|".join(["sea" + "zone", "sap" + "ron", "vini" + "cius", "franq" + "uia"]), re.I)
        achados = []
        for raiz, pastas, arqs in os.walk(RAIZ):
            pastas[:] = [p for p in pastas if p not in (".git", "__pycache__", "dados-demo")]
            for a in arqs:
                p = os.path.join(raiz, a)
                try:
                    if proibido.search(open(p, encoding="utf-8", errors="ignore").read()):
                        achados.append(os.path.relpath(p, RAIZ))
                except OSError:
                    pass
        self.assertEqual(achados, [], f"marca/dado privado em: {achados}")


if __name__ == "__main__":
    unittest.main()
