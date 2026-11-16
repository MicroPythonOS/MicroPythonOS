/* Fixed-address layout for an mpos_core blob.
 *
 * A core is mapped into the instruction window (0x42000000..) by
 * esp_partition_mmap(ESP_PARTITION_MMAP_INST), so it must be linked for the
 * exact address it will appear at. 0x43000000 sits well inside that window and
 * clear of the app image (which starts at 0x42000020). Only code and rodata
 * live here: flash is read-only, so a core keeps its writable state in the
 * arena the host hands it through the ABI.
 *
 * Literals are kept next to their text: xtensa's l32r reaches only 256 KB, so
 * collecting every .literal at the top of a larger blob would break the longer
 * jumps.
 */
OUTPUT_FORMAT("elf32-xtensa-le")
ENTRY(core_init)

SECTIONS
{
    . = 0x43000000;

    .core_entry : ALIGN(4)
    {
        KEEP(*(.core_entry))
    }

    .text : ALIGN(4)
    {
        *(.literal .literal.* .text .text.*)
    }

    .rodata : ALIGN(4)
    {
        *(.rodata .rodata.*)
    }

    /DISCARD/ :
    {
        *(.data .data.*)
        *(.bss .bss.*)
        *(.comment)
        *(.xt.prop)
        *(.debug*)
    }
}
