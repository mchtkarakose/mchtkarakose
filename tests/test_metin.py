from robot.metin import CumleBolucu, konusmaya_uygun


def _bol(parcalar, **kw):
    b = CumleBolucu(**kw)
    cikti = []
    for p in parcalar:
        cikti += b.ekle(p)
    return cikti + b.bitir()


def test_cumlelere_boler_ve_akista_erken_verir():
    b = CumleBolucu()
    assert b.ekle("Merhaba! Nası") == ["Merhaba!"]
    assert b.ekle("lsın? İyi") == ["Nasılsın?"]
    assert b.bitir() == ["İyi"]


def test_kisaltma_ve_sayilarda_bolmez():
    assert _bol(["Dr. Ahmet geldi. ", "Fiyat 3.5 lira."]) == ["Dr. Ahmet geldi.", "Fiyat 3.5 lira."]
    assert _bol(["Bugün 19. gün. Tamam."]) == ["Bugün 19. gün.", "Tamam."]


def test_ilk_parca_virgulde_erken_kesilir():
    metin = "Bunu sana memnuniyetle anlatırım, çünkü çok ilginç bir konu, gerçekten."
    sonuc = _bol([metin])
    assert sonuc[0] == "Bunu sana memnuniyetle anlatırım,"
    assert sonuc[1] == "çünkü çok ilginç bir konu, gerçekten."


def test_markdown_temizlenir():
    assert konusmaya_uygun("**Kalın** ve [bağlantı](http://x) # başlık") == "Kalın ve bağlantı başlık"
    assert _bol(["- birinci\n- ikinci"]) == ["birinci", "ikinci"]
