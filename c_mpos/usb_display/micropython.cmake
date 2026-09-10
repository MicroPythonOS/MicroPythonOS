# MicroPython USER_C_MODULE for USB display adapters (Pico_USB_Disp, MIT).
# ESP32-only PoC: DisplayLink DL-1xx via the in-tree IDF usb_host stack.
#
# Pass as:
#   USER_C_MODULE=<repo>/c_mpos/usb_display/micropython.cmake
# ...to make.py when building for esp32. Requires CFLAGS_EXTRA to contain
# -DMICROPY_HW_ENABLE_USBDEV=0 so the OTG peripheral is free for USB Host
# (TinyUSB device mode would otherwise own it).

add_library(usermod_c_usb_disp INTERFACE)

set(C_USB_DISP_UPSTREAM ${CMAKE_CURRENT_LIST_DIR}/upstream)

set(C_USB_DISP_SOURCES
    ${C_USB_DISP_UPSTREAM}/usb_disp.cpp
    ${C_USB_DISP_UPSTREAM}/usb_disp_prot_dl-1xx.cpp
    ${C_USB_DISP_UPSTREAM}/usb_disp_hal_esp32.cpp
    ${CMAKE_CURRENT_LIST_DIR}/src/usb_disp_mpy.c
)

# T6/MS91xx need USB High-Speed (ESP32-P4 only); on S2/S3 they compile to
# empty stubs, so leave them out entirely to save flash.
if(IDF_TARGET STREQUAL "esp32p4")
    list(APPEND C_USB_DISP_SOURCES
        ${C_USB_DISP_UPSTREAM}/usb_disp_prot_t6.cpp
        ${C_USB_DISP_UPSTREAM}/usb_disp_prot_ms91xx.cpp
    )
endif()

target_sources(usermod_c_usb_disp INTERFACE ${C_USB_DISP_SOURCES})

# Optimize the vendored sources for size: the esp32 port compiles usermod
# sources into the top-level micropython.elf with -O2, and the DL protocol
# code is not timing-critical (USB Full-Speed is the bottleneck).
# set_source_files_properties applies wherever the sources get compiled.
set_source_files_properties(${C_USB_DISP_SOURCES} PROPERTIES COMPILE_OPTIONS -Os)

# ESP_PLATFORM is required by upstream's usb_disp.h platform detection.
# It must be an INTERFACE definition (not just CFLAGS_EXTRA) because the
# esp32 port also compiles usermod sources into the top-level micropython.elf
# target, which does not inherit MICROPY_CPP_FLAGS/CFLAGS_EXTRA — but it does
# inherit INTERFACE properties through the usermod -> main -> elf link chain.
target_compile_definitions(usermod_c_usb_disp INTERFACE ESP_PLATFORM)

target_include_directories(usermod_c_usb_disp INTERFACE
    ${C_USB_DISP_UPSTREAM}
    ${CMAKE_CURRENT_LIST_DIR}/src
)

# Propagate the in-tree IDF `usb` (usb_host) and `esp_timer` component
# include dirs, lcd_bus-style. NOTE: do NOT target_link_libraries() the
# idf::<comp> aliases here: usermod.cmake recurses INTERFACE_LINK_LIBRARIES
# into MICROPY_INC_USERMOD, which drags every transitive IDF include dir
# (including relative ones like esp_hw_support's) into main's
# idf_component_register and breaks configure. All component libs link into
# the final app image anyway, so symbols resolve at final link.
foreach(_comp usb esp_timer)
    idf_component_get_property(_comp_includes ${_comp} INCLUDE_DIRS)
    idf_component_get_property(_comp_dir ${_comp} COMPONENT_DIR)
    set(_comp_abs_includes "")
    foreach(_inc ${_comp_includes})
        if(IS_ABSOLUTE ${_inc})
            list(APPEND _comp_abs_includes ${_inc})
        else()
            list(APPEND _comp_abs_includes ${_comp_dir}/${_inc})
        endif()
    endforeach()
    target_include_directories(usermod_c_usb_disp INTERFACE ${_comp_abs_includes})
endforeach()

target_link_libraries(usermod INTERFACE usermod_c_usb_disp)
