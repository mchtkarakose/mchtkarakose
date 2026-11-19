"""Komut satırı arayüzü.

  python -m robot sohbet              Yazılı test modu (klavye + ekran)
  python -m robot calistir            Ayarlardaki ses sağlayıcılarıyla çalıştır
  python -m robot hafiza listele      Hafızayı yönet (bkz. --help)
"""

from __future__ import annotations

import argparse
import json
import logging
import sys

from robot import config
from robot.memory.store import TURLER, Hafiza


def _hafiza(ayarlar) -> Hafiza:
    return Hafiza(ayarlar.hafiza.veritabani, kullanici=ayarlar.robot.kullanici)


def _robot_kur(ayarlar, metin_modu: bool, gecikme: bool):
    from robot.beyin import Beyin, ClaudeModel
    from robot.speech import olustur
    from robot.uygulama import Robot

    if metin_modu:
        ayarlar.ses.dinleyici = "klavye"
        ayarlar.ses.konusmaci = "konsol"
    dinleyici, konusmaci = olustur(ayarlar.ses, ayarlar)
    beyin = Beyin(ClaudeModel(ayarlar.beyin), _hafiza(ayarlar), ayarlar.hafiza, ayarlar.robot.ad)
    return Robot(
        beyin,
        dinleyici,
        konusmaci,
        bosta_kalma_sn=ayarlar.hafiza.bosta_kalma_dk * 60,
        gecikme_goster=gecikme,
        yaziya_dok=ayarlar.ses.konusmaci != "konsol",
    )


def _calistir(args, ayarlar) -> int:
    if args.komut == "calistir":
        print(
            f"Ses ayarı: dinleyici={ayarlar.ses.dinleyici}, konusmaci={ayarlar.ses.konusmaci}\n"
            "Hazırlanıyor (ortam gürültüsü ölçülüyor, lütfen bir saniye sessiz kalın)...",
            flush=True,
        )
    robot = _robot_kur(ayarlar, metin_modu=args.komut == "sohbet", gecikme=args.gecikme)
    if args.komut == "sohbet":
        print(f"{ayarlar.robot.ad} hazır. Çıkmak için 'çıkış' yazın.\n")
    else:
        print(f"{ayarlar.robot.ad} hazır. Konuşabilirsiniz; kapatmak için 'görüşürüz' deyin.\n", flush=True)
    try:
        robot.calistir()
    except TypeError as e:
        if "authentication" not in str(e):
            raise
        print(
            "\nClaude API anahtarı bulunamadı. ANTHROPIC_API_KEY ortam değişkenini ayarlayın"
            " (veya 'ant auth login' ile giriş yapın).",
            file=sys.stderr,
        )
        return 2
    return 0


def _hafiza_komutu(args, ayarlar) -> int:
    h = _hafiza(ayarlar)
    k = args.hafiza_komut
    if k == "listele":
        bilgiler = h.bilgileri_listele(args.tur)
        if not bilgiler:
            print("Hafızada kayıtlı bilgi yok.")
        for b in bilgiler:
            print(f"#{b.id:<4} {b.tur:<8} {b.icerik}   ({b.guncelleme})")
    elif k == "ara":
        for b in h.bilgi_ara(" ".join(args.sorgu), limit=20):
            print(f"#{b.id:<4} {b.tur:<8} {b.icerik}")
    elif k == "ekle":
        no = h.bilgi_ekle(" ".join(args.icerik), args.tur, kaynak="elle")
        print(f"Eklendi: #{no}")
    elif k == "duzelt":
        print("Güncellendi." if h.bilgi_guncelle(args.numara, " ".join(args.icerik)) else "Kayıt bulunamadı.")
    elif k == "sil":
        print("Silindi." if h.bilgi_sil(args.numara) else "Kayıt bulunamadı.")
    elif k == "konusmalar":
        for c in h.konusmalari_listele(args.adet):
            print(f"#{c['id']:<4} {c['baslangic']}  {c['mesaj_sayisi']} mesaj  {c['ozet'] or '(özet yok)'}")
    elif k == "konusma":
        for m in h.mesajlar(args.numara):
            print(f"[{m['zaman']}] {m['rol']}: {m['metin']}")
    elif k == "konusma-sil":
        print("Silindi." if h.konusma_sil(args.numara) else "Konuşma bulunamadı.")
    elif k == "disa-aktar":
        if args.dosya == "-":
            print(json.dumps(h.disa_aktar(), ensure_ascii=False, indent=2))
        else:
            h.disa_aktar_dosya(args.dosya)
            print(f"Hafıza '{args.dosya}' dosyasına aktarıldı.")
    elif k == "temizle":
        if not args.onayla:
            print("Bu işlem tüm bilgileri ve konuşmaları kalıcı olarak siler. Onaylamak için --onayla ekleyin.")
            return 1
        h.tumunu_sil()
        print("Hafıza temizlendi.")
    h.kapat()
    return 0


def parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="robot", description="Akıllı Sesli İletişim ve Etkileşim Robotu")
    p.add_argument("--ayar", help="Ayar dosyası (varsayılan: robot.toml)")
    p.add_argument("-v", "--ayrintili", action="store_true", help="Ayrıntılı kayıt (log) çıktısı")
    alt = p.add_subparsers(dest="komut", required=True)

    for ad, yardim in (("sohbet", "Yazılı test modu"), ("calistir", "Sesli mod (ayarlara göre)")):
        s = alt.add_parser(ad, help=yardim)
        s.add_argument("--gecikme", action="store_true", help="Her yanıtın gecikmesini göster")

    h = alt.add_parser("hafiza", help="Hafızayı görüntüle ve yönet")
    ha = h.add_subparsers(dest="hafiza_komut", required=True)
    s = ha.add_parser("listele", help="Kayıtlı bilgileri listele")
    s.add_argument("--tur", choices=TURLER)
    s = ha.add_parser("ara", help="Bilgilerde ara")
    s.add_argument("sorgu", nargs="+")
    s = ha.add_parser("ekle", help="Elle bilgi ekle")
    s.add_argument("icerik", nargs="+")
    s.add_argument("--tur", choices=TURLER, default="bilgi")
    s = ha.add_parser("duzelt", help="Bir bilgiyi düzelt")
    s.add_argument("numara", type=int)
    s.add_argument("icerik", nargs="+")
    s = ha.add_parser("sil", help="Bir bilgiyi sil")
    s.add_argument("numara", type=int)
    s = ha.add_parser("konusmalar", help="Geçmiş konuşmaları listele")
    s.add_argument("--adet", type=int, default=20)
    s = ha.add_parser("konusma", help="Bir konuşmanın dökümünü göster")
    s.add_argument("numara", type=int)
    s = ha.add_parser("konusma-sil", help="Bir konuşmayı sil")
    s.add_argument("numara", type=int)
    s = ha.add_parser("disa-aktar", help="Tüm hafızayı JSON olarak dışa aktar")
    s.add_argument("dosya", help="Dosya yolu ('-' ekrana yazar)")
    s = ha.add_parser("temizle", help="Tüm hafızayı sil")
    s.add_argument("--onayla", action="store_true")
    return p


def main(argv: list[str] | None = None) -> int:
    args = parser().parse_args(argv)
    logging.basicConfig(
        level=logging.DEBUG if args.ayrintili else logging.WARNING,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )
    if not args.ayrintili:
        logging.getLogger("robot").setLevel(logging.WARNING)
    ayarlar = config.yukle(args.ayar)
    if args.komut == "hafiza":
        return _hafiza_komutu(args, ayarlar)
    return _calistir(args, ayarlar)


if __name__ == "__main__":
    sys.exit(main())
