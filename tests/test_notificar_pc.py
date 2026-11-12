"""Aviso de 'computador desligado' (12/11): rotina perdida com o PC desligado avisa uma vez quando ele volta."""
import json, os, shutil, sys, tempfile, unittest

RAIZ = os.path.normpath(os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, RAIZ)
from vigia import notificar  # noqa: E402


def dados(rods_kpis, rods_tars=None, gerado="2026-11-11T09:15:00"):
    return {"titulo": "Vigia", "gerado": gerado, "itens": [
        {"k": "kpis", "nome": "KPIs diários", "st": "ok", "motivo": "ok", "rodadas": rods_kpis},
        {"k": "tars", "nome": "TARS", "st": "ok", "motivo": "ok", "rodadas": rods_tars or {}},
        {"k": "pausado", "nome": "Pausado", "st": "pause", "motivo": "", "rodadas": {"0": [["08:00", "pc", "x"]]}},
    ]}


class TestPcDesligado(unittest.TestCase):
    def setUp(self):
        self.d = tempfile.mkdtemp()
        self.saida = os.path.join(self.d, "enviado.txt")
        self.geral = {"dados": self.d, "notificar": {
            "comando": f"cat {{arquivo}} >> {self.saida}", "link": "http://x", "ao_voltar": True}}
        os.environ.pop("VIGIA_SEM_AVISO", None)

    def tearDown(self):
        shutil.rmtree(self.d)

    def enviado(self):
        return open(self.saida).read() if os.path.exists(self.saida) else ""

    def test_perdidas_so_hoje_e_ontem_e_ignora_pausado(self):
        p = notificar.perdidas(dados({"0": [["08:30", "pc", "Computador desligado no horário"], ["09:03", "ok", "x"]],
                                      "1": [["08:30", "ok", "x"]], "2": [["08:30", "pc", "x"]]}))
        self.assertEqual(list(p), ["kpis|2026-11-11|08:30"])

    def test_primeira_vez_so_memoriza(self):
        r = notificar.verificar(self.geral, dados({"0": [["08:30", "pc", "x"]]}))
        self.assertEqual(r["pc"], 0)
        self.assertEqual(self.enviado(), "")

    def test_avisa_uma_vez_quando_o_pc_volta(self):
        notificar.verificar(self.geral, dados({}))  # memoriza: nada perdido
        tars = {"0": [[f"0{h}:{m:02d}", "pc", "x"] for h in range(3, 9) for m in (0, 30)]}
        r = notificar.verificar(self.geral, dados({"0": [["08:30", "pc", "x"]]}, tars))
        self.assertEqual(r["pc"], 13)
        txt = self.enviado()
        self.assertIn("Computador desligado", txt)
        self.assertIn("KPIs diários: 11/11 08:30", txt)
        self.assertIn("TARS: 12 horários, de 11/11 03:00 a 11/11 08:30", txt)
        self.assertNotIn("Pausado", txt)
        # mesma geração de novo: não repete
        r = notificar.verificar(self.geral, dados({"0": [["08:30", "pc", "x"]]}, tars))
        self.assertEqual(r["pc"], 0)
        self.assertEqual(txt, self.enviado())
        est = json.load(open(os.path.join(self.d, "estado.json")))
        self.assertIn("kpis|2026-11-11|08:30", est["pc_avisado"])

    def test_falha_no_envio_tenta_de_novo(self):
        notificar.verificar(self.geral, dados({}))
        self.geral["notificar"]["comando"] = "false {arquivo}"
        r = notificar.verificar(self.geral, dados({"0": [["08:30", "pc", "x"]]}))
        self.assertFalse(r["enviado"])
        self.geral["notificar"]["comando"] = f"cat {{arquivo}} >> {self.saida}"
        r = notificar.verificar(self.geral, dados({"0": [["08:30", "pc", "x"]]}))
        self.assertEqual(r["pc"], 1)
        self.assertIn("KPIs diários", self.enviado())


if __name__ == "__main__":
    unittest.main()
