MOD_DIR := $(USERMOD_DIR)

ifneq (,$(findstring -Wno-missing-field-initializers, $(CFLAGS_USERMOD)))
    CFLAGS_USERMOD += -Wno-missing-field-initializers
endif

# Check which system this build is being performed on
UNAME_S := $(shell uname -s)
ifneq ($(UNAME_S),Darwin)
    # Non-macOS settings (e.g., Linux)
    LDFLAGS += -lv4l2
    SRC_USERMOD_C += $(MOD_DIR)/src/hello_world.c
    SRC_USERMOD_C += $(MOD_DIR)/src/webcam.c
endif

SRC_USERMOD_C += $(MOD_DIR)/src/quirc_decode.c

SRC_USERMOD_C += $(MOD_DIR)/quirc/lib/identify.c
SRC_USERMOD_C += $(MOD_DIR)/quirc/lib/version_db.c
SRC_USERMOD_C += $(MOD_DIR)/quirc/lib/decode.c
SRC_USERMOD_C += $(MOD_DIR)/quirc/lib/quirc.c

CFLAGS+= -I/usr/include

