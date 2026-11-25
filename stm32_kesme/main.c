/*
 * STM32F103C6 - Harici Kesme (EXTI) ile "Sinyal Hatasi" Uyarisi
 * ---------------------------------------------------------------
 * Proteus'ta tamamen sanal calisacak sekilde yazildi (HAL yok, dogrudan register).
 *
 *  - Ana program surekli calisir: LCD'nin 1. satirinda bir sayac artar,
 *    yesil LED (PA1) "sistem calisiyor" diye yanip soner.
 *  - PA0'a bagli butona basilinca (dusen kenar) EXTI0 kesmesi olusur.
 *    Kesme rutini sadece bayrak kaldirir (kisa ve hizli).
 *  - Ana dongu bayragi gorunce:
 *      * LCD'nin 2. satirina "SINYAL HATASI nn" yazar (3 saniye),
 *      * kirmizi LED (PA2) 5 kez yanip soner,
 *    ve bu sirada sayac DURMADAN saymaya devam eder.
 *
 * Baglantilar:
 *   PA0  <- Buton (diger ucu GND), 10k pull-up -> 3.3V
 *   PA1  -> 220R -> Yesil LED -> GND   (calisiyor)
 *   PA2  -> 220R -> Kirmizi LED -> GND (hata)
 *   LCD 16x2 (LM016L), 4-bit mod, RW = GND
 *   PB10 -> RS, PB11 -> E, PB12..PB15 -> D4..D7
 *
 * Saat: dahili HSI 8 MHz (PLL yok), SysTick 1 ms.
 */

#include <stdint.h>

/* ------------------------- Register tanimlari ------------------------- */
#define REG(addr)        (*(volatile uint32_t *)(addr))

#define RCC_APB2ENR      REG(0x40021018)

#define GPIOA_BASE       0x40010800u
#define GPIOB_BASE       0x40010C00u
#define GPIO_CRL(b)      REG((b) + 0x00)
#define GPIO_CRH(b)      REG((b) + 0x04)
#define GPIO_IDR(b)      REG((b) + 0x08)
#define GPIO_ODR(b)      REG((b) + 0x0C)
#define GPIO_BSRR(b)     REG((b) + 0x10)
#define GPIO_BRR(b)      REG((b) + 0x14)

#define AFIO_EXTICR1     REG(0x40010008)

#define EXTI_IMR         REG(0x40010400)
#define EXTI_RTSR        REG(0x40010408)
#define EXTI_FTSR        REG(0x4001040C)
#define EXTI_PR          REG(0x40010414)

#define NVIC_ISER0       REG(0xE000E100)
#define NVIC_IPR_BYTE(n) (*(volatile uint8_t *)(0xE000E400 + (n)))
#define EXTI0_IRQn       6

#define SYST_CSR         REG(0xE000E010)
#define SYST_RVR         REG(0xE000E014)
#define SYST_CVR         REG(0xE000E018)

#define F_CPU            8000000u

/* ------------------------- Pin tanimlari ------------------------------ */
#define LED_YESIL        1   /* PA1 */
#define LED_KIRMIZI      2   /* PA2 */

#define LCD_RS           10  /* PB10 */
#define LCD_E            11  /* PB11 */
#define LCD_D4           12  /* PB12..PB15 = D4..D7 */

/* ------------------------- Global degiskenler ------------------------- */
static volatile uint32_t ms_tick = 0;        /* SysTick ile artar        */
static volatile uint8_t  hata_bayragi = 0;   /* Kesme -> ana dongu       */
static volatile uint32_t hata_sayisi = 0;
static volatile uint32_t son_kesme_ms = 0;   /* buton sicramasi (debounce) */

/* ------------------------- Kesme rutinleri ---------------------------- */
void SysTick_Handler(void)
{
    ms_tick++;
}

/* PA0 dusen kenar -> EXTI0. Kisa tutulur: sadece bayrak kaldirir. */
void EXTI0_IRQHandler(void)
{
    if (EXTI_PR & (1u << 0)) {
        EXTI_PR = (1u << 0);                 /* bekleyen biti temizle (1 yazarak) */
        if (ms_tick - son_kesme_ms > 200) {  /* 200 ms debounce */
            son_kesme_ms = ms_tick;
            hata_sayisi++;
            hata_bayragi = 1;
        }
    }
}

/* ------------------------- Yardimci fonksiyonlar ---------------------- */
static void delay_ms(uint32_t ms)
{
    uint32_t bas = ms_tick;
    while ((ms_tick - bas) < ms) { }
}

static void delay_kisa(uint32_t n)   /* ~ birkac mikrosaniye */
{
    while (n--) { __asm__ volatile ("nop"); }
}

static void pin_yaz(uint32_t port, uint32_t pin, uint32_t deger)
{
    if (deger) GPIO_BSRR(port) = (1u << pin);
    else       GPIO_BRR(port)  = (1u << pin);
}

/* ------------------------- LCD (HD44780, 4-bit) ----------------------- */
static void lcd_nibble(uint8_t n)
{
    /* D4..D7 = PB12..PB15 */
    GPIO_BRR(GPIOB_BASE)  = (0xFu << LCD_D4);
    GPIO_BSRR(GPIOB_BASE) = ((uint32_t)(n & 0x0F) << LCD_D4);
    pin_yaz(GPIOB_BASE, LCD_E, 1);
    delay_kisa(20);
    pin_yaz(GPIOB_BASE, LCD_E, 0);
    delay_kisa(20);
}

static void lcd_byte(uint8_t b, uint8_t veri_mi)
{
    pin_yaz(GPIOB_BASE, LCD_RS, veri_mi);
    lcd_nibble(b >> 4);
    lcd_nibble(b & 0x0F);
    delay_kisa(400);                         /* ~50 us komut suresi */
}

static void lcd_komut(uint8_t k)
{
    lcd_byte(k, 0);
    if (k == 0x01 || k == 0x02) delay_ms(2); /* clear / home uzun surer */
}

static void lcd_git(uint8_t satir, uint8_t sutun)
{
    lcd_komut((uint8_t)(0x80 | ((satir ? 0x40 : 0x00) + sutun)));
}

static void lcd_yazi(const char *s)
{
    while (*s) lcd_byte((uint8_t)*s++, 1);
}

static void lcd_baslat(void)
{
    delay_ms(20);
    pin_yaz(GPIOB_BASE, LCD_RS, 0);
    lcd_nibble(0x3); delay_ms(5);
    lcd_nibble(0x3); delay_ms(1);
    lcd_nibble(0x3); delay_ms(1);
    lcd_nibble(0x2); delay_ms(1);            /* 4-bit moda gec */
    lcd_komut(0x28);                         /* 4-bit, 2 satir, 5x8 */
    lcd_komut(0x0C);                         /* ekran acik, imlec kapali */
    lcd_komut(0x06);                         /* otomatik saga kay */
    lcd_komut(0x01);                         /* temizle */
}

/* sayi -> sabit genislikte metin (sola sifir doldurur) */
static void sayi_yazi(uint32_t sayi, char *buf, int basamak)
{
    for (int i = basamak - 1; i >= 0; i--) {
        buf[i] = (char)('0' + (sayi % 10));
        sayi /= 10;
    }
    buf[basamak] = '\0';
}

/* ------------------------- Donanim ayarlari --------------------------- */
static void gpio_ayarla(void)
{
    /* GPIOA, GPIOB ve AFIO saatlerini ac */
    RCC_APB2ENR |= (1u << 0) | (1u << 2) | (1u << 3);

    /* PA0: giris, pull-up (CNF=10, MODE=00 -> 0x8), ODR0=1 => pull-up
       PA1, PA2: cikis push-pull 2 MHz (0x2) */
    uint32_t crl = GPIO_CRL(GPIOA_BASE);
    crl &= ~(0xFFFu);
    crl |=  (0x8u << 0) | (0x2u << 4) | (0x2u << 8);
    GPIO_CRL(GPIOA_BASE) = crl;
    GPIO_BSRR(GPIOA_BASE) = (1u << 0);                 /* pull-up sec */
    GPIO_BRR(GPIOA_BASE)  = (1u << LED_YESIL) | (1u << LED_KIRMIZI);

    /* PB10..PB15: cikis push-pull 2 MHz (LCD) */
    uint32_t crh = GPIO_CRH(GPIOB_BASE);
    crh &= ~(0xFFFFFFu << 8);
    crh |=  (0x222222u << 8);
    GPIO_CRH(GPIOB_BASE) = crh;
    GPIO_BRR(GPIOB_BASE) = (0x3Fu << 10);
}

static void exti_ayarla(void)
{
    AFIO_EXTICR1 &= ~0xFu;            /* EXTI0 kaynagi = PA0 */
    EXTI_FTSR    |=  (1u << 0);       /* dusen kenar (butona basinca) */
    EXTI_RTSR    &= ~(1u << 0);
    EXTI_PR       =  (1u << 0);       /* eski bekleyen kesmeyi temizle */
    EXTI_IMR     |=  (1u << 0);       /* kesme maskesini ac */

    NVIC_IPR_BYTE(EXTI0_IRQn) = 0x40; /* oncelik */
    NVIC_ISER0 = (1u << EXTI0_IRQn);  /* NVIC'te EXTI0'i etkinlestir */
}

static void systick_ayarla(void)
{
    SYST_RVR = (F_CPU / 1000u) - 1u;  /* 1 ms */
    SYST_CVR = 0;
    SYST_CSR = 0x7;                   /* islemci saati, kesme acik, calis */
}

/* ------------------------- Ana program -------------------------------- */
int main(void)
{
    char buf[8];

    gpio_ayarla();
    systick_ayarla();
    lcd_baslat();

    lcd_git(0, 0); lcd_yazi("Sayac:          ");
    lcd_git(1, 0); lcd_yazi("Durum: NORMAL   ");

    exti_ayarla();                    /* kesmeyi en son ac */

    uint32_t sayac = 0;
    uint32_t t_sayac = 0, t_yesil = 0, t_kirmizi = 0;
    uint32_t uyari_bitis = 0;
    uint8_t  uyari_aktif = 0;
    uint8_t  kirmizi_adim = 0;        /* kalan yak/sondur adimi */

    for (;;) {
        uint32_t simdi = ms_tick;

        /* 1) Ana is: sayac her 250 ms artar - kesme gelse de durmaz */
        if (simdi - t_sayac >= 250) {
            t_sayac = simdi;
            sayac++;
            sayi_yazi(sayac, buf, 6);
            lcd_git(0, 10); lcd_yazi(buf);
        }

        /* 2) Calisiyor LED'i (yesil) 500 ms'de bir yanip soner */
        if (simdi - t_yesil >= 500) {
            t_yesil = simdi;
            GPIO_ODR(GPIOA_BASE) ^= (1u << LED_YESIL);
        }

        /* 3) Kesmeden gelen bayrak var mi? */
        if (hata_bayragi) {
            hata_bayragi = 0;
            uyari_aktif  = 1;
            uyari_bitis  = simdi + 3000;          /* 3 sn ekranda kalsin */
            kirmizi_adim = 10;                    /* 5 kez yan-son */
            t_kirmizi    = simdi;

            sayi_yazi(hata_sayisi % 100, buf, 2);
            lcd_git(1, 0); lcd_yazi("SINYAL HATASI ");
            lcd_yazi(buf);
        }

        /* 4) Kirmizi LED'i yanip sondur (bloklamadan) */
        if (kirmizi_adim && (simdi - t_kirmizi >= 150)) {
            t_kirmizi = simdi;
            GPIO_ODR(GPIOA_BASE) ^= (1u << LED_KIRMIZI);
            if (--kirmizi_adim == 0) GPIO_BRR(GPIOA_BASE) = (1u << LED_KIRMIZI);
        }

        /* 5) Uyari suresi doldu -> normal ekrana don */
        if (uyari_aktif && (int32_t)(simdi - uyari_bitis) >= 0) {
            uyari_aktif = 0;
            lcd_git(1, 0); lcd_yazi("Durum: NORMAL   ");
        }
    }
}
