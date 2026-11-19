"""Modelin hafızayı yönetmek için kullandığı araçlar (tool use)."""

from __future__ import annotations

import json

from robot.memory.store import TURLER, Hafiza

ARACLAR = [
    {
        "name": "hafizaya_kaydet",
        "description": (
            "Kullanıcının öğrettiği bir bilgiyi, bir tercihini veya kendisiyle ilgili kişisel "
            "bir bilgiyi kalıcı hafızaya kaydeder. Yalnızca kullanıcı açıkça bir şey öğrettiğinde, "
            "hatırlamanı istediğinde ya da kalıcı bir tercih/kişisel bilgi paylaştığında kullan. "
            "İçeriği tek başına anlaşılır, kısa bir cümle olarak yaz (ör. 'Kullanıcının kedisinin "
            "adı Pamuk.'). Hafızada zaten benzeri varsa yenisini eklemek yerine hafizayi_guncelle kullan."
        ),
        "eager_input_streaming": True,
        "input_schema": {
            "type": "object",
            "properties": {
                "icerik": {"type": "string", "description": "Kaydedilecek bilgi, tek cümle."},
                "tur": {
                    "type": "string",
                    "enum": list(TURLER),
                    "description": "bilgi: öğretilen genel bilgi; tercih: beğeni/istek; kisisel: kullanıcı hakkında bilgi.",
                },
            },
            "required": ["icerik", "tur"],
            "additionalProperties": False,
        },
    },
    {
        "name": "hafizayi_guncelle",
        "description": "Hafızadaki bir kaydı numarasıyla düzeltir. Kullanıcı bir bilgiyi düzelttiğinde kullan.",
        "eager_input_streaming": True,
        "input_schema": {
            "type": "object",
            "properties": {
                "numara": {"type": "integer", "description": "Kaydın numarası (#12 ise 12)."},
                "icerik": {"type": "string", "description": "Kaydın yeni hali, tek cümle."},
            },
            "required": ["numara", "icerik"],
            "additionalProperties": False,
        },
    },
    {
        "name": "hafizadan_sil",
        "description": "Hafızadaki bir kaydı numarasıyla siler. Kullanıcı bir şeyi unutmanı istediğinde kullan.",
        "eager_input_streaming": True,
        "input_schema": {
            "type": "object",
            "properties": {"numara": {"type": "integer", "description": "Silinecek kaydın numarası."}},
            "required": ["numara"],
            "additionalProperties": False,
        },
    },
    {
        "name": "hafizada_ara",
        "description": (
            "Kalıcı hafızada anahtar kelimelerle arama yapar. Sana verilen hafıza özetinde olmayan "
            "bir şeyi hatırlaman gerektiğinde ya da silinecek/güncellenecek kaydın numarasını "
            "bulmak için kullan."
        ),
        "eager_input_streaming": True,
        "input_schema": {
            "type": "object",
            "properties": {"sorgu": {"type": "string", "description": "Aranacak anahtar kelimeler."}},
            "required": ["sorgu"],
            "additionalProperties": False,
        },
    },
]

_SEMALAR = {a["name"]: a["input_schema"] for a in ARACLAR}
_TIPLER = {"string": str, "integer": int}


class GecersizGirdi(ValueError):
    pass


def dogrula(ad: str, girdi: object) -> dict:
    """Araç girdisini şemaya göre doğrular (akışlı girdi eksik/bozuk gelebilir)."""
    sema = _SEMALAR.get(ad)
    if sema is None:
        raise GecersizGirdi(f"Bilinmeyen araç: {ad}")
    if not isinstance(girdi, dict):
        raise GecersizGirdi("Girdi bir nesne olmalı")
    ozellikler = sema["properties"]
    fazla = set(girdi) - set(ozellikler)
    if fazla:
        raise GecersizGirdi(f"Beklenmeyen alanlar: {sorted(fazla)}")
    for alan in sema["required"]:
        if alan not in girdi:
            raise GecersizGirdi(f"Eksik alan: {alan}")
    for alan, deger in girdi.items():
        tip = _TIPLER[ozellikler[alan]["type"]]
        if not isinstance(deger, tip) or isinstance(deger, bool):
            raise GecersizGirdi(f"{alan} alanının tipi hatalı")
        if "enum" in ozellikler[alan] and deger not in ozellikler[alan]["enum"]:
            raise GecersizGirdi(f"{alan} alanı şunlardan biri olmalı: {ozellikler[alan]['enum']}")
        if tip is str and not deger.strip():
            raise GecersizGirdi(f"{alan} boş olamaz")
    return girdi


def calistir(hafiza: Hafiza, ad: str, girdi: dict) -> str:
    """Doğrulanmış bir araç çağrısını çalıştırır, modele dönecek sonucu üretir."""
    if ad == "hafizaya_kaydet":
        no = hafiza.bilgi_ekle(girdi["icerik"], girdi["tur"])
        return f"Kaydedildi (#{no})."
    if ad == "hafizayi_guncelle":
        ok = hafiza.bilgi_guncelle(girdi["numara"], girdi["icerik"])
        return "Güncellendi." if ok else f"#{girdi['numara']} numaralı kayıt bulunamadı."
    if ad == "hafizadan_sil":
        ok = hafiza.bilgi_sil(girdi["numara"])
        return "Silindi." if ok else f"#{girdi['numara']} numaralı kayıt bulunamadı."
    if ad == "hafizada_ara":
        sonuclar = hafiza.bilgi_ara(girdi["sorgu"], limit=10)
        if not sonuclar:
            return "Hafızada eşleşen kayıt yok."
        return json.dumps(
            [{"numara": b.id, "tur": b.tur, "icerik": b.icerik} for b in sonuclar], ensure_ascii=False
        )
    raise GecersizGirdi(f"Bilinmeyen araç: {ad}")
