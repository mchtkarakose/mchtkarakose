from contextlib import contextmanager
from types import SimpleNamespace as NS

import anthropic
import pytest

from robot.beyin import BAGLANTI_HATASI, REDDEDILDI, Beyin
from robot.config import HafizaAyar
from robot.memory.store import Hafiza


def metin_blok(t):
    return NS(type="text", text=t)


def arac_blok(id_, ad, girdi):
    return NS(type="tool_use", id=id_, name=ad, input=girdi)


class SahteModel:
    """Önceden yazılmış yanıtları sırayla döndüren dil modeli."""

    def __init__(self, yanitlar, ozet="Kısa özet."):
        self.yanitlar = list(yanitlar)
        self.cagrilar = []
        self.ozet = ozet

    @contextmanager
    def akis(self, *, system, messages, tools):
        self.cagrilar.append([dict(m) for m in messages])
        y = self.yanitlar.pop(0)
        if isinstance(y, Exception):
            raise y
        parcalar, icerik, durdurma = y

        class _Akis:
            def metin(self_):
                yield from parcalar

            def son_mesaj(self_):
                return NS(content=icerik, stop_reason=durdurma)

        yield _Akis()

    def ozetle(self, dokum):
        self.son_dokum = dokum
        return self.ozet


def duz_yanit(*parcalar):
    return (list(parcalar), [metin_blok("".join(parcalar))], "end_turn")


def beyin_kur(yanitlar, **ayar):
    h = Hafiza()
    m = SahteModel(yanitlar)
    return Beyin(m, h, HafizaAyar(**ayar)), m, h


def test_akista_cumle_cumle_yanit_ve_kayit():
    b, m, h = beyin_kur([duz_yanit("Merhaba! Ben ", "Robi. Nasılsın?")])
    assert list(b.yanitla("selam")) == ["Merhaba!", "Ben Robi.", "Nasılsın?"]
    b.konusma_bitir()
    k = h.konusmalari_listele()[0]
    assert k["mesaj_sayisi"] == 2 and k["ozet"] == "Kısa özet."
    assert "Kullanıcı: selam" in m.son_dokum


def test_ilk_turda_hafiza_baglami_verilir_sonra_tekrarlanmaz():
    b, m, h = beyin_kur([duz_yanit("Tamam."), duz_yanit("Evet.")])
    h.bilgi_ekle("Kullanıcının adı Mehmet.", "kisisel")
    h.bilgi_ekle("Kullanıcı kahveyi sütlü içer.", "tercih")
    list(b.yanitla("kahve yapar mısın"))
    ilk = m.cagrilar[0][0]["content"]
    assert "<hafiza>" in ilk and "Mehmet" in ilk and "sütlü" in ilk and ilk.endswith("kahve yapar mısın")
    list(b.yanitla("kahve gerçekten güzel"))
    ikinci = m.cagrilar[1][-1]["content"]
    assert ikinci == "kahve gerçekten güzel"  # Zaten gösterilen kayıtlar tekrar eklenmez


def test_onceki_konusma_ozeti_yeni_konusmaya_tasinir():
    b, m, h = beyin_kur([duz_yanit("A."), duz_yanit("B."), duz_yanit("C.")])
    list(b.yanitla("bir"))
    list(b.yanitla("iki"))
    b.konusma_bitir()
    list(b.yanitla("üç"))
    assert "Kısa özet." in m.cagrilar[2][0]["content"]


def test_arac_ile_hafizaya_kaydetme():
    b, m, h = beyin_kur(
        [
            (
                ["Hemen kaydediyorum."],
                [metin_blok("Hemen kaydediyorum."), arac_blok("t1", "hafizaya_kaydet", {"icerik": "Kedinin adı Pamuk.", "tur": "kisisel"})],
                "tool_use",
            ),
            duz_yanit("Kaydettim."),
        ]
    )
    assert list(b.yanitla("kedimin adı Pamuk, unutma")) == ["Hemen kaydediyorum.", "Kaydettim."]
    assert h.bilgileri_listele()[0].icerik == "Kedinin adı Pamuk."
    sonuc = m.cagrilar[1][-1]["content"][0]
    assert sonuc["tool_use_id"] == "t1" and "Kaydedildi" in sonuc["content"]


def test_gecersiz_arac_girdisi_calistirilmaz():
    b, m, h = beyin_kur(
        [
            ([], [arac_blok("t1", "hafizaya_kaydet", {"icerik": "x", "tur": "yanlis"})], "tool_use"),
            ([], [arac_blok("t2", "hafizadan_sil", {"numara": 99})], "tool_use"),
            duz_yanit("Tamam."),
        ]
    )
    list(b.yanitla("dene"))
    assert h.bilgileri_listele() == []
    assert m.cagrilar[1][-1]["content"][0]["is_error"] is True
    assert "bulunamadı" in m.cagrilar[2][-1]["content"][0]["content"]


def test_baglanti_hatasinda_tur_geri_alinir():
    hata = anthropic.APIConnectionError(request=None)
    b, m, h = beyin_kur([hata, duz_yanit("Buradayım.")])
    assert list(b.yanitla("orada mısın")) == [BAGLANTI_HATASI]
    assert b.mesajlar == []
    assert list(b.yanitla("şimdi?")) == ["Buradayım."]


def test_reddetmede_tur_geri_alinir():
    b, m, h = beyin_kur([(["Şey"], [metin_blok("Şey")], "refusal")])
    assert list(b.yanitla("..."))[-1] == REDDEDILDI
    assert b.mesajlar == []


def test_kayit_kapaliysa_konusma_saklanmaz():
    b, m, h = beyin_kur([duz_yanit("Tamam.")], konusmalari_kaydet=False)
    list(b.yanitla("gizli konuşma"))
    b.konusma_bitir()
    assert h.konusmalari_listele() == []


@pytest.mark.parametrize("girdi", [None, "metin", {"icerik": "a"}, {"icerik": "a", "tur": "bilgi", "x": 1}, {"numara": True}])
def test_dogrulama(girdi):
    from robot.memory import araclar

    with pytest.raises(araclar.GecersizGirdi):
        araclar.dogrula("hafizaya_kaydet" if not (isinstance(girdi, dict) and "numara" in girdi) else "hafizadan_sil", girdi)
