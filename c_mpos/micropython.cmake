# This must be passed as:
# USER_C_MODULE=/path/to/c_mpos/micropython.cmake
# ...to make.py when building for esp32 to ensure it gets compiled.

add_library(usermod_c_mpos INTERFACE)

set(MPOS_C_INCLUDES)

set(MPOS_C_INCLUDES
    ${CMAKE_CURRENT_LIST_DIR}/../lvgl_micropython/lib/micropython/ports/esp32/managed_components/espressif__esp_codec_dev/include/
    ${CMAKE_CURRENT_LIST_DIR}/../lvgl_micropython/lib/micropython/ports/esp32/managed_components/espressif__esp_codec_dev/interface/
)

set(MPOS_C_SOURCES
    ${CMAKE_CURRENT_LIST_DIR}/src/adc_mic.c
    ${CMAKE_CURRENT_LIST_DIR}/src/quirc_decode.c
    ${CMAKE_CURRENT_LIST_DIR}/quirc/lib/identify.c
    ${CMAKE_CURRENT_LIST_DIR}/quirc/lib/version_db.c
    ${CMAKE_CURRENT_LIST_DIR}/quirc/lib/decode.c
    ${CMAKE_CURRENT_LIST_DIR}/quirc/lib/quirc.c
#    ${CMAKE_CURRENT_LIST_DIR}/src/font_Noto_Sans_sat_emojis_compressed.c
)

# Add our source files to the lib
target_sources(usermod_c_mpos INTERFACE ${MPOS_C_SOURCES})

# Add include directories.
target_include_directories(usermod_c_mpos INTERFACE ${MPOS_C_INCLUDES})


target_compile_definitions(usermod_c_mpos INTERFACE
    # force quirc to use single precision floating point math
    -DQUIRC_FLOAT_TYPE=float
    -DQUIRC_USE_TGMATH=1
)

# Be sure to set the -O2 "optimize" flag!!
target_compile_options(usermod_c_mpos INTERFACE
    -O2
)

# Link our INTERFACE library to the usermod target.
target_link_libraries(usermod INTERFACE usermod_c_mpos)

