/* Fixed-address layout for the Duke3D core.
 *
 * Same two-window scheme as the Doom core (text in IROM, read-only data in
 * DROM, both mapped from the same flash pages), with one addition: this engine
 * has real initialised globals (key-name tables, default settings), so the
 * blob carries a .data image after .rodata. The .data section's *virtual*
 * address is in the arena (the host's RAM), while its initial bytes are stored
 * after .rodata in the read-only region; core_init copies them across before
 * anything reads a global.
 *
 *   core_data_init_src = core_data_addr + SIZEOF(.rodata)
 *   .data VMA          = core_arena_addr
 *   .data LMA          = core_data_lma + SIZEOF(.rodata)   (contiguous in blob)
 *
 * arena_addr/arena_size in the entry table cover .data and .bss; the build
 * script patches the size from the linked sections.
 */
OUTPUT_FORMAT("elf32-xtensa-le")

core_text_addr = 0x43000000;
core_data_addr = 0x3DF00000;
core_arena_addr = 0x3DC00000;

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
        . = ALIGN(16);
    }

    core_data_init_src = core_data_addr + SIZEOF(.rodata);

    .data core_arena_addr : AT(core_data_lma + SIZEOF(.rodata))
    {
        *(.data .data.*)
        . = ALIGN(16);
    }

    __data_start = ADDR(.data);
    __data_end = ADDR(.data) + SIZEOF(.data);

    .bss (NOLOAD) : ALIGN(16)
    {
        *(.bss .bss.* .sbss .sbss.* COMMON)
        . = ALIGN(16);
    }

    /DISCARD/ :
    {
        *(.comment)
        *(.xt.prop)
        *(.debug*)
    }
}
