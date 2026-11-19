from robot.memory.store import Hafiza, _arama_sorgusu


def test_bilgi_ekle_ara_sil():
    h = Hafiza()
    a = h.bilgi_ekle("Kullanıcının kedisinin adı Pamuk.", "kisisel")
    h.bilgi_ekle("Ankara Türkiye'nin başkentidir.", "bilgi")
    assert [b.id for b in h.bilgi_ara("kedim ne yapıyor")] == [a]
    assert h.bilgi_ara("ANKARA")[0].icerik.startswith("Ankara")
    # Türkçe karakter farkı aramayı etkilememeli
    assert h.bilgi_ara("başkent")
    assert h.bilgi_sil(a)
    assert h.bilgi_ara("kedi") == []
    assert not h.bilgi_sil(a)


def test_ayni_bilgi_tekrar_eklenmez():
    h = Hafiza()
    assert h.bilgi_ekle("Çayı şekersiz sever.", "tercih") == h.bilgi_ekle("Çayı şekersiz sever.", "tercih")
    assert len(h.bilgileri_listele()) == 1


def test_guncelle_arama_dizinini_de_gunceller():
    h = Hafiza()
    no = h.bilgi_ekle("En sevdiği renk mavi.", "tercih")
    assert h.bilgi_guncelle(no, "En sevdiği renk yeşil.")
    assert h.bilgi_ara("yeşil")[0].id == no
    assert h.bilgi_ara("mavi") == []


def test_kullanicilar_birbirinin_hafizasini_gormez(tmp_path):
    yol = tmp_path / "h.db"
    a, b = Hafiza(yol, "ali"), Hafiza(yol, "ayse")
    no = a.bilgi_ekle("Ali futbol sever.", "tercih")
    assert b.bilgileri_listele() == []
    assert b.bilgi_ara("futbol") == []
    assert not b.bilgi_sil(no)
    b.tumunu_sil()
    assert len(a.bilgileri_listele()) == 1


def test_konusma_ozet_ve_disa_aktarma(tmp_path):
    h = Hafiza(tmp_path / "h.db")
    k = h.konusma_baslat()
    h.mesaj_ekle(k, "kullanici", "Merhaba")
    h.mesaj_ekle(k, "robot", "Merhaba!")
    h.konusma_bitir(k, "Selamlaştılar.")
    assert h.son_ozetler(3)[0]["ozet"] == "Selamlaştılar."
    veri = h.disa_aktar()
    assert veri["konusmalar"][0]["mesajlar"][1]["metin"] == "Merhaba!"
    h.disa_aktar_dosya(tmp_path / "d.json")
    assert (tmp_path / "d.json").read_text("utf-8")
    assert h.konusma_sil(k)
    assert h.mesajlar(k) == []


def test_tumunu_sil():
    h = Hafiza()
    h.bilgi_ekle("x bilgisi", "bilgi")
    h.konusma_baslat()
    h.tumunu_sil()
    assert h.bilgileri_listele() == [] and h.konusmalari_listele() == []
    assert h.bilgi_ara("bilgisi") == []


def test_arama_sorgusu_ozel_karakterlere_dayanikli():
    assert _arama_sorgusu('"; DROP TABLE -- ne?') is not None
    assert _arama_sorgusu("ve bu mi") is None
    Hafiza().bilgi_ara('" OR * NEAR(')


def test_dosyadan_bilgiler(tmp_path):
    from robot.cli import dosyadan_bilgiler

    f = tmp_path / "b.txt"
    f.write_text("\ufeff# yorum\n\nkisisel: Eşi Büşra.\ntercih: Çayı şekersiz sever.\n- Saat: 10:30 gibi gelir.\n", "utf-8")
    assert dosyadan_bilgiler(f) == [
        ("kisisel", "Eşi Büşra."),
        ("tercih", "Çayı şekersiz sever."),
        ("kisisel", "Saat: 10:30 gibi gelir."),
    ]
