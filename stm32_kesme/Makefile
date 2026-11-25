CC      = arm-none-eabi-gcc
OBJCOPY = arm-none-eabi-objcopy
SIZE    = arm-none-eabi-size

CFLAGS  = -mcpu=cortex-m3 -mthumb -Os -g -Wall -Wextra -ffreestanding \
          -ffunction-sections -fdata-sections
LDFLAGS = -nostdlib -T stm32f103c6.ld -Wl,--gc-sections -Wl,-Map=kesme.map

all: kesme.hex

kesme.elf: main.c startup.c stm32f103c6.ld
	$(CC) $(CFLAGS) main.c startup.c $(LDFLAGS) -o $@
	$(SIZE) $@

kesme.hex: kesme.elf
	$(OBJCOPY) -O ihex $< $@

clean:
	rm -f kesme.elf kesme.hex kesme.map

.PHONY: all clean
