"""Kalıcı hafıza (SQLite).

Saklananlar:
  * konusmalar / mesajlar : Önceki konuşmaların kaydı ve özetleri
  * bilgiler              : Kullanıcının öğrettiği bilgiler, tercihleri ve
                            kendisiyle ilgili kişisel bilgiler

Tüm veriler kullanıcının kontrolündedir: listelenebilir, aranabilir,
düzeltilebilir, silinebilir ve dışa aktarılabilir.
"""

from __future__ import annotations

import json
import re
import sqlite3
import threading
from dataclasses import asdict, dataclass
from datetime import datetime
from pathlib import Path

TURLER = ("bilgi", "tercih", "kisisel")

_TR = str.maketrans("çğıöşüâîûÇĞIİÖŞÜÂÎÛ", "cgiosuaiucgiiosuaiu")
_DURAK = {
    "ve", "veya", "ile", "bir", "bu", "su", "o", "da", "de", "ki", "mi", "mu",
    "ne", "ben", "sen", "biz", "siz", "icin", "gibi", "cok", "daha", "en",
    "ama", "ise", "var", "yok", "beni", "bana", "sana", "nasil", "neden",
    "hangi", "kim", "acaba", "evet", "hayir", "tamam", "lutfen",
}

_SEMA = """
CREATE TABLE IF NOT EXISTS konusmalar (
    id INTEGER PRIMARY KEY,
    kullanici TEXT NOT NULL,
    baslangic TEXT NOT NULL,
    bitis TEXT,
    ozet TEXT
);
CREATE TABLE IF NOT EXISTS mesajlar (
    id INTEGER PRIMARY KEY,
    konusma_id INTEGER NOT NULL REFERENCES konusmalar(id) ON DELETE CASCADE,
    rol TEXT NOT NULL CHECK (rol IN ('kullanici', 'robot')),
    metin TEXT NOT NULL,
    zaman TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS bilgiler (
    id INTEGER PRIMARY KEY,
    kullanici TEXT NOT NULL,
    tur TEXT NOT NULL CHECK (tur IN ('bilgi', 'tercih', 'kisisel')),
    icerik TEXT NOT NULL,
    kaynak TEXT NOT NULL DEFAULT 'konusma',
    olusturma TEXT NOT NULL,
    guncelleme TEXT NOT NULL
);
CREATE VIRTUAL TABLE IF NOT EXISTS bilgiler_ara USING fts5(metin);
CREATE INDEX IF NOT EXISTS ix_bilgi_kullanici ON bilgiler(kullanici, tur);
CREATE INDEX IF NOT EXISTS ix_mesaj_konusma ON mesajlar(konusma_id);
"""


def normalize(metin: str) -> str:
    """Aramada Türkçe karakter ve büyük/küçük harf farkını ortadan kaldırır."""
    return metin.translate(_TR).lower()


def _arama_sorgusu(metin: str) -> str | None:
    """Serbest metinden FTS5 sorgusu üretir.

    Türkçe eklemeli bir dil olduğu için ('kedim', 'kedimin', 'kedi') kelime
    köklerine yaklaşmak üzere kelimenin başından (en fazla 5, son harfi atarak)
    önek araması yapılır: 'kedim' -> 'kedi*'.
    """
    kelimeler = re.findall(r"\w+", normalize(metin))
    terimler = []
    for k in kelimeler:
        if len(k) < 3 or k in _DURAK:
            continue
        terimler.append(f'"{k[: max(3, min(len(k) - 1, 5))]}"*')
    return " OR ".join(dict.fromkeys(terimler)) or None


def _simdi() -> str:
    return datetime.now().isoformat(timespec="seconds")


@dataclass
class Bilgi:
    id: int
    tur: str
    icerik: str
    kaynak: str
    olusturma: str
    guncelleme: str


class Hafiza:
    def __init__(self, yol: str | Path = ":memory:", kullanici: str = "varsayilan"):
        if str(yol) != ":memory:":
            Path(yol).parent.mkdir(parents=True, exist_ok=True)
        self._db = sqlite3.connect(str(yol), check_same_thread=False)
        self._db.row_factory = sqlite3.Row
        self._db.execute("PRAGMA foreign_keys = ON")
        self._db.executescript(_SEMA)
        self._kilit = threading.Lock()
        self.kullanici = kullanici

    def kapat(self) -> None:
        self._db.close()

    # ------------------------------------------------------------------ bilgiler

    def bilgi_ekle(self, icerik: str, tur: str = "bilgi", kaynak: str = "konusma") -> int:
        icerik = icerik.strip()
        if tur not in TURLER:
            raise ValueError(f"Geçersiz tür: {tur}")
        if not icerik:
            raise ValueError("Boş bilgi kaydedilemez")
        with self._kilit, self._db:
            # Birebir aynısı zaten varsa tekrar ekleme
            var = self._db.execute(
                "SELECT id FROM bilgiler WHERE kullanici=? AND tur=? AND icerik=?",
                (self.kullanici, tur, icerik),
            ).fetchone()
            if var:
                return var["id"]
            zaman = _simdi()
            cur = self._db.execute(
                "INSERT INTO bilgiler (kullanici, tur, icerik, kaynak, olusturma, guncelleme)"
                " VALUES (?, ?, ?, ?, ?, ?)",
                (self.kullanici, tur, icerik, kaynak, zaman, zaman),
            )
            self._db.execute(
                "INSERT INTO bilgiler_ara (rowid, metin) VALUES (?, ?)",
                (cur.lastrowid, normalize(icerik)),
            )
            return cur.lastrowid

    def bilgi_guncelle(self, bilgi_id: int, icerik: str) -> bool:
        icerik = icerik.strip()
        if not icerik:
            raise ValueError("Boş bilgi kaydedilemez")
        with self._kilit, self._db:
            cur = self._db.execute(
                "UPDATE bilgiler SET icerik=?, guncelleme=? WHERE id=? AND kullanici=?",
                (icerik, _simdi(), bilgi_id, self.kullanici),
            )
            if cur.rowcount:
                self._db.execute(
                    "UPDATE bilgiler_ara SET metin=? WHERE rowid=?", (normalize(icerik), bilgi_id)
                )
            return cur.rowcount > 0

    def bilgi_sil(self, bilgi_id: int) -> bool:
        with self._kilit, self._db:
            cur = self._db.execute(
                "DELETE FROM bilgiler WHERE id=? AND kullanici=?", (bilgi_id, self.kullanici)
            )
            if cur.rowcount:
                self._db.execute("DELETE FROM bilgiler_ara WHERE rowid=?", (bilgi_id,))
            return cur.rowcount > 0

    def bilgi_getir(self, bilgi_id: int) -> Bilgi | None:
        satir = self._db.execute(
            "SELECT * FROM bilgiler WHERE id=? AND kullanici=?", (bilgi_id, self.kullanici)
        ).fetchone()
        return self._bilgi(satir) if satir else None

    def bilgileri_listele(self, tur: str | None = None, limit: int | None = None) -> list[Bilgi]:
        sql = "SELECT * FROM bilgiler WHERE kullanici=?"
        param: list = [self.kullanici]
        if tur:
            sql += " AND tur=?"
            param.append(tur)
        sql += " ORDER BY guncelleme DESC, id DESC"
        if limit:
            sql += " LIMIT ?"
            param.append(limit)
        return [self._bilgi(s) for s in self._db.execute(sql, param)]

    def bilgi_ara(self, sorgu: str, limit: int = 5, tur: str | None = None) -> list[Bilgi]:
        fts = _arama_sorgusu(sorgu)
        if not fts:
            return []
        sql = (
            "SELECT b.* FROM bilgiler_ara a JOIN bilgiler b ON b.id = a.rowid"
            " WHERE bilgiler_ara MATCH ? AND b.kullanici=?"
        )
        param: list = [fts, self.kullanici]
        if tur:
            sql += " AND b.tur=?"
            param.append(tur)
        sql += " ORDER BY bm25(bilgiler_ara) LIMIT ?"
        param.append(limit)
        return [self._bilgi(s) for s in self._db.execute(sql, param)]

    @staticmethod
    def _bilgi(satir: sqlite3.Row) -> Bilgi:
        return Bilgi(
            id=satir["id"],
            tur=satir["tur"],
            icerik=satir["icerik"],
            kaynak=satir["kaynak"],
            olusturma=satir["olusturma"],
            guncelleme=satir["guncelleme"],
        )

    # ---------------------------------------------------------------- konuşmalar

    def konusma_baslat(self) -> int:
        with self._kilit, self._db:
            cur = self._db.execute(
                "INSERT INTO konusmalar (kullanici, baslangic) VALUES (?, ?)",
                (self.kullanici, _simdi()),
            )
            return cur.lastrowid

    def mesaj_ekle(self, konusma_id: int, rol: str, metin: str) -> None:
        with self._kilit, self._db:
            self._db.execute(
                "INSERT INTO mesajlar (konusma_id, rol, metin, zaman) VALUES (?, ?, ?, ?)",
                (konusma_id, rol, metin, _simdi()),
            )

    def konusma_bitir(self, konusma_id: int, ozet: str | None = None) -> None:
        with self._kilit, self._db:
            self._db.execute(
                "UPDATE konusmalar SET bitis=?, ozet=COALESCE(?, ozet) WHERE id=?",
                (_simdi(), ozet, konusma_id),
            )

    def mesajlar(self, konusma_id: int) -> list[dict]:
        return [
            dict(s)
            for s in self._db.execute(
                "SELECT rol, metin, zaman FROM mesajlar WHERE konusma_id=? ORDER BY id",
                (konusma_id,),
            )
        ]

    def konusmalari_listele(self, limit: int = 20) -> list[dict]:
        return [
            dict(s)
            for s in self._db.execute(
                "SELECT k.id, k.baslangic, k.bitis, k.ozet,"
                " (SELECT COUNT(*) FROM mesajlar m WHERE m.konusma_id = k.id) AS mesaj_sayisi"
                " FROM konusmalar k WHERE k.kullanici=? ORDER BY k.id DESC LIMIT ?",
                (self.kullanici, limit),
            )
        ]

    def son_ozetler(self, adet: int = 3, haric: int | None = None) -> list[dict]:
        return [
            dict(s)
            for s in self._db.execute(
                "SELECT id, baslangic, ozet FROM konusmalar"
                " WHERE kullanici=? AND ozet IS NOT NULL AND id IS NOT ?"
                " ORDER BY id DESC LIMIT ?",
                (self.kullanici, haric, adet),
            )
        ][::-1]

    def konusma_sil(self, konusma_id: int) -> bool:
        with self._kilit, self._db:
            cur = self._db.execute(
                "DELETE FROM konusmalar WHERE id=? AND kullanici=?", (konusma_id, self.kullanici)
            )
            return cur.rowcount > 0

    # ------------------------------------------------------------ toplu yönetim

    def disa_aktar(self) -> dict:
        konusmalar = []
        for k in self.konusmalari_listele(limit=1_000_000):
            k["mesajlar"] = self.mesajlar(k["id"])
            konusmalar.append(k)
        return {
            "kullanici": self.kullanici,
            "disa_aktarma_zamani": _simdi(),
            "bilgiler": [asdict(b) for b in self.bilgileri_listele()],
            "konusmalar": konusmalar,
        }

    def disa_aktar_dosya(self, yol: str | Path) -> None:
        Path(yol).write_text(json.dumps(self.disa_aktar(), ensure_ascii=False, indent=2), "utf-8")

    def tumunu_sil(self) -> None:
        """Bu kullanıcıya ait tüm hafızayı kalıcı olarak siler."""
        with self._kilit, self._db:
            self._db.execute(
                "DELETE FROM bilgiler_ara WHERE rowid IN (SELECT id FROM bilgiler WHERE kullanici=?)",
                (self.kullanici,),
            )
            self._db.execute("DELETE FROM bilgiler WHERE kullanici=?", (self.kullanici,))
            self._db.execute("DELETE FROM konusmalar WHERE kullanici=?", (self.kullanici,))
