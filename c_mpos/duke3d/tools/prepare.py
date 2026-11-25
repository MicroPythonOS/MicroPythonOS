#!/usr/bin/env python3
"""Generate the dataless Duke3D tree the native module is built from.

A MicroPython native module is linked with text, rodata and BSS only: it has no
data section and it may not contain static BSS. Duke's engine (and the platform
shims in core/) use both, so tools/dataless.py rewrites copies of those sources
into gen/ and this script wires the per-file initialised-data copies into one
``duke_init_all_data()`` the module calls once before the engine boots.

The generated tree mirrors the original depth so the sources' relative includes
keep working:

    engine/Game/x.c  -> gen/Game/x.c
    engine/Engine/x.c -> gen/Engine/x.c
    core/x.c          -> gen/x.c

The flash-resident core build keeps compiling the pristine sources; it has a
real .data/.bss arena and needs no rewrite.
"""

import os
import shutil
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import dataless

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

# The core shims. duke_core.c is only for the flash-resident core (it owns the
# entry table and the fixed-address layout); the native module has natmod.c.
CORE_SOURCES = (
    "duke_audio.c",
    "duke_libc.c",
    "duke_platform.c",
    "lodepng.c",
    "sdl_event.c",
    "sdl_input.c",
    "sdl_system.c",
    "sdl_video.c",
)

# Engine sources, matching build_duke_core.sh: the stub networking file is the
# one that is not built (mmulti.c/network.c are the pair the core keeps).
SKIP = {
    "Engine/dummy_multi.c",
}

# Headers that define initialised data instead of just declaring it. They are
# included by one .c file each, so the generated copy can carry the init-copy
# function the registry calls. config.c includes _functio.h, which is where
# gamefunctions[] and keydefaults[] (arrays of string pointers) live.
HEADERS = (
    ("engine/Game/_functio.h", "gen/Game/_functio.h"),
)


def strip_cpp_block(text, marker="#ifdef LODEPNG_COMPILE_CPP"):
    """Remove `marker` ... its matching `#endif` (dead C++ code)."""
    lines = text.splitlines(True)
    out = []
    depth = 0
    skipping = False
    for line in lines:
        stripped = line.lstrip()
        if depth == 0 and stripped.startswith(marker):
            skipping = True
            depth = 1
            continue
        if skipping:
            if stripped.startswith(("#if", "#ifdef", "#ifndef")):
                depth += 1
            elif stripped.startswith("#endif"):
                depth -= 1
                if depth == 0:
                    skipping = False
            continue
        out.append(line)
    return "".join(out)


def sources():
    for directory, out in (("engine/Game", "Game"), ("engine/Engine", "Engine")):
        path = os.path.join(ROOT, directory)
        for name in sorted(os.listdir(path)):
            if not name.endswith(".c"):
                continue
            if "%s/%s" % (out, name) in SKIP:
                continue
            yield os.path.join(path, name), os.path.join("gen", out, name)
    for name in CORE_SOURCES:
        yield os.path.join(ROOT, "core", name), os.path.join("gen", name)


def main():
    gen = os.path.join(ROOT, "gen")
    for name in sorted(os.listdir(gen)) if os.path.isdir(gen) else ():
        path = os.path.join(gen, name)
        if os.path.isdir(path):
            for child in os.listdir(path):
                os.remove(os.path.join(path, child))
            os.rmdir(path)
        else:
            os.remove(path)
    problems = []
    inited = []
    total = 0
    for source, output in sources():
        stem = os.path.splitext(os.path.basename(output))[0]
        text = None
        if stem == "lodepng":
            # lodepng keeps a C++ wrapper under `LODEPNG_COMPILE_CPP`. It is
            # dead code in C, but the transformer's C parser cannot read the
            # namespace block, so drop that conditional first. The file also
            # has a relocated version-string pointer that has to move to BSS
            # like every other initialised object.
            text = strip_cpp_block(open(source, errors="replace").read())
        inits, errors = dataless.transform_file(
            source, os.path.join(ROOT, output), stem, text=text)
        if errors:
            problems.extend(errors)
            continue
        if stem == "network":
            # network.c is the stub dispatcher with USER_DUMMY_NETWORK. Its
            # Setup_* and callcommit collide with duke_platform.c and mmulti.c
            # (the core link allows multiple definitions; mpy_ld does not).
            path = os.path.join(ROOT, output)
            text = open(path).read()
            text = text.replace("void Setup_UnstableNetworking()",
                                "void network_unused_setup_unstable()")
            text = text.replace("void Setup_StableNetworking()",
                                "void network_unused_setup_stable()")
            text = text.replace("void callcommit(void)",
                                "void network_unused_callcommit(void)")
            open(path, "w").write(text)
        total += 1
        if inits:
            inited.append(stem)
    # mpos_printf.c is shared with Doom. Keep a copy under gen/ so the build
    # object stays inside build_x64/ instead of next to ../doom.
    shutil.copyfile(os.path.join(ROOT, "..", "doom", "mpos_printf.c"),
                    os.path.join(gen, "mpos_printf.c"))
    total += 1

    for source, output in HEADERS:
        stem = os.path.splitext(os.path.basename(output))[0]
        path = os.path.join(ROOT, source)
        # `extern "C" {` would make the transformer skip everything inside as
        # a function body; the block is C++-only anyway.
        text = strip_cpp_block(open(path, errors="replace").read(),
                               "#ifdef __cplusplus")
        inits, errors = dataless.transform_file(
            path, os.path.join(ROOT, output), stem, text=text)
        if errors:
            problems.extend(errors)
            continue
        total += 1
        if inits:
            inited.append(stem)
    dataless.write_registry(gen, inited)
    print("GENERATED %d files, %d with initialised data" % (total, len(inited)))
    if problems:
        print("PROBLEMS (%d):" % len(problems))
        for problem in problems:
            print("  ", problem)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
