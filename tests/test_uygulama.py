from robot.beyin import Beyin
from robot.config import HafizaAyar
from robot.memory.store import Hafiza
from robot.speech.base import Dinleyici, Konusmaci
from robot.uygulama import Robot, cikis_mi
from tests.test_beyin import SahteModel, duz_yanit


class SahteDinleyici(Dinleyici):
    def __init__(self, sozler):
        self.sozler = list(sozler)

    def dinle(self):
        if not self.sozler:
            raise EOFError
        return self.sozler.pop(0)


class SahteKonusmaci(Konusmaci):
    def __init__(self):
        self.soylenen = []

    def konus(self, metin):
        self.soylenen.append(metin)


def test_cikis_ifadeleri():
    assert cikis_mi("Görüşürüz!") and cikis_mi("çıkış") and not cikis_mi("görüşürüz yarın")


def test_robot_dongusu():
    h = Hafiza()
    beyin = Beyin(SahteModel([duz_yanit("Merhaba! Nasılsın?")]), h, HafizaAyar())
    k = SahteKonusmaci()
    robot = Robot(beyin, SahteDinleyici(["", "selam", "görüşürüz"]), k)
    robot.calistir()
    assert k.soylenen == ["Merhaba!", "Nasılsın?", "Görüşmek üzere!"]
    assert len(robot.gecikmeler_ms) == 1
    assert h.konusmalari_listele()[0]["bitis"] is not None
