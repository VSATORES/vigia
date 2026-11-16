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

    def escrever(self, nome, txt, mtime):
        p = os.path.join(self.d, nome)
        with open(p, "w") as f:
            f.write(txt)
        os.utime(p, (mtime.timestamp(),) * 2)

    def test_fim_rodada_com_circunflexo_sem_m(self):
        # '^' no fim_rodada vale para cada linha, mesmo sem (?m)
        self.escrever("log-2026-11-16.txt", "07:10:01 robo: início\nfeito\nrobo: rodada encerrada Mon Nov 16 07:10:58 -03 2026\n"
                      "07:40:01 robo: início\nrobo: rodada encerrada Mon Nov 16 07:40:31 -03 2026\n", T(2026, 11, 16, 7, 40, 31))
        a = self.agente(_cron=Cron("10,40 7-22 * * *"))
        a["log"]["fim_rodada"] = r"^robo: rodada encerrada"
        r = log_texto.coletar(a, {}, T(2026, 11, 16, 8))["rodadas"]
        self.assertEqual([(x["ini"], x["dur"], x["manual"]) for x in r],
                         [(T(2026, 11, 16, 7, 10, 1), 57, False), (T(2026, 11, 16, 7, 40, 1), 30, False)])

    def test_rodadas_depois_da_primeira_sao_do_cron_e_tem_duracao(self):
        linhas = "".join(f"{h:02d}:{m:02d}:01 robo: início\nrobo exit=0 Mon Nov 16 {h:02d}:{m:02d}:09 -03 2026\n"
                         for h, m in [(7, 10), (7, 40), (8, 42), (9, 10)])
        linhas += "09:24:58 robo: início (teste)\nrobo exit=0 Mon Nov 16 09:25:30 -03 2026\n"
        self.escrever("log-2026-11-16.txt", linhas, T(2026, 11, 16, 9, 25, 30))
        r = log_texto.coletar(self.agente(_cron=Cron("10,40 7-22 * * *")), {}, T(2026, 11, 16, 10))["rodadas"]
        self.assertEqual([x["manual"] for x in r], [False, False, False, False, True])  # 08:42 = atraso; 09:24 = à mão
        self.assertEqual(r[2]["ini"], T(2026, 11, 16, 8, 42, 1))
        self.assertTrue(all(x["dur"] == 8 for x in r[:4]))
        self.assertEqual(r[4]["dur"], 32)

    def test_linha_so_com_hora_usa_data_do_arquivo(self):
        self.escrever("ciclo-2026-11-16.txt", "a\nciclo exit=0 07:00\nb\nciclo exit=0 07:05\nc\nciclo exit=1 07:10\n",
                      T(2026, 11, 16, 7, 10, 2))
        a = self.agente(_cron=Cron("*/5 7-19 * * 1-5"))
        a["log"].update(arquivos=os.path.join(self.d, "ciclo-*.txt"), fim_rodada=r"ciclo exit=\d+")
        r = log_texto.coletar(a, {}, T(2026, 11, 16, 7, 12))["rodadas"]
        self.assertEqual([(x["ini"].strftime("%H:%M"), x["status"], x["manual"]) for x in r],
                         [("07:00", "ok", False), ("07:05", "ok", False), ("07:10", "falhou", False)])
        self.assertTrue(all(x["fim"] is not None and x["dur"] == 0 for x in r))

    def test_data_futura_dentro_da_mensagem_nao_e_hora_da_rodada(self):
        self.escrever("log-2026-11-16.txt",
                      '07:00 robo exit=0\n07:15 aviso: {"expira_em":"2026-11-18T16:07:33.767Z"}\n07:15 robo exit=0\n',
                      T(2026, 11, 16, 7, 15, 1))
        a = self.agente(_cron=Cron("*/15 7-19 * * *"))
        a["log"]["fim_rodada"] = r"robo exit=\d+"
        r = log_texto.coletar(a, {}, T(2026, 11, 16, 8))["rodadas"]
        self.assertEqual([x["ini"] for x in r], [T(2026, 11, 16, 7, 0), T(2026, 11, 16, 7, 15)])
        self.assertTrue(all(x["fim"].date() == dt.date(2026, 11, 16) for x in r))

    def test_sem_novidade_nao_vale_quando_postou(self):
        regras = [{"se": "sem novidade", "status": "sem_novidade", "motivo": "Sem novidade"},
                  {"se": r"post exit=0", "status": "ok", "motivo": "Postou"}]
        com_post = 'relatório: 3 chamados sem novidade, 2 resolvidos\nclaude exit=0\n{"successful": true}\npost exit=0'
        sem_post = "nada a fazer\nclaude exit=0\nsem novidade; nada postado\npost exit=0"
        self.assertEqual(log_texto.avaliar(com_post, regras, True), ("ok", "Postou"))
        self.assertEqual(log_texto.avaliar(sem_post, regras, True), ("sem_novidade", "Sem novidade"))
        self.assertEqual(log_texto.avaliar(com_post, regras, True, postou="")[0], "sem_novidade")  # desligado

    def test_arquivo_com_hora_no_nome_fora_do_cron_e_a_mao(self):
        self.escrever("log-2026-11-16-11h.txt", "x\nexit=0 Mon Nov 16 11:16:10 -03 2026\n", T(2026, 11, 16, 11, 16, 10))
        self.escrever("log-2026-11-16-12h.txt", "y\nexit=0 Mon Nov 16 12:03:00 -03 2026\n", T(2026, 11, 16, 12, 3))
        r = log_texto.coletar(self.agente(_cron=Cron("0 8-18/2 * * *")), {}, T(2026, 11, 16, 13))["rodadas"]
        self.assertEqual([(x["ini"], x["manual"], x["dur"]) for x in r],
                         [(T(2026, 11, 16, 11, 16, 10), True, None), (T(2026, 11, 16, 12, 0), False, 180)])

    def test_hora_solta_no_conteudo_nao_vira_fim(self):
        self.escrever("log-2026-11-16.txt", "Mon Nov 16 15:00:01 -03 2026 inicio\n08:30 card aberto\nexit=0\n", T(2026, 11, 16, 15, 0, 5))
        r = log_texto.coletar(self.agente(_cron=Cron("0 8,15 * * *")), {}, T(2026, 11, 16, 16))["rodadas"]
        self.assertEqual((r[0]["ini"], r[0]["manual"]), (T(2026, 11, 16, 15, 0, 1), False))

    def test_na_linha_de_fim_vale_a_ultima_data_pela_posicao(self):
        self.escrever("log-2026-11-16.txt", "x\nsem pedido novo Mon Nov 16 15:01:00 -03 2026 (ultimo 2026-11-12 10:00:00)\n",
                      T(2026, 11, 16, 15, 1))
        a = self.agente(_cron=Cron("0 10,15 * * *"))
        a["log"]["fim_rodada"] = r"^sem pedido novo"
        r = log_texto.coletar(a, {}, T(2026, 11, 16, 16))["rodadas"]
        self.assertEqual(r[0]["fim"], T(2026, 11, 16, 15, 1))  # não a data antiga citada na mesma linha
        self.assertEqual(r[0]["ini"].date(), dt.date(2026, 11, 16))
        self.assertFalse(r[0]["manual"])

    def test_arquivo_antigo_mexido_depois_nao_ocupa_horario_de_outro_dia(self):
        self.escrever("log-2026-11-06.txt", "x\nexit=0 Fri Nov  6 09:01:00 -03 2026\ncopiado\n", T(2026, 11, 13, 15, 28))
        r = log_texto.coletar(self.agente(duracao_max_min=480), {}, T(2026, 11, 13, 16))["rodadas"]
        self.assertTrue(all(x["manual"] or x["ini"].date() == dt.date(2026, 11, 6) for x in r))

    def test_so_carimbo_de_inicio_nao_inventa_duracao_zero(self):
        self.escrever("log-2026-11-16.txt", "2026-11-16 09:00:02 inicio\nfeito\nexit=0\n", T(2026, 11, 16, 9, 0, 40))
        r = log_texto.coletar(self.agente(), {}, T(2026, 11, 16, 10))["rodadas"]
        self.assertEqual((r[0]["ini"], r[0]["dur"]), (T(2026, 11, 16, 9, 0, 2), None))

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

    def test_rodada_a_mao_nao_ocupa_horario_da_agendada(self):
        mao = dict(self.rodada(T(2026, 11, 10, 8, 50)), manual=True, motivo="teste")
        it = self.item([mao, self.rodada(T(2026, 11, 10, 9, 0, 5))], [], T(2026, 11, 10, 12))
        hoje = it["rodadas"]["0"]
        self.assertEqual([(x[0], x[2]) for x in hoje], [("08:50", "teste (rodada à mão)"), ("09:00", "ok")])

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
