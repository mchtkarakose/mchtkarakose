#include <stdint.h>

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

#define LED_YESIL        1
#define LED_KIRMIZI      2

#define LCD_RS           10
#define LCD_E            11
#define LCD_D4           12

static volatile uint32_t ms_tick = 0;
static volatile uint8_t  hata_bayragi = 0;
static volatile uint32_t hata_sayisi = 0;
static volatile uint32_t son_kesme_ms = 0;

void SysTick_Handler(void)
{
    ms_tick++;
}

void EXTI0_IRQHandler(void)
{
    if (EXTI_PR & (1u << 0)) {
        EXTI_PR = (1u << 0);
        if (ms_tick - son_kesme_ms > 200) {
            son_kesme_ms = ms_tick;
            hata_sayisi++;
            hata_bayragi = 1;
        }
    }
}

static void delay_ms(uint32_t ms)
{
    uint32_t bas = ms_tick;
    while ((ms_tick - bas) < ms) { }
}

static void delay_kisa(uint32_t n)
{
    while (n--) { __asm__ volatile ("nop"); }
}

static void pin_yaz(uint32_t port, uint32_t pin, uint32_t deger)
{
    if (deger) GPIO_BSRR(port) = (1u << pin);
    else       GPIO_BRR(port)  = (1u << pin);
}

static void lcd_nibble(uint8_t n)
{

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
    delay_kisa(400);
}

static void lcd_komut(uint8_t k)
{
    lcd_byte(k, 0);
    if (k == 0x01 || k == 0x02) delay_ms(2);
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
    lcd_nibble(0x2); delay_ms(1);
    lcd_komut(0x28);
    lcd_komut(0x0C);
    lcd_komut(0x06);
    lcd_komut(0x01);
}

static void sayi_yazi(uint32_t sayi, char *buf, int basamak)
{
    for (int i = basamak - 1; i >= 0; i--) {
        buf[i] = (char)('0' + (sayi % 10));
        sayi /= 10;
    }
    buf[basamak] = '\0';
}

static void gpio_ayarla(void)
{

    RCC_APB2ENR |= (1u << 0) | (1u << 2) | (1u << 3);

    uint32_t crl = GPIO_CRL(GPIOA_BASE);
    crl &= ~(0xFFFu);
    crl |=  (0x8u << 0) | (0x2u << 4) | (0x2u << 8);
    GPIO_CRL(GPIOA_BASE) = crl;
    GPIO_BSRR(GPIOA_BASE) = (1u << 0);
    GPIO_BRR(GPIOA_BASE)  = (1u << LED_YESIL) | (1u << LED_KIRMIZI);

    uint32_t crh = GPIO_CRH(GPIOB_BASE);
    crh &= ~(0xFFFFFFu << 8);
    crh |=  (0x222222u << 8);
    GPIO_CRH(GPIOB_BASE) = crh;
    GPIO_BRR(GPIOB_BASE) = (0x3Fu << 10);
}

static void exti_ayarla(void)
{
    AFIO_EXTICR1 &= ~0xFu;
    EXTI_FTSR    |=  (1u << 0);
    EXTI_RTSR    &= ~(1u << 0);
    EXTI_PR       =  (1u << 0);
    EXTI_IMR     |=  (1u << 0);

    NVIC_IPR_BYTE(EXTI0_IRQn) = 0x40;
    NVIC_ISER0 = (1u << EXTI0_IRQn);
}

static void systick_ayarla(void)
{
    SYST_RVR = (F_CPU / 1000u) - 1u;
    SYST_CVR = 0;
    SYST_CSR = 0x7;
}

int main(void)
{
    char buf[8];

    gpio_ayarla();
    systick_ayarla();
    lcd_baslat();

    lcd_git(0, 0); lcd_yazi("Sayac:          ");
    lcd_git(1, 0); lcd_yazi("Durum: NORMAL   ");

    exti_ayarla();

    uint32_t sayac = 0;
    uint32_t t_sayac = 0, t_yesil = 0, t_kirmizi = 0;
    uint32_t uyari_bitis = 0;
    uint8_t  uyari_aktif = 0;
    uint8_t  kirmizi_adim = 0;

    for (;;) {
        uint32_t simdi = ms_tick;

        if (simdi - t_sayac >= 250) {
            t_sayac = simdi;
            sayac++;
            sayi_yazi(sayac, buf, 6);
            lcd_git(0, 10); lcd_yazi(buf);
        }

        if (simdi - t_yesil >= 500) {
            t_yesil = simdi;
            GPIO_ODR(GPIOA_BASE) ^= (1u << LED_YESIL);
        }

        if (hata_bayragi) {
            hata_bayragi = 0;
            uyari_aktif  = 1;
            uyari_bitis  = simdi + 3000;
            kirmizi_adim = 10;
            t_kirmizi    = simdi;

            sayi_yazi(hata_sayisi % 100, buf, 2);
            lcd_git(1, 0); lcd_yazi("SINYAL HATASI ");
            lcd_yazi(buf);
        }

        if (kirmizi_adim && (simdi - t_kirmizi >= 150)) {
            t_kirmizi = simdi;
            GPIO_ODR(GPIOA_BASE) ^= (1u << LED_KIRMIZI);
            if (--kirmizi_adim == 0) GPIO_BRR(GPIOA_BASE) = (1u << LED_KIRMIZI);
        }

        if (uyari_aktif && (int32_t)(simdi - uyari_bitis) >= 0) {
            uyari_aktif = 0;
            lcd_git(1, 0); lcd_yazi("Durum: NORMAL   ");
        }
    }
}
