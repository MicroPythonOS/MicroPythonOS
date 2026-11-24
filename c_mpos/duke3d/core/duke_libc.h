#ifndef MPOS_DUKE_LIBC_H
#define MPOS_DUKE_LIBC_H

#include <stddef.h>
#include "../../core_abi.h"

void mpos_libc_init(const mpos_core_abi_t *abi);
int mpos_libc_exit_requested(void);
void mpos_fatal_jump(void);

void mpos_heap_init(void *base, size_t size);
size_t mpos_heap_free(void);
size_t mpos_heap_largest(void);

#endif
