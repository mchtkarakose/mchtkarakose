/* STM32F103C6 icin minimal baslangic kodu ve kesme vektor tablosu */
#include <stdint.h>

extern uint32_t _sidata, _sdata, _edata, _sbss, _ebss, _estack;
extern int main(void);

void Reset_Handler(void);
void Default_Handler(void) { for (;;) { } }

void NMI_Handler(void)        __attribute__((weak, alias("Default_Handler")));
void HardFault_Handler(void)  __attribute__((weak, alias("Default_Handler")));
void MemManage_Handler(void)  __attribute__((weak, alias("Default_Handler")));
void BusFault_Handler(void)   __attribute__((weak, alias("Default_Handler")));
void UsageFault_Handler(void) __attribute__((weak, alias("Default_Handler")));
void SVC_Handler(void)        __attribute__((weak, alias("Default_Handler")));
void DebugMon_Handler(void)   __attribute__((weak, alias("Default_Handler")));
void PendSV_Handler(void)     __attribute__((weak, alias("Default_Handler")));
void SysTick_Handler(void)    __attribute__((weak, alias("Default_Handler")));
void EXTI0_IRQHandler(void)   __attribute__((weak, alias("Default_Handler")));

__attribute__((section(".isr_vector"), used))
void (* const vektor_tablosu[])(void) = {
    (void (*)(void))&_estack,
    Reset_Handler,
    NMI_Handler,
    HardFault_Handler,
    MemManage_Handler,
    BusFault_Handler,
    UsageFault_Handler,
    0, 0, 0, 0,
    SVC_Handler,
    DebugMon_Handler,
    0,
    PendSV_Handler,
    SysTick_Handler,
    /* Harici kesmeler (IRQ0..IRQ6) */
    Default_Handler,   /* 0 WWDG   */
    Default_Handler,   /* 1 PVD    */
    Default_Handler,   /* 2 TAMPER */
    Default_Handler,   /* 3 RTC    */
    Default_Handler,   /* 4 FLASH  */
    Default_Handler,   /* 5 RCC    */
    EXTI0_IRQHandler,  /* 6 EXTI0  */
};

void Reset_Handler(void)
{
    uint32_t *src = &_sidata, *dst = &_sdata;
    while (dst < &_edata) *dst++ = *src++;      /* .data kopyala */
    for (dst = &_sbss; dst < &_ebss; ) *dst++ = 0; /* .bss sifirla */
    main();
    for (;;) { }
}
