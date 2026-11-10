import datetime as dt, json, os, shutil, sys, tempfile, threading, time, unittest, urllib.request, urllib.error

RAIZ = os.path.normpath(os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, RAIZ)
from vigia import acoes, estado, notificar  # noqa: E402


class Base(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.g = {"base": self.tmp, "dados": os.path.join(self.tmp, "dados"), "notificar": {}}

    def tearDown(self):
        shutil.rmtree(self.tmp)


class TestAcoes(Base):
    def esperar(self, id_, s=10):
        for _ in range(s * 10):
            ex = acoes.execucoes(self.g, id_)
            if ex and not ex[0]["rodando"]:
                return ex[0]
            time.sleep(.1)
        self.fail("não terminou")

    def test_sem_comando_no_toml_recusa(self):
        with self.assertRaises(PermissionError):
            acoes.rodar(self.g, {"id": "x", "acoes": {}})

    def test_roda_e_registra_saida_e_exit(self):
        acoes.rodar(self.g, {"id": "x", "acoes": {"rodar": "echo oi; exit 3"}})
        e = self.esperar("x")
        self.assertEqual(e["exit"], 3)
        self.assertIn("oi", e["saida"])

    def test_nao_roda_duas_vezes(self):
        acoes.rodar(self.g, {"id": "y", "acoes": {"rodar": "sleep 2"}})
        with self.assertRaises(RuntimeError):
            acoes.rodar(self.g, {"id": "y", "acoes": {"rodar": "sleep 2"}})
        self.esperar("y")


class TestEstado(Base):
    def test_visto_pausa_retomar(self):
        estado.registrar(self.g, "a", "visto", st="er")
        estado.registrar(self.g, "a", "pausar", "férias")
        d = estado.ler(self.g)
        self.assertEqual(d["visto"]["a"]["st"], "er")
        self.assertEqual(d["pausa"]["a"]["motivo"], "férias")
        estado.registrar(self.g, "a", "retomar")
        self.assertNotIn("a", estado.ler(self.g)["pausa"])
        self.assertEqual(len(estado.ler(self.g)["historico"]), 3)


class TestNotificar(Base):
    def setUp(self):
        super().setUp()
        os.environ.pop("VIGIA_SEM_AVISO", None)

    def dados(self, st):
        return {"gerado": "2026-11-10T10:00:00", "titulo": "Vigia",
                "itens": [{"k": "a", "nome": "A", "st": st, "motivo": "m", "area": "", "ult": "", "acao": ""}]}

    def test_primeira_vez_so_memoriza_e_depois_so_na_mudanca(self):
        arq = os.path.join(self.tmp, "saida.txt")
        self.g["notificar"] = {"comando": f"cat {{arquivo}} >> {arq}"}
        os.environ.pop("VIGIA_SEM_AVISO", None)
        self.assertEqual(notificar.verificar(self.g, self.dados("ok"))["eventos"], 0)
        self.assertEqual(notificar.verificar(self.g, self.dados("er"))["eventos"], 1)
        self.assertEqual(notificar.verificar(self.g, self.dados("er"))["eventos"], 0)  # não repete
        self.assertEqual(notificar.verificar(self.g, self.dados("ok"))["eventos"], 1)  # voltou
        txt = open(arq).read()
        self.assertIn("Problema:", txt)
        self.assertIn("Voltou ao normal", txt)

    def test_envio_que_falha_tenta_de_novo(self):
        self.g["notificar"] = {"comando": "exit 1"}
        notificar.verificar(self.g, self.dados("ok"))
        self.assertFalse(notificar.verificar(self.g, self.dados("er"))["enviado"])
        self.assertEqual(notificar.verificar(self.g, self.dados("er"))["eventos"], 1)


class TestServidor(Base):
    def test_token_e_comando_fora_do_toml(self):
        from vigia import servidor
        os.makedirs(os.path.join(self.tmp, "agentes.d"))
        open(os.path.join(self.tmp, "vigia.toml"), "w").write('porta = 18787\n')
        open(os.path.join(self.tmp, "agentes.d", "a.toml"), "w").write(
            'nome = "A"\nfonte = "jsonl"\n[agenda]\ncron = "0 9 * * *"\n[log]\narquivos = "x.jsonl"\n')
        self.g.update(saida=os.path.join(self.tmp, "p.html"), porta=18787)
        open(self.g["saida"], "w").write("const API=null;")
        t = threading.Thread(target=servidor.servir, args=(self.g, lambda: None, os.path.join(self.tmp, "vigia.toml")), daemon=True)
        t.start()
        time.sleep(.5)
        tok = servidor.token(self.g)

        def post(caminho, token):
            r = urllib.request.Request("http://127.0.0.1:18787" + caminho, data=b"{}", method="POST",
                                       headers={"X-Vigia-Token": token, "Content-Type": "application/json"})
            try:
                return urllib.request.urlopen(r, timeout=5).status
            except urllib.error.HTTPError as e:
                return e.code
        self.assertEqual(post("/api/rodar/a", "errado"), 403)
        self.assertEqual(post("/api/rodar/a", tok), 403)       # sem [acoes] rodar no toml
        self.assertEqual(post("/api/rodar/zzz", tok), 404)
        self.assertEqual(post("/api/visto/a", tok), 200)
        html = urllib.request.urlopen("http://127.0.0.1:18787/", timeout=5).read().decode()
        self.assertIn(tok, html)                                # só a página servida ganha o token
        self.assertNotIn(tok, open(self.g["saida"]).read())


if __name__ == "__main__":
    unittest.main()
