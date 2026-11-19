# Akıllı Sesli İletişim ve Etkileşim Robotu

İnsanlarla doğal Türkçe konuşabilen, söyleneni anlayıp yapay zekâ ile değerlendiren,
insan benzeri sesle yanıt veren ve **kalıcı hafızası** sayesinde önceki konuşmalardan
öğrenen bir robotun yazılım altyapısı.

Proje önce bilgisayarda geliştirilip test edilecek, ardından fiziksel robot donanımına
aktarılacak şekilde **modüler** tasarlanmıştır: ses tanıma, yapay zekâ, ses sentezi, hafıza
ve gövde (donanım) birbirinden bağımsız katmanlardır ve her biri ayrı ayrı değiştirilebilir.

## Mimari

```
  Mikrofon ──► Dinleyici (STT) ──► Beyin (Claude) ──► Cümle bölücü ──► Seslendirme kuyruğu ──► Konuşmacı (TTS) ──► Hoparlör
                                     │      ▲
                       hafıza araçları│      │ ilgili kayıtlar, özetler
                                     ▼      │
                                  Hafıza (SQLite)            Gövde: LED / ekran / motor durumları
```

| Modül | Dosya | Görevi |
|---|---|---|
| Ana döngü | `robot/uygulama.py` | dinle → düşün → konuş döngüsü, boşta kalma takibi, gecikme ölçümü |
| Beyin | `robot/beyin.py` | Claude ile akışlı (streaming) yanıt, araç kullanımı, konuşma özetleme |
| İstemler | `robot/istemler.py` | Robotun kişiliği, konuşma kuralları, hafıza bağlamının biçimi |
| Hafıza | `robot/memory/store.py` | Konuşmalar, öğretilen bilgiler, tercihler; Türkçe uyumlu arama |
| Hafıza araçları | `robot/memory/araclar.py` | Modelin hafızaya kaydetme / düzeltme / silme / arama araçları |
| Ses | `robot/speech/` | Dinleyici ve konuşmacı arayüzleri; klavye/konsol (test) ve Azure (gerçek ses) |
| Metin | `robot/metin.py` | Akan yanıtı seslendirilebilir cümlelere bölme, biçim temizleme |
| Gövde | `robot/govde.py` | Donanım soyutlaması (dinliyor / düşünüyor / konuşuyor durumları) |
| Arayüz | `robot/cli.py` | Komut satırı: sohbet, sesli çalıştırma, hafıza yönetimi |

## Kurulum

Python 3.11 veya üstü gerekir.

```bash
python -m venv .venv && source .venv/bin/activate
```

```bash
pip install -e ".[dev]"
```

```bash
cp robot.example.toml robot.toml
```

Claude API anahtarını ortam değişkeni olarak verin (anahtarlar ayar dosyasına yazılmaz):

```bash
export ANTHROPIC_API_KEY="..."
```

## Kullanım

### 1. Yazılı test modu (bilgisayarda)

Mikrofon ve hoparlör gerekmeden robotun beynini ve hafızasını test etmek için:

```bash
python -m robot sohbet --gecikme
```

Örnek:

```
Sen: Merhaba, benim adım Mehmet. Kedimin adı Pamuk, bunu unutma.
Robot: Memnun oldum Mehmet! Pamuk'u hafızama kaydettim.
Sen: çıkış
```

Bir sonraki çalıştırmada robot Mehmet'i ve Pamuk'u hatırlar; önceki konuşmanın özeti de
yeni konuşmaya bağlam olarak taşınır.

### 2. Sesli mod

İlk sürümde konuşma tanıma ve doğal ses için **Azure AI Speech** kullanılır
(Türkçe nöral sesler: `tr-TR-EmelNeural`, `tr-TR-AhmetNeural`).

```bash
pip install -e ".[azure]"
```

```bash
export AZURE_SPEECH_KEY="..." AZURE_SPEECH_REGION="westeurope"
```

`robot.toml` içinde `[ses]` bölümünde `dinleyici = "azure"` ve `konusmaci = "azure"` yapın, sonra:

```bash
python -m robot calistir --gecikme
```

"Görüşürüz", "hoşça kal" veya "kapan" dendiğinde robot kapanır.

### 3. Hafıza yönetimi (kullanıcı kontrolü)

Hafızadaki her şey kullanıcının kontrolündedir:

| Komut | İşlev |
|---|---|
| `python -m robot hafiza listele [--tur bilgi\|tercih\|kisisel]` | Kayıtlı bilgileri göster |
| `python -m robot hafiza ara <kelimeler>` | Bilgilerde ara |
| `python -m robot hafiza ekle <metin> --tur tercih` | Elle bilgi ekle |
| `python -m robot hafiza duzelt <no> <yeni metin>` | Bir bilgiyi düzelt |
| `python -m robot hafiza sil <no>` | Bir bilgiyi sil |
| `python -m robot hafiza konusmalar` | Geçmiş konuşmaları ve özetlerini listele |
| `python -m robot hafiza konusma <no>` | Bir konuşmanın tam dökümü |
| `python -m robot hafiza konusma-sil <no>` | Bir konuşmayı sil |
| `python -m robot hafiza disa-aktar hafiza.json` | Tüm hafızayı JSON olarak dışa aktar |
| `python -m robot hafiza temizle --onayla` | Tüm hafızayı kalıcı olarak sil |

Robota sesli olarak da "bunu unut", "hayır, kedimin adı Pamuk değil Boncuk" denebilir;
robot ilgili kaydı siler veya düzeltir.

Ayarlarla: `konusmalari_kaydet = false` yapılırsa konuşmalar ve özetleri hiç saklanmaz,
yalnızca açıkça öğretilen bilgiler tutulur.

## Hafıza ve öğrenme sistemi

Üç tür kalıcı bilgi tutulur:

- **bilgi** – kullanıcının öğrettiği genel bilgiler ("Komşumuz Ayşe Hanım öğretmendir")
- **tercih** – beğeniler ve istekler ("Çayı şekersiz içerim")
- **kisisel** – kullanıcıyla ilgili bilgiler ("Adım Mehmet", "Kedimin adı Pamuk")

Şifre, kimlik/kart numarası, sağlık ayrıntısı gibi hassas veriler, kullanıcı açıkça istemedikçe kaydedilmez.

Bağlamın kullanılması:

1. Her konuşmanın başında kişisel bilgiler, tercihler ve **son konuşmaların özetleri** modele verilir.
2. Her mesajda, söylenenle **ilgili kayıtlar** Türkçe uyumlu tam metin aramasıyla bulunup eklenir
   (Türkçe karakter ve ek farklarına dayanıklı: "kedim" → "kedisinin adı Pamuk").
3. Konuşma bittiğinde (kapanış ya da `bosta_kalma_dk` kadar sessizlik) konuşma özetlenip saklanır.
4. Kayıtlar kullanıcı kimliğine (`[robot] kullanici`) bağlıdır; ileride ses/yüz tanıma ile
   kişiye özel hafıza buna dayanarak kurulabilir.

## Gecikme (yanıt hızı)

Konuşmanın bitmesiyle robotun konuşmaya başlaması arasındaki süreyi kısaltmak için:

- **Akışlı yanıt + cümle cümle seslendirme:** Model ilk cümleyi bitirir bitirmez seslendirme başlar;
  ilk parça uzunsa virgülde daha da erken kesilir. Sonraki cümleler, önceki çalınırken üretilir.
- **Isıtma:** Açılışta ve boşta kaldıkça bağlantı açılır ve sabit istem önbelleğe yazılır; ilk soru da hızlı yanıtlanır.
- **Hızlı model seçeneği:** `robot.toml` içinde `model = "claude-haiku-5-5"` en düşük gecikmeyi verir.
- **İstem önbelleği:** Sistem istemi sabit tutulur, konuşma geçmişi önbelleğe alınır.
- **Düşük düşünme derinliği:** Sohbette `effort = "low"` varsayılandır (`robot.toml` → `[beyin]`).
- **Hızlı konuşma sonu algılama:** `sessizlik_ms` (varsayılan 600 ms) ile konuşmanın bittiğine hızlı karar verilir.
- **Önceden açılan TTS bağlantısı:** İlk cümlede bağlantı kurma beklemesi olmaz.
- `--gecikme` seçeneği her yanıtta "konuşma bitti → ilk ses" süresini gösterir.

## Testler

```bash
python -m pytest
```

Testler gerçek API'ye bağlanmaz; dil modeli sahte bir modelle taklit edilir.

## Yol haritası

**Aşama 1 – Bilgisayarda yazılım (bu sürüm)**
- [x] Modüler mimari, yazılı test modu
- [x] Claude ile akışlı, düşük gecikmeli diyalog
- [x] Kalıcı hafıza: konuşmalar, özetler, öğretilen bilgiler, tercihler
- [x] Kullanıcı kontrollü hafıza yönetimi (listele / düzelt / sil / dışa aktar / temizle)
- [x] Azure ile Türkçe konuşma tanıma ve doğal ses
- [ ] Söz kesme (robot konuşurken kullanıcı araya girince susması)
- [ ] Uyandırma kelimesi ("Hey Robi")

**Aşama 2 – Donanıma aktarım**
- [ ] Hedef kart: Raspberry Pi 5 (veya benzeri), mikrofon dizisi (yankı engellemeli), hoparlör
- [ ] `Govde` sınıfından türeyen donanım sürücüsü: durum LED'leri, ekranda yüz ifadesi, baş/göz servo motorları
- [ ] Ses yönü algılama ile konuşana dönme

**Aşama 3 – Gelişmiş yetenekler**
- [ ] Ses veya yüz tanıma ile kişiye özel hafıza (çok kullanıcı)
- [ ] Çevrimdışı çalışma seçenekleri (yerel konuşma tanıma ve ses sentezi; internet yokken temel yanıtlar)
- [ ] Kamera ile görme yeteneği
- [ ] Yeni yetenekler için araç (tool) eklentileri: hava durumu, takvim, hatırlatıcılar, ev otomasyonu

## Yeni bir ses sağlayıcısı eklemek

`robot/speech/base.py` içindeki `Dinleyici` (STT) veya `Konusmaci` (TTS) sınıfından türetin,
`robot/speech/__init__.py` içindeki `olustur()` fonksiyonuna adını ekleyin ve `robot.toml`
dosyasında seçin. Robotun geri kalanında değişiklik gerekmez.
