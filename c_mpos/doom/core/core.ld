/* Fixed-address layout for an mpos_core blob.
 *
 * The S3 has two windows for external memory, and a core needs both:
 *
 *   instruction window (IROM, 0x42000000..0x44000000): code is fetched from
 *       here through the instruction bus. It cannot be read as data, so
 *       strings and tables must not live here.
 *   data window (DROM, 0x3C000000..0x3E000000): readable by the CPU, so
 *       read-only data lives here.
 *
 * The loader maps the same flash pages twice - INST for the text, DATA for the
 * data region - which is exactly how the firmware itself is laid out
 * (.flash.text in IROM, .flash.rodata in DROM).
 *
 * The data region starts at a 64 KB boundary inside the partition (see AT()
 * below): that is what lets the loader map it on its own. Keep the two
 * addresses in sync with hello_core.c, which declares them in its entry table.
 *
 * Only code and read-only data live here: flash is read-only, so a core keeps
 * its writable state in the arena the host hands it through the ABI.
 *
 * Literals are kept next to their text: xtensa's l32r reaches only 256 KB, so
 * collecting every .literal at the top of a larger blob would break the longer
 * jumps.
 */
OUTPUT_FORMAT("elf32-xtensa-le")

core_text_addr = 0x43000000;
core_data_addr = 0x3DF00000;
/* Writable memory. Flash is read-only, so .data/.bss live in RAM the host
 * allocates and maps here (see arena_addr/arena_size in the entry table). Only
 * .bss is supported: initialised data would need a copy from the blob, so the
 * engine tree is built "dataless" (tools/dataless.py) and sets its initial
 * values from code. */
core_arena_addr = 0x3DC00000;
core_arena_size = 0x20000;

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
           "core .bss does not fit the arena: raise core_arena_size")

    /DISCARD/ :
    {
        *(.data .data.*)
        *(.comment)
        *(.xt.prop)
        *(.debug*)
    }
}
