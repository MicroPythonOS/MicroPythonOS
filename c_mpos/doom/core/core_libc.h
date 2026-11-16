// The core's C library, set up once from the ABI (see core_libc.c).
#ifndef MPOS_CORE_LIBC_H
#define MPOS_CORE_LIBC_H

#include "../../core_abi.h"

void mpos_libc_init(const mpos_core_abi_t *abi);
int mpos_libc_exit_requested(void);

#endif  // MPOS_CORE_LIBC_H
