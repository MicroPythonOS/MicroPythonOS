#!/usr/bin/env python3
"""Rewrite the Duke3D sources so they can be loaded as a MicroPython natmod.

A native module is linked with text, rodata and BSS only:

* no data section at all, and
* no static BSS variables (mpy_ld: "bss variables can't be static").

Duke keeps its state in those two places: file-scope ``static``
variables everywhere, and a few hundred initialized tables. This tool rewrites
a pristine upstream tree into a generated one at build time, so the vendored
sources stay untouched and the rewrite is reviewable in one place:

* ``static T x;`` -> ``T x;`` (global BSS; the linker reports name clashes)
* ``T x = init;`` -> ``static T const x_init = init;`` plus ``T x;`` and a
  ``memcpy`` in the file's init function, which is called once at module load.
* ``static T x = init;`` inside a function -> hoisted to file scope and renamed
  ``x__<function>``, with its uses in that function renamed to match.

Anything the transformer cannot parse safely is left alone and reported with
``WARN``; the build fails on those files rather than silently shipping a wrong
translation, so they can be handled explicitly.

Usage:
    dataless.py <src-dir> <out-dir>
"""

import os
import re
import sys

IDENT = re.compile(r"[A-Za-z_]\w*")
STORAGE = {"static", "extern", "typedef", "register", "auto", "inline"}

# Declarations the compiler never sees because they sit in `#if 0` or
# `#if ORIGCODE` dead code (ORIGCODE is not defined for doomgeneric). They must
# not be rewritten, or the init function references something that was compiled
# out. tools/checkcompile.sh fails when upstream grows another one.
INACTIVE = {
    # mmulti.c's UDP branch is `#elif UDP_NETWORKING`, and STUB_NETWORKING is
    # 1, so these are not compiled. The transformer does not evaluate the
    # preprocessor, and their initialiser copies would reference variables the
    # compiler never sees.
    "mmulti": {"udpsocket", "udpport", "udpmode"},
}


class Skipped(Exception):
    pass


class Source:
    def __init__(self, text):
        self.text = text
        self.stem = None  # non-.c belongs to no init function

    # -- scanners ---------------------------------------------------------

    def match_brace(self, start):
        """Index just past the brace block that opens at ``start``."""
        depth = 0
        i = start
        while i < len(self.text):
            c = self.text[i]
            if c in "\"'":
                i = self.skip_literal(i)
                continue
            if self.comment_at(i):
                i = self.skip_comment(i)
                continue
            if c == "{":
                depth += 1
            elif c == "}":
                depth -= 1
                if depth == 0:
                    return i + 1
            i += 1
        raise Skipped("unterminated brace block")

    def skip_literal(self, i):
        quote = self.text[i]
        i += 1
        while i < len(self.text):
            if self.text[i] == "\\":
                i += 2
                continue
            if self.text[i] == quote:
                return i + 1
            i += 1
        raise Skipped("unterminated literal")

    def comment_at(self, i):
        return self.text.startswith("/*", i) or self.text.startswith("//", i)

    def skip_comment(self, i):
        if self.text.startswith("//", i):
            end = self.text.find("\n", i)
            return len(self.text) if end < 0 else end
        end = self.text.find("*/", i + 2)
        if end < 0:
            raise Skipped("unterminated comment")
        return end + 2

    def find_statement_end(self, start):
        """Index of the ';' that ends a declaration starting at ``start``."""
        depth = 0
        i = start
        while i < len(self.text):
            c = self.text[i]
            if c in "\"'":
                i = self.skip_literal(i)
                continue
            if self.comment_at(i):
                i = self.skip_comment(i)
                continue
            if c in "([{":
                depth += 1
            elif c in ")]}":
                depth -= 1
            elif c == ";" and depth == 0:
                return i
            elif c == "}" and depth == 0:
                raise Skipped("declaration does not end with ';'")
            i += 1
        raise Skipped("missing ';'")


def split_top_level(text, separator=","):
    """Split on ``separator`` outside braces/parens/strings."""
    parts = []
    depth = 0
    start = 0
    i = 0
    while i < len(text):
        c = text[i]
        if c in "\"'":
            quote = c
            i += 1
            while i < len(text) and text[i] != quote:
                if text[i] == "\\":
                    i += 1
                i += 1
        elif text.startswith("/*", i):
            i = text.find("*/", i) + 1
        elif text.startswith("//", i):
            i = text.find("\n", i)
            if i < 0:
                i = len(text)
                continue
        elif c in "([{":
            depth += 1
        elif c in ")]}":
            depth -= 1
        elif c == separator and depth == 0:
            parts.append(text[start:i])
            start = i + 1
        i += 1
    parts.append(text[start:])
    return parts


def count_array_elements(init):
    """Number of top-level elements in a braced initializer."""
    body = init.strip()
    if not body.startswith("{"):
        raise Skipped("non-braced initializer with empty dimension")
    # Strip the outermost braces.
    depth = 0
    end = 0
    for i, c in enumerate(body):
        if c == "{":
            depth += 1
        elif c == "}":
            depth -= 1
            if depth == 0:
                end = i
                break
    inner = body[1:end]
    if not inner.strip():
        return 0
    # A trailing comma is not an element.
    parts = [part for part in split_top_level(inner) if part.strip()]
    return len(parts)


def parse_declaration(text):
    """Split ``[static] type declarator = init`` into its parts.

    Returns (specifiers, stars, name, dims, init) where dims is a string like
    ``[10][2]`` or ``[]`` and init is the text after '=' (or None).
    """
    body = text.strip()
    semi = body.rstrip().rstrip(";").rstrip()
    eq = 0
    depth = 0
    while eq < len(semi):
        c = semi[eq]
        if c in "\"'":
            raise Skipped("literal before '='")
        if c in "([{":
            depth += 1
        elif c in ")]}":
            depth -= 1
        elif c == "=" and depth == 0:
            break
        eq += 1
    if eq >= len(semi):
        lhs, init = semi, None
    else:
        lhs, init = semi[:eq], semi[eq + 1:]

    lhs = lhs.rstrip()
    # Declarator: optional stars, a name, and optional [..] dimensions.
    match = re.search(r"((?:\*\s*)*)([A-Za-z_]\w*)((?:\s*\[[^\]]*\])*)$", lhs)
    if match is None:
        raise Skipped("cannot find declarator")
    stars, name, dims = match.group(1), match.group(2), match.group(3)
    specifiers = lhs[:match.start()].strip()
    if not specifiers:
        raise Skipped("no type specifiers")
    tokens = specifiers.split()
    if any(t in ("typedef", "extern") for t in tokens):
        raise Skipped("typedef/extern")
    if "(" in specifiers:
        raise Skipped("function-like")
    return specifiers, stars.strip(), name, dims.replace(" ", ""), init


def parse_declarations(statement):
    """Parse a declaration, including `type a = 1, b = 2;` lists.

    Returns a list of (specifiers, stars, name, dims, init) tuples. Each element
    of a multi-declarator statement is emitted as its own declaration later, so
    the caller never has to deal with commas.
    """
    body = statement.strip().rstrip(";").rstrip()
    parts = split_top_level(body, ",")
    first = parse_declaration(parts[0])
    result = [first]
    for part in parts[1:]:
        # In C each declarator has its own stars: `char *a, b` makes only `a`
        # a pointer. Carrying the first declarator's stars over produced
        # `int32_t * *insptr` for `int32_t *scriptptr,*insptr;`.
        specifiers, _stars, _name, _dims, _init = first
        result.append(parse_declaration("%s %s" % (specifiers, part)))
    return result


def is_zero_initialiser(init):
    """A zero initialiser is what BSS already holds (and needs no copy)."""
    body = strip_leading_comments(init).strip()
    if body in ("0", "false", "NULL", '"\"\""', "'\\0'"):
        return True
    if body.startswith("{") and body.endswith("}"):
        inner = body[1:-1].strip()
        if not inner:
            return True
        return all(is_zero_initialiser(part) for part in split_top_level(inner))
    return False


def replace_identifier(text, name, replacement):
    """Replace a whole-word identifier, skipping literals and comments."""
    out = []
    i = 0
    n = len(text)
    pattern = re.compile(r"\b%s\b" % re.escape(name))
    while i < n:
        c = text[i]
        if c in "\"'":
            quote = c
            j = i + 1
            while j < n and text[j] != quote:
                if text[j] == "\\":
                    j += 1
                j += 1
            j = min(j + 1, n)
            out.append(text[i:j])
            i = j
            continue
        if text.startswith("/*", i):
            j = text.find("*/", i)
            j = n if j < 0 else j + 2
            out.append(text[i:j])
            i = j
            continue
        if text.startswith("//", i):
            j = text.find("\n", i)
            j = n if j < 0 else j
            out.append(text[i:j])
            i = j
            continue
        if text.startswith(("struct", "union", "enum"), i) and (
                i == 0 or not (text[i - 1].isalnum() or text[i - 1] == "_")):
            # Member names inside a struct/union/enum body are not variables:
            # leave the whole definition alone.
            brace = text.find("{", i)
            semi = text.find(";", i)
            if brace >= 0 and (semi < 0 or brace < semi):
                depth = 0
                j = brace
                while j < n:
                    if text[j] == "{":
                        depth += 1
                    elif text[j] == "}":
                        depth -= 1
                        if depth == 0:
                            j += 1
                            break
                    j += 1
                out.append(text[i:j])
                i = j
                continue
        match = pattern.match(text, i)
        boundary_ok = i == 0 or not (text[i - 1].isalnum() or text[i - 1] == "_")
        if match and boundary_ok and text[i - 1:i] not in (".", ">"):
            out.append(replacement)
            i = match.end()
            continue
        out.append(c)
        i += 1
    return "".join(out)


def strip_storage(specifiers):
    """Drop storage classes only: `const`/`volatile` belong to the type."""
    tokens = [t for t in specifiers.split()
              if t not in ("static", "extern", "register", "auto", "inline")]
    return " ".join(tokens)


def first_top_level(text, start, targets):
    """Positions of the first occurrence of each target char at depth zero.

    Parentheses, brackets and braces count as depth, so a target that is itself
    an opener (``(``, ``{``) is recorded before the depth changes.
    """
    found = {}
    depth = 0
    i = start
    while i < len(text):
        c = text[i]
        if c in "\"'":
            quote = c
            i += 1
            while i < len(text) and text[i] != quote:
                if text[i] == "\\":
                    i += 1
                i += 1
            i += 1
            continue
        if text.startswith("/*", i):
            i = text.find("*/", i) + 2
            continue
        if text.startswith("//", i):
            i = text.find("\n", i)
            if i < 0:
                return found
            continue
        if c in targets and depth == 0:
            if c not in found:
                found[c] = i
            if len(found) == len(targets):
                return found
        if c in "([{":
            depth += 1
        elif c in ")]}":
            depth -= 1
        i += 1
    return found


def find_statement_end_at(text, start):
    """Index of the ';' that ends the statement at ``start``, or -1.

    Braces, brackets and parentheses nest, so a `struct { ... }` body or an
    array initialiser does not end the declaration at its first ';'.
    """
    depth = 0
    i = start
    n = len(text)
    while i < n:
        c = text[i]
        if c in "\"'":
            quote = c
            i += 1
            while i < n:
                if text[i] == "\\":
                    i += 2
                    continue
                if text[i] == quote:
                    i += 1
                    break
                i += 1
            continue
        if text.startswith("/*", i):
            end = text.find("*/", i + 2)
            if end < 0:
                return -1
            i = end + 2
            continue
        if text.startswith("//", i):
            end = text.find("\n", i)
            if end < 0:
                return -1
            i = end + 1
            continue
        if c in "([{":
            depth += 1
        elif c in ")]}":
            depth -= 1
        elif c == ";" and depth == 0:
            return i
        i += 1
    return -1


def hoist_block_statics(body, function, inits, hoisted):
    """Move function-scope `static` variables to file scope.

    A natmod accepts no static BSS and no data section, so a `static` inside a
    function is as illegal as one at file scope. Each declaration is lifted out
    of the body and renamed `name__function`, and its uses in that body are
    renamed to match (the suffix makes the name unique to the function).
    Initialised ones get the same init-copy as file-scope data.
    """
    spans = []
    renames = []
    # Two block-scope statics with the same name (menues.c has one timer in
    # each of two switch cases) are hoisted to one variable. They live in
    # disjoint scopes, so sharing is exactly what the rename-every-use rule
    # already assumes; emitting the declaration twice is not.
    emitted = set()
    i = 0
    n = len(body)
    while i < n:
        c = body[i]
        if c in "\"'":
            quote = c
            i += 1
            while i < n and body[i] != quote:
                if body[i] == "\\":
                    i += 1
                i += 1
            i += 1
            continue
        if body.startswith("/*", i):
            i = body.find("*/", i) + 2
            continue
        if body.startswith("//", i):
            end = body.find("\n", i)
            if end < 0:
                break
            i = end
            continue
        previous = i - 1
        # A comment between the last statement and this declaration must not
        # hide the statement boundary (Duke's player.c puts `// FIX_00038`
        # right above three function statics). Walk back over whitespace and
        # whole comments until the real previous token.
        while previous >= 0:
            while previous >= 0 and body[previous] in " \t\r\n":
                previous -= 1
            if previous >= 1 and body[previous - 1:previous + 1] == "*/":
                start = body.rfind("/*", 0, previous - 1)
                if start < 0:
                    break
                previous = start - 1
                continue
            line_start = body.rfind("\n", 0, previous + 1) + 1
            comment = body.find("//", line_start, previous + 1)
            if comment >= 0:
                previous = comment - 1
                continue
            # A preprocessor directive between two statements is not a token:
            # `#ifdef MPOS_CORE` sits right above loadtmb's 8 KB static buffer.
            if body[line_start:previous + 1].lstrip().startswith("#"):
                previous = line_start - 1
                continue
            break
        at_statement_start = previous < 0 or body[previous] in "{};"
        if body.startswith("static", i) and at_statement_start:
            # The declaration can contain braces and parentheses (`static
            # const struct { ... } table[] = { ... };`), so the first ';' is
            # not the end of the statement.
            semi = find_statement_end_at(body, i)
            if semi < 0:
                raise Skipped("static without ';'")
            statement = body[i:semi + 1]
            i = semi + 1
            try:
                declarations = parse_declarations(statement)
            except Skipped:
                continue
            replaced = []
            for specifiers, stars, name, dims, init in declarations:
                if "const" in specifiers.split():
                    replaced.append(None)
                    continue
                lifted = "%s__%s" % (name, function)
                base = strip_storage(specifiers)
                star_text = (stars + " ") if stars else ""
                if lifted in emitted:
                    renames.append((name, lifted))
                    continue
                emitted.add(lifted)
                if init is None or is_zero_initialiser(init):
                    hoisted.append("%s %s%s%s;" % (base, star_text, lifted, dims))
                else:
                    dims = resolve_empty_dims(dims, init)
                    hoisted.append("static %s %sconst %s_init%s = %s;"
                                   % (base, star_text, lifted, dims, init.strip()))
                    hoisted.append("%s %s%s%s;" % (base, star_text, lifted, dims))
                    inits.append(lifted)
                renames.append((name, lifted))
            spans.append((i - len(statement), semi + 1))
            continue
        i += 1

    if not spans:
        return body
    # The hoisted declarations can mention each other (sdl_video's mode list is
    # an array of pointers into the rows next to it), so rename them too - not
    # only the function body they came out of.
    for index, line in enumerate(hoisted):
        for name, lifted in renames:
            line = re.sub(r"(?<!\.)(?<!\->)\b%s\b" % re.escape(name), lifted,
                          line)
        hoisted[index] = line
    result = []
    cursor = 0
    for begin, end in spans:
        result.append(body[cursor:begin])
        cursor = end
    result.append(body[cursor:])
    renamed = "".join(result)
    for name, lifted in renames:
        # A member access (`s.x`, `p->x`) keeps its name: only the identifier
        # standing on its own refers to the variable being hoisted.
        renamed = re.sub(r"(?<!\.)(?<!\->)\b%s\b" % re.escape(name), lifted, renamed)
    return renamed


def transform_file(path, out_path, stem, text=None):
    if text is None:
        text = open(path, errors="replace").read()
    src = Source(text)
    src.stem = stem
    text = src.text
    out = []
    cursor = 0
    inits = []
    renames = []
    conditional = 0
    i = 0
    n = len(text)
    while i < n:
        c = text[i]
        if c in "\"'":
            i = src.skip_literal(i)
            continue
        if src.comment_at(i):
            i = src.skip_comment(i)
            continue
        if c == "#":
            line_end = text.find("\n", i)
            if line_end < 0:
                line_end = n
            # Follow backslash continuations: a multi-line macro body is not
            # code and must not be parsed as a declaration.
            while line_end > 0 and text[line_end - 1] == "\\":
                following = text.find("\n", line_end + 1)
                if following < 0:
                    line_end = n
                    break
                line_end = following
            directive = text[i + 1:line_end].strip()
            word = directive.split()[0] if directive.split() else ""
            if word in ("if", "ifdef", "ifndef"):
                conditional += 1
            elif word == "endif":
                conditional -= 1
            i = line_end
            continue
        if c == "{":
            i = src.match_brace(i)
            continue
        if c == ";":
            i += 1
            continue
        if c in " \t\r\n}":
            i += 1
            continue

        start = i
        positions = first_top_level(text, start, ";(={")
        paren = positions.get("(")
        semi = positions.get(";")
        brace = positions.get("{")
        equals = positions.get("=")

        # A function *definition* is `name(...) {`. A function-pointer
        # declaration is `void (*p)(void) = NULL;`: the first '(' belongs to
        # the declarator, and there is no body brace before the ';'.
        is_function = (paren is not None and brace is not None
                       and paren < brace
                       and (semi is None or brace < semi))
        if is_function:
            if brace is not None and (semi is None or brace < semi):
                end = src.match_brace(brace)
                # Hoist block-scope statics of this function.
                name_match = None
                for name_match in re.finditer(r"([A-Za-z_]\w*)\s*\($",
                                              text[max(0, paren - 64):paren + 1]):
                    pass
                function = "fn"
                if name_match is not None:
                    function = name_match.group(1)
                hoisted = []
                body = text[brace:end]
                new_body = hoist_block_statics(body, function, inits, hoisted)
                if hoisted:
                    out.append(text[cursor:start])
                    out.append("\n/* dataless.py: hoisted from %s */\n" % function)
                    out.append("\n".join(hoisted) + "\n")
                    out.append(text[start:brace])
                    out.append(new_body)
                    cursor = end
                i = end
            else:
                i = (semi + 1) if semi is not None else n
            continue

        try:
            end = src.find_statement_end(start)
        except Skipped as exc:
            return None, ["%s: %s: %r" % (
                os.path.basename(path), exc, text[start:start + 60])]

        statement = text[start:end + 1]
        replacement = statement
        try:
            declarations = parse_declarations(statement)
        except Skipped:
            declarations = None

        if declarations is None:
            # A function-pointer declaration has no declarator at the end of
            # the text (`static void (*p)(void) = NULL;`), so the declarator
            # regex in parse_declaration refuses it. It is a plain BSS object
            # with a zero initialiser; drop the `static` and the NULL.
            pointer = re.search(r"\(\s*\*\s*([A-Za-z_]\w*)\s*\)", statement)
            is_static = re.search(r"^\s*static\b", statement) is not None
            zero = re.search(r"=\s*(0|NULL|false)\s*;\s*$", statement) is not None
            if pointer is not None and is_static and zero and not conditional:
                name = pointer.group(1)
                public = "%s__%s" % (name, stem)
                replacement = re.sub(r"^\s*static\s+", "", statement, count=1)
                replacement = re.sub(r"=\s*(0|NULL|false)\s*;", ";",
                                     replacement)
                renames.append((name, public))

        if declarations is not None:
            pieces = []
            for specifiers, stars, name, dims, init in declarations:
                is_static = "static" in specifiers.split()
                base = strip_storage(specifiers)
                star_text = (stars + " ") if stars else ""
                public = name
                if is_static and not conditional:
                    # A file-local variable becomes a global, so its name has to
                    # be unique across the module: suffix it with the file.
                    public = "%s__%s" % (name, stem)
                    renames.append((name, public))
                # Const data is rodata, which the linker takes as-is: only
                # mutable data has to move to BSS. (`const char *x[]` also
                # lands in .data.rel.ro because of its relocations, and that
                # is accepted too.)
                # `const T *p` is a *writable* pointer to const data, so only a
                # const object (no declarator stars) can stay in rodata.
                object_is_const = "const" in specifiers.split() and not stars
                if object_is_const or name in INACTIVE.get(stem, ()):
                    pieces.append("%s %s%s%s%s;" % (
                        specifiers, star_text, name, dims,
                        (" = " + init.strip()) if init else ""))
                elif init is None or is_zero_initialiser(init):
                    pieces.append("%s %s%s%s;" % (base, star_text, public, dims))
                else:
                    try:
                        dims = resolve_empty_dims(dims, init)
                    except Skipped as exc:
                        return None, ["%s: %s: %r" % (
                            os.path.basename(path), exc, statement.strip()[:70])]
                    pieces.append("static %s %sconst %s_init%s = %s;\n%s %s%s%s;"
                                  % (base, star_text, public, dims, init.strip(),
                                     base, star_text, public, dims))
                    inits.append(public)
            replacement = "\n".join(pieces)

        out.append(text[cursor:start])
        out.append(replacement)
        cursor = end + 1
        i = end + 1

    out.append(text[cursor:])
    result = "".join(out)
    # Rename the globalised statics everywhere in the file: they were file-local
    # before, so every use is in here.
    for name, public in renames:
        result = replace_identifier(result, name, public)
    if inits:
        result += (
            "\n/* dataless.py: initialised data copied into BSS at module load */\n"
            "#include <string.h>\n"
            "void duke_init_data_%s(void) {\n" % stem)
        for name in inits:
            result += "    memcpy(&%s, &%s_init, sizeof(%s));\n" % (name, name, name)
        result += "}\n"
    os.makedirs(os.path.dirname(out_path), exist_ok=True)
    with open(out_path, "w") as handle:
        handle.write(result)
    return inits, []


def write_registry(out_dir, stems):
    """One function that runs every file's init-copy, called once at load."""
    header = os.path.join(out_dir, "duke_data_init.h")
    source = os.path.join(out_dir, "duke_data_init.c")
    with open(header, "w") as handle:
        handle.write(
            "// Generated by dataless.py: run every file's initialised-data copy.\n"
            "#ifndef DUKE_DATA_INIT_H\n#define DUKE_DATA_INIT_H\n"
            "void duke_init_all_data(void);\n#endif\n")
    with open(source, "w") as handle:
        handle.write("// Generated by dataless.py.\n")
        for stem in stems:
            handle.write("void duke_init_data_%s(void);\n" % stem)
        handle.write("void duke_init_all_data(void) {\n")
        for stem in stems:
            handle.write("    duke_init_data_%s();\n" % stem)
        handle.write("}\n")


def literal_length(text):
    """Number of bytes in a C string literal initialiser, including the NUL."""
    body = text.strip()
    body = strip_leading_comments(body)
    if not (body.startswith('"') and body.endswith('"')):
        raise Skipped("cannot size an empty dimension from this initialiser")
    total = 0
    i = 1
    while i < len(body) - 1:
        if body[i] == "\\":
            if body[i + 1] in "01234567":
                i += 4
            elif body[i + 1] == "x":
                j = i + 2
                while j < len(body) and body[j] in "0123456789abcdefABCDEF":
                    j += 1
                i = j
            else:
                i += 2
            total += 1
            continue
        total += 1
        i += 1
    return total + 1


def strip_leading_comments(text):
    body = text.lstrip()
    while True:
        if body.startswith("/*"):
            end = body.find("*/")
            if end < 0:
                raise Skipped("unterminated comment in initialiser")
            body = body[end + 2:].lstrip()
        elif body.startswith("//"):
            end = body.find("\n")
            if end < 0:
                raise Skipped("comment-only initialiser")
            body = body[end + 1:].lstrip()
        else:
            return body


def resolve_empty_dims(dims, init):
    if "[]" not in dims:
        return dims
    init = strip_leading_comments(init)
    if init.startswith("{"):
        count = count_array_elements(init)
    else:
        count = literal_length(init)
    return dims.replace("[]", "[%d]" % count, 1)


def main():
    src_dir = sys.argv[1]
    out_dir = sys.argv[2]
    # Optional: only these stems are compiled, so only they belong in the
    # registry (the tree also holds platform ports we do not build).
    only = set(sys.argv[3:])
    problems = []
    names = []
    total_inits = 0
    inited = []
    for name in sorted(os.listdir(src_dir)):
        if not name.endswith(".c"):
            continue
        path = os.path.join(src_dir, name)
        stem = os.path.splitext(name)[0]
        inits, errors = transform_file(path, os.path.join(out_dir, name), stem)
        if errors:
            problems.extend(errors)
            continue
        total_inits += len(inits)
        names.append(stem)
        if inits and (not only or stem in only):
            inited.append(stem)
    write_registry(out_dir, inited)
    print("GENERATED %d files, %d initialisers in %d files" % (
        len(names), total_inits, len(inited)))
    if problems:
        print("PROBLEMS (%d):" % len(problems))
        for problem in problems:
            print("  ", problem)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
