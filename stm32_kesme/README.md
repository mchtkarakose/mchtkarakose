# STM32 Kesme (EXTI) – "Sinyal Hatası" Uyarısı (Proteus)

Ana program sürekli çalışır (LCD'de sayaç artar, yeşil LED yanıp söner).
Butona basılınca **EXTI0 kesmesi** gelir:

- LCD'nin 2. satırında **`SINYAL HATASI 01`** yazar (3 saniye kalır, sayı her hatada artar),
- **kırmızı LED 5 kez yanıp söner**,
- bu sırada **sayaç durmaz**, işlem devam eder.

Kesme rutini (`EXTI0_IRQHandler`) yalnızca bir bayrak kaldırır. LCD'ye yazma ve LED
yakıp söndürme işini ana döngü yapar. Böylece kesme kısa sürer ve program takılmaz.

## Dosyalar

| Dosya | Açıklama |
|---|---|
| `kesme.hex` | **Proteus'a doğrudan yüklenecek hazır dosya** |
| `main.c` | Program (register seviyesinde, HAL gerekmez) |
| `startup.c` | Vektör tablosu ve başlangıç kodu |
| `stm32f103c6.ld` | Bellek haritası (linker script) |
| `Makefile` | `make` ile yeniden derleme (arm-none-eabi-gcc) |

## Proteus Devresi

Kullanılan parçalar (Pick Devices): `STM32F103C6`, `LM016L`, `BUTTON`, `RES`, `LED-GREEN`, `LED-RED`.

| STM32 pini | Bağlantı |
|---|---|
| **PA0** | BUTTON → GND, ayrıca 10k direnç → 3.3V (pull-up) |
| **PA1** | 220Ω → LED-GREEN → GND (sistem çalışıyor) |
| **PA2** | 220Ω → LED-RED → GND (hata / kesme) |
| **PB10** | LCD RS |
| **PB11** | LCD E |
| **PB12** | LCD D4 |
| **PB13** | LCD D5 |
| **PB14** | LCD D6 |
| **PB15** | LCD D7 |

LCD (LM016L) diğer pinleri: **VSS → GND**, **VDD → POWER**, **VEE → GND**, **RW → GND**,
D0–D3 boş kalır.

```
         3.3V
          |
         [10k]
          |
PA0 ------+------[BUTTON]---- GND        PA1 --[220R]-->|-- GND  (yeşil)
                                         PA2 --[220R]-->|-- GND  (kırmızı)
PB10 -> RS   PB11 -> E
PB12 -> D4   PB13 -> D5   PB14 -> D6   PB15 -> D7     (LCD 16x2)
```

## Çalıştırma

1. STM32F103C6'ya çift tıkla → **Program File** kısmına `kesme.hex` dosyasını seç.
2. Crystal Frequency alanı varsa **8MHz** yap (program dahili 8 MHz HSI ile çalışır).
3. Proteus'ta güç uyarısı çıkarsa: *Design → Configure Power Rails* ile VDD / VDDA'yı
   **3.3V** (VCC) ağına, VSS / VSSA'yı **GND**'ye bağla.
4. ▶ Simülasyonu başlat:
   - 1. satır: `Sayac:    000001, 000002, ...`
   - 2. satır: `Durum: NORMAL`
5. Butona bas → 2. satır `SINYAL HATASI 01` olur, kırmızı LED yanıp söner,
   sayaç saymaya devam eder. 3 saniye sonra ekran tekrar `Durum: NORMAL` olur.

> İstersen butonun yerine PA0'a bir **DCLOCK / PULSE** üreteci bağlayıp
> sinyal hatasını otomatik olarak da oluşturabilirsin (her düşen kenar bir kesme).

## Nasıl çalışıyor?

1. `exti_ayarla()`: PA0 → EXTI0 hattına bağlanır (`AFIO_EXTICR1`), düşen kenar seçilir
   (`EXTI_FTSR`), maske açılır (`EXTI_IMR`) ve NVIC'te 6 numaralı EXTI0 kesmesi etkinleştirilir.
2. Butona basılınca PA0 0'a düşer → işlemci ana döngüyü bırakıp `EXTI0_IRQHandler`'a gider.
3. Kesme rutini `EXTI_PR` bitini temizler, 200 ms debounce kontrolü yapar,
   `hata_sayisi++` ve `hata_bayragi = 1` yapıp hemen geri döner.
4. Ana döngü kaldığı yerden devam eder, bayrağı görünce uyarıyı LCD'ye yazar ve
   kırmızı LED'i SysTick zamanlamasıyla (bloklamadan) yakıp söndürür.

## Yeniden derleme

```bash
sudo apt install gcc-arm-none-eabi
```

```bash
make
```

STM32CubeIDE veya Keil kullanmak istersen: yeni bir STM32F103C6 projesi aç ve
`main.c` içeriğini kendi `main.c`'nin yerine koy (`startup.c` ve `.ld` dosyasını
IDE kendisi sağlar). Derlenen `.hex` dosyasını Proteus'a yükle.
