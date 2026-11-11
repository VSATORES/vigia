import datetime as dt, json, os, shutil, sys, tempfile, time, unittest

RAIZ = os.path.normpath(os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, RAIZ)
from vigia import config, pedidos  # noqa: E402


def pedido(id_="p1", **kw):
    p = {"id": id_, "agente": "ag", "criado_em": "2026-11-11T10:00:00", "titulo": "Liberar o item 1?",
         "risco": "producao", "entrada": {"fonte": "slack"},
         "proposta": {"acao": "liberar", "rotulo": "Liberar", "previa": "texto original"},
         "alternativa": {"acao": "devolver", "rotulo": "Devolver", "previa": "outro texto"}}
    p.update(kw)
    return p


class TestPedidos(unittest.TestCase):
    def setUp(self):
        self.d = tempfile.mkdtemp()
        self.geral = {"base": self.d, "dados": os.path.join(self.d, "dados"), "pedidos": os.path.join(self.d, "pedidos")}
        os.makedirs(os.path.join(self.geral["pedidos"], "ag"))
        self.saida = os.path.join(self.d, "executou.txt")
        # executor de teste: copia a prévia efetiva do pedido para um arquivo
        cmd = (f"python3 -c \"import json,sys; p=json.load(open(sys.argv[1])); "
               f"open('{self.saida}','a').write(p['executar']['previa']+'\\n')\" {{pedido}}")
        self.agentes = [{"id": "ag", "nome": "Agente", "executores": {"liberar": cmd}}]

    def tearDown(self):
        shutil.rmtree(self.d)

    def grava(self, p):
        json.dump(p, open(os.path.join(self.geral["pedidos"], "ag", p["id"] + ".json"), "w"))

    def espera_execucao(self, id_="p1", seg=10):
        fim = time.time() + seg
        while time.time() < fim:
            ev = pedidos.estados(self.geral).get(("ag", id_))
            if ev and ev["estado"] in ("executado", "falhou"):
                return ev
            time.sleep(0.05)
        self.fail("executor não terminou")

    def test_valido_aparece_e_invalido_vira_problema(self):
        self.grava(pedido())
        self.grava(pedido("p2", risco="qualquer"))
        lista, prob = pedidos.ler(self.geral)
        self.assertEqual([p["id"] for p in lista], ["p1"])
        self.assertTrue(any("risco" in x for x in prob))
        self.assertEqual(len(pedidos.pendentes(self.geral)), 1)

    def test_executor_fora_do_toml_e_recusado(self):
        self.grava(pedido())
        with self.assertRaises(PermissionError):
            pedidos.decidir(self.geral, self.agentes, "ag", "p1", "aprovar", opcao=1)  # 'devolver' não declarado
        self.assertEqual(len(pedidos.pendentes(self.geral)), 1)  # segue esperando

    def test_aprova_uma_vez_so_e_texto_editado_chega(self):
        self.grava(pedido())
        pedidos.decidir(self.geral, self.agentes, "ag", "p1", "aprovar", texto="texto editado")
        with self.assertRaises(RuntimeError):
            pedidos.decidir(self.geral, self.agentes, "ag", "p1", "aprovar")
        ev = self.espera_execucao()
        self.assertEqual(ev["estado"], "executado")
        self.assertEqual(open(self.saida).read(), "texto editado\n")
        self.assertEqual(pedidos.pendentes(self.geral), [])
        evs = [e for e in pedidos.eventos(self.geral) if e["id"] == "p1"]
        self.assertTrue(evs[0]["editado"])

    def test_recusar_some_e_nao_executa(self):
        self.grava(pedido())
        pedidos.decidir(self.geral, self.agentes, "ag", "p1", "recusar")
        self.assertEqual(pedidos.pendentes(self.geral), [])
        self.assertFalse(os.path.exists(self.saida))

    def test_adiado_volta_no_horario(self):
        self.grava(pedido())
        pedidos.decidir(self.geral, self.agentes, "ag", "p1", "adiar", horas=1)
        self.assertEqual(pedidos.pendentes(self.geral), [])
        depois = pedidos.agora() + dt.timedelta(hours=1, minutes=1)
        self.assertEqual(len(pedidos.pendentes(self.geral, depois)), 1)
        pedidos.decidir(self.geral, self.agentes, "ag", "p1", "aprovar")  # adiado ainda pode ser aprovado
        self.assertEqual(self.espera_execucao()["estado"], "executado")

    def test_executor_que_falha_fica_registrado(self):
        self.agentes[0]["executores"]["liberar"] = "exit 3 # {pedido}"
        self.grava(pedido())
        pedidos.decidir(self.geral, self.agentes, "ag", "p1", "aprovar")
        self.assertEqual(self.espera_execucao()["estado"], "falhou")

    def test_anexo_fora_da_pasta_bloqueado(self):
        open(os.path.join(self.geral["pedidos"], "ag", "foto.png"), "wb").write(b"x")
        self.assertIsNotNone(pedidos.midia_segura(self.geral, "ag", "foto.png"))
        self.assertIsNone(pedidos.midia_segura(self.geral, "ag", "../../dados/decisoes.jsonl"))
        self.assertIsNone(pedidos.midia_segura(self.geral, "ag", "/etc/passwd"))

    def test_id_invalido(self):
        with self.assertRaises(LookupError):
            pedidos.decidir(self.geral, self.agentes, "ag", "../x", "aprovar")


class TestOutraEAnexos(TestPedidos):
    def test_outra_exige_texto_e_sai_da_fila(self):
        self.grava(pedido())
        with self.assertRaises(ValueError):
            pedidos.decidir(self.geral, self.agentes, "ag", "p1", "outra", texto=" ")
        pedidos.decidir(self.geral, self.agentes, "ag", "p1", "outra", texto="Pergunte se o técnico volta amanhã")
        self.assertEqual(pedidos.pendentes(self.geral), [])
        ev = pedidos.estados(self.geral)[("ag", "p1")]
        self.assertEqual((ev["estado"], ev["texto"]), ("outra", "Pergunte se o técnico volta amanhã"))
        self.assertFalse(os.path.exists(self.saida))

    def test_anexos_pelo_resolvedor_com_cache(self):
        cont = os.path.join(self.d, "chamadas")
        self.geral["aprovacao"] = {"resolvedores": {"teste": f"echo x >> {cont}; echo '[{{\"rotulo\":\"f\",\"url\":\"https://h/{{id}}.jpg\"}},{{\"rotulo\":\"ruim\",\"url\":\"file:///etc/passwd\"}}]'"}}
        self.grava(pedido(anexos={"de": "teste", "id": 42}))
        a = pedidos.anexos(self.geral, "ag", "p1")
        self.assertEqual([x["url"] for x in a], ["https://h/42.jpg"])  # link que não é http cai fora
        pedidos.anexos(self.geral, "ag", "p1")
        self.assertEqual(open(cont).read().count("x"), 1)  # segunda vez veio do cache

    def test_resolvedor_nao_declarado(self):
        self.geral["aprovacao"] = {}
        self.grava(pedido(anexos={"de": "outro", "id": 1}))
        with self.assertRaises(PermissionError):
            pedidos.anexos(self.geral, "ag", "p1")


class TestConfigExecutores(unittest.TestCase):
    def test_executor_sem_pedido_e_nome_ruim(self):
        d = tempfile.mkdtemp()
        try:
            os.makedirs(os.path.join(d, "agentes.d"))
            open(os.path.join(d, "vigia.toml"), "w").write('titulo = "t"\n')
            open(os.path.join(d, "agentes.d", "a.toml"), "w").write(
                'nome = "A"\nfonte = "log_texto"\n[agenda]\ncron = "0 8 * * *"\n[log]\narquivos = "x/*.txt"\n'
                '[executores]\nliberar = "rodar.sh"\nRuim = "rodar.sh {pedido}"\nok = "rodar.sh {pedido}"\n')
            _, _, erros = config.carregar(os.path.join(d, "vigia.toml"))
            self.assertTrue(any("executores.liberar precisa" in e for e in erros))
            self.assertTrue(any("executores.Ruim" in e for e in erros))
            self.assertFalse(any("executores.ok" in e for e in erros))
        finally:
            shutil.rmtree(d)


if __name__ == "__main__":
    unittest.main()
