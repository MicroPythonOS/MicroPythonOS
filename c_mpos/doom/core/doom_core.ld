/* Fixed-address layout for the Doom core.
 *
 * Text in the instruction window, read-only data in the data window (same
 * reasoning as core.ld for the hello core), and the engine's globals in the
 * RAM arena the host maps at a fixed address.
 *
 * The data region starts at the next 64 KB boundary after the text: the loader
 * has to map it as a separate window, so it must begin on an MMU page. Its LMA
 * follows the text in the flat binary (AT below) while its VMA is the data
 * window, which is what objcopy needs to lay the blob out correctly.
 */
OUTPUT_FORMAT("elf32-xtensa-le")

core_text_addr = 0x43000000;
core_data_addr = 0x3DF00000;
core_arena_addr = 0x3DC00000;
core_arena_size = 0x80000;

SECTIONS
{
    . = core_text_addr;

    .core_entry : ALIGN(4)
    {
        KEEP(*(.core_entry))
    }

    .text : ALIGN(4)
    {
        *(.literal .literal.* .text .text.*)
    }

    . = ALIGN(0x10000);
    core_data_lma = .;

    .rodata core_data_addr : AT(core_data_lma)
    {
        *(.rodata .rodata.* .srodata .srodata.* .lit4 .lit4.*)
    }

    .bss core_arena_addr (NOLOAD) : ALIGN(4)
    {
        *(.bss .bss.* .sbss .sbss.* COMMON)
        . = ALIGN(4);
    }
    ASSERT(. <= core_arena_addr + core_arena_size,
           "DOOM core .bss does not fit the arena: raise core_arena_size")

    /DISCARD/ :
    {
        *(.data .data.*)
        *(.comment)
        *(.xt.prop)
        *(.debug*)
    }
}
