#!/usr/bin/env python3
"""Analyze ESP32 micropython.elf/.map size and emit drill-down reports.

Reads the linker map, ELF symbols, frozen .mpy tree, sdkconfig and bin
sizes, then writes a terminal report, CSVs, a drill-down JSON tree and a
self-contained HTML treemap into tmp/size-reports/.

Usage:
    python3 scripts/size_analyze.py --build-dir <build> --out-dir <out> --label <name>
"""

import argparse
import csv
import json
import os
import re
import subprocess
import sys


REPO = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))

FLASH_SECTIONS = {
    ".flash.text",
    ".flash.rodata",
    ".flash.appdesc",
    ".iram0.text",
    ".iram0.vectors",
    ".dram0.data",
    ".rtc.text",
}

RAM_ONLY_SECTIONS = {
    ".dram0.bss",
    ".dram0.heap_start",
    ".noinit",
    ".rtc_noinit",
    ".rtc.bss",
}

ALLOC_FLASH_SECTIONS = {
    ".flash.text",
    ".flash.rodata",
    ".flash.appdesc",
    ".iram0.text",
    ".iram0.vectors",
    ".dram0.data",
    ".rtc.text",
    ".rtc.force_fast",
}

ALLOC_RAM_SECTIONS = {
    ".dram0.data",
    ".dram0.bss",
    ".iram0.bss",
    ".iram0.data",
    ".noinit",
    ".rtc_noinit",
    ".rtc.force_slow",
    ".rtc_reserved",
    ".dram0.heap_start",
}

CONTRIB_RE = re.compile(
    r"^\s+\.([A-Za-z][A-Za-z0-9_]*)"
    r"(?:\.\S+)?"
    r"\s+(0x[0-9a-fA-F]+)\s+(0x[0-9a-fA-F]+)\s+(\S.*\S)\s*$"
)

KNOWN_INPUT_BASES = {
    "text",
    "literal",
    "rodata",
    "srodata",
    "sdata2",
    "data",
    "sdata",
    "bss",
    "common",
    "rodata_desc",
}

RELAX_RE = re.compile(r"^\s+(0x[0-9a-fA-F]+)\s+\(size before relaxing\)\s*$")

SECTION_HDR_RE = re.compile(r"^(\.\S+)\s+(0x[0-9a-fA-F]+)\s+(0x[0-9a-fA-F]+)\s*$")

OUTPUT_HDR_ONLY_RE = re.compile(r"^(\.\S+)\s*$")

ADDR_SIZE_ONLY_RE = re.compile(r"^\s+(0x[0-9a-fA-F]+)\s+(0x[0-9a-fA-F]+)\s*$")

SECTION_ONLY_RE = re.compile(r"^\s+\.(\S+)\s*$")

ADDR_SIZE_SRC_RE = re.compile(
    r"^\s+(0x[0-9a-fA-F]+)\s+(0x[0-9a-fA-F]+)\s+(\S.*\S)\s*$"
)

FILL_RE = re.compile(r"^\s+\*fill\*\s+(0x[0-9a-fA-F]+)\s+(0x[0-9a-fA-F]+)\s*$")

INPUT_SECTIONS = {
    "text",
    "literal",
    "rodata",
    "srodata",
    "sdata2",
    "data",
    "sdata",
    "bss",
    "common",
    "rodata_desc",
}


def input_base(name):
    base = name.split(".")[0]
    if base in KNOWN_INPUT_BASES:
        return base
    if base.startswith("iram") or base.startswith("sram"):
        return "text"
    if base.startswith("dram"):
        return "data"
    if base.startswith("rtc"):
        return "data"
    if base.startswith("wif") and base.endswith("iram"):
        return "text"
    if base in ("coexiram",):
        return "text"
    return ""

ARCHIVE_RE = re.compile(r"^(.*?\.a)\(([^)]+)\)\s*$")

CMAKE_PREFIX = "CMakeFiles/micropython.elf.dir/"

SIZE_OPTS = [
    "CONFIG_COMPILER_OPTIMIZATION_SIZE",
    "CONFIG_COMPILER_OPTIMIZATION_PERF",
    "CONFIG_COMPILER_OPTIMIZATION_ASSERTIONS_DISABLE",
    "CONFIG_BOOTLOADER_LOG_LEVEL",
    "CONFIG_LOG_DEFAULT_LEVEL",
    "CONFIG_LOG_COLORS",
    "CONFIG_BT_ENABLED",
    "CONFIG_BT_NIMBLE_ENABLED",
    "CONFIG_BT_BLUEDROID_ENABLED",
    "CONFIG_BT_CONTROLLER_ENABLED",
    "CONFIG_WIFI_ENABLED",
    "CONFIG_ESP_WIFI_",
    "CONFIG_MBEDTLS_",
    "CONFIG_LWIP_",
    "CONFIG_FATFS_",
    "CONFIG_VFS_",
    "CONFIG_FREERTOS_",
    "CONFIG_ESPTOOLPY_FLASHSIZE",
    "CONFIG_PARTITION_TABLE_CUSTOM_FILENAME",
    "CONFIG_SPIRAM_",
    "CONFIG_TINYUSB",
    "CONFIG_USB_HOST_",
]


def find_tool(name):
    candidates = [
        os.path.join(
            os.path.expanduser("~"),
            ".espressif/tools/xtensa-esp-elf/esp-14.2.0_20241119/"
            "xtensa-esp-elf/bin",
            name,
        ),
    ]
    path_dirs = os.environ.get("PATH", "").split(os.pathsep)
    for d in path_dirs:
        candidates.append(os.path.join(d, name))
    for c in candidates:
        if c and os.path.isfile(c) and os.access(c, os.X_OK):
            return c
    return name


def parse_partitions_size(build_dir):
    for name in ("partitions.csv",):
        for root, _dirs, files in os.walk(build_dir):
            if name in files:
                p = os.path.join(root, name)
                try:
                    with open(p) as f:
                        for line in f:
                            line = line.strip()
                            if line.startswith("ota_0,"):
                                parts = [x.strip() for x in line.split(",")]
                                if len(parts) >= 5:
                                    return int(parts[4], 16), p
                except (OSError, ValueError):
                    pass
    csv_path = os.path.join(REPO, "lvgl_micropython/build/partitions.csv")
    try:
        with open(csv_path) as f:
            for line in f:
                line = line.strip()
                if line.startswith("ota_0,"):
                    parts = [x.strip() for x in line.split(",")]
                    if len(parts) >= 5:
                        return int(parts[4], 16), csv_path
    except OSError:
        pass
    return 3670016, "default(0x380000)"


def index_main_objects(build_dir):
    index = {}
    main_dir = os.path.join(build_dir, "esp-idf", "main")
    for root, _dirs, files in os.walk(main_dir):
        for fn in files:
            if fn.endswith(".obj"):
                full = os.path.join(root, fn)
                index.setdefault(fn, full)
    return index


def classify(source, main_index):
    s = source.strip()
    if s.startswith("*fill*"):
        return ("padding", "alignment-fill")
    if s.startswith("*merged-strings*"):
        return ("string-merge-pool", "merged-rodata-strings")
    m = ARCHIVE_RE.match(s)
    if m:
        archive, member = m.group(1), m.group(2)
        if "/main/libmain.a" in archive or archive.endswith("main/libmain.a"):
            if member == "frozen_content.c.obj":
                return ("frozen-python", "frozen_content.c")
            full = main_index.get(member, "")
            if "/lib/micropython/py/" in full:
                return ("micropython-core", member)
            if "/lib/micropython/extmod/" in full:
                return ("micropython-extmod", member)
            if "/ports/esp32/" in full or "/ports/" in full:
                return ("micropython-port", member)
            if "/drivers/" in full:
                return ("micropython-drivers", member)
            if "/lib/" in full and ("mbedtls" in full or "littlefs" in full or "fatfs" in full):
                return ("micropython-lib", member)
            return ("micropython-other", member)
        if archive.startswith("esp-idf/"):
            comp = archive.split("/")[1] if "/" in archive else archive
            return ("esp-idf:" + comp, member)
        if "libnet80211.a" in archive or "libpp.a" in archive or "libmesh.a" in archive:
            return ("esp-idf:esp_wifi-blob", os.path.basename(archive) + ":" + member)
        if "libbtdm_app.a" in archive or "libcoexist.a" in archive:
            return ("esp-idf:bt-blob", os.path.basename(archive) + ":" + member)
        if "libphy.a" in archive:
            return ("esp-idf:phy-blob", member)
        return ("other-archive", os.path.basename(archive) + ":" + member)
    if s.startswith(CMAKE_PREFIX):
        rel = s[len(CMAKE_PREFIX):]
        if "/lib/lvgl/" in rel:
            parts = rel.split("/lib/lvgl/src/")
            sub = parts[1].split("/")[0] if len(parts) > 1 else "other"
            return ("lvgl:" + sub, rel.split("/")[-1])
        if rel.endswith("lv_mp.c.obj"):
            return ("lvgl-bindings", "lv_mp.c")
        if "/c_mpos/usb_display/" in rel:
            return ("usermod:usb-display", rel.split("/")[-1])
        if "/c_mpos/quirc/" in rel:
            return ("usermod:quirc", rel.split("/")[-1])
        if "/c_mpos/" in rel:
            return ("usermod:c_mpos", rel.split("/")[-1])
        if "secp256k1" in rel:
            return ("usermod:secp256k1", rel.split("/")[-1])
        if "micropython-camera-API" in rel or "esp32-camera" in rel:
            return ("usermod:camera", rel.split("/")[-1])
        if "esp32-component-rvswd" in rel:
            return ("usermod:rvswd", rel.split("/")[-1])
        if "/ext_mod/" in rel:
            parts = rel.split("/ext_mod/")
            sub = parts[1].split("/")[0] if len(parts) > 1 else "other"
            return ("drivers:" + sub, rel.split("/")[-1])
        if "adc_mic" in rel or "espressif__" in rel:
            return ("usermod:adc_mic", rel.split("/")[-1])
        return ("other-direct", rel.split("/")[-1])
    if s.startswith("esp-idf/"):
        comp = s.split("/")[1] if "/" in s else s
        return ("esp-idf:" + comp, s.split("/")[-1])
    return ("other", s.split("/")[-1][:60])


def parse_map(map_path, main_index):
    per_object = {}
    per_bucket_flash = {}
    per_bucket_ram = {}
    per_bucket_detail = {}
    total_flash_mapped = 0
    total_bss = 0
    in_map = False
    current_section = ""
    pending_input = ""
    pending_output_hdr = ""
    in_output_section = False

    def record(source, size, ibase):
        nonlocal total_flash_mapped, total_bss
        if size == 0:
            return
        if not ibase:
            return
        if "=" in source and "0x" in source:
            return
        bucket, detail = classify(source, main_index)
        key = (bucket, detail, current_section, ibase)
        per_object[key] = per_object.get(key, 0) + size
        if current_section in ALLOC_FLASH_SECTIONS:
            per_bucket_flash[bucket] = per_bucket_flash.get(bucket, 0) + size
            total_flash_mapped += size
            dkey = (bucket, detail)
            per_bucket_detail[dkey] = per_bucket_detail.get(dkey, 0) + size
        elif current_section in ALLOC_RAM_SECTIONS or ibase == "bss":
            per_bucket_ram[bucket] = per_bucket_ram.get(bucket, 0) + size
            total_bss += size

    def record_with_relax(source, size, ibase, relax_size):
        if relax_size is not None and relax_size < size:
            record(source, relax_size, ibase)
        else:
            record(source, size, ibase)

    with open(map_path, errors="replace") as f:
        lines = f.read().splitlines()
    n = len(lines)
    i = 0
    while i < n:
        line = lines[i]
        if not in_map:
            if "Linker script and memory map" in line:
                in_map = True
            i += 1
            continue
        if line.startswith("OUTPUT(") or line.startswith("ENTRY("):
            i += 1
            continue
        stripped = line.rstrip("\n")
        if not stripped.strip():
            pending_input = ""
            pending_output_hdr = ""
            i += 1
            continue
        if "(size before relaxing)" in stripped:
            i += 1
            continue
        if pending_output_hdr:
            ao = ADDR_SIZE_ONLY_RE.match(stripped)
            if ao:
                current_section = pending_output_hdr
                in_output_section = current_section in ALLOC_FLASH_SECTIONS or (
                    current_section in ALLOC_RAM_SECTIONS
                )
                pending_output_hdr = ""
                pending_input = ""
                i += 1
                continue
            pending_output_hdr = ""
        om = OUTPUT_HDR_ONLY_RE.match(stripped)
        if om and not line.startswith(" ") and not line.startswith("\t"):
            pending_output_hdr = om.group(1)
            pending_input = ""
            i += 1
            continue
        hm = SECTION_HDR_RE.match(stripped)
        if hm and not line.startswith(" "):
            current_section = hm.group(1)
            in_output_section = current_section in ALLOC_FLASH_SECTIONS or (
                current_section in ALLOC_RAM_SECTIONS
            )
            pending_input = ""
            pending_output_hdr = ""
            i += 1
            continue
        if line.startswith(".") and "0x" in line:
            tok = line.split()
            if len(tok) >= 3 and tok[0].startswith(".") and tok[1].startswith("0x"):
                current_section = tok[0]
                in_output_section = current_section in ALLOC_FLASH_SECTIONS or (
                    current_section in ALLOC_RAM_SECTIONS
                )
                pending_input = ""
                pending_output_hdr = ""
                i += 1
                continue
        if not in_output_section:
            if stripped.startswith("LOAD "):
                pending_input = ""
                pending_output_hdr = ""
            i += 1
            continue
        fm = FILL_RE.match(stripped)
        if fm:
            size = int(fm.group(2), 16)
            if size:
                record("*fill*", size, "fill")
            pending_input = ""
            i += 1
            continue
        cm = CONTRIB_RE.match(stripped)
        if cm:
            size = int(cm.group(3), 16)
            source = cm.group(4).strip()
            relax_size = None
            if i + 1 < n:
                rm = RELAX_RE.match(lines[i + 1])
                if rm:
                    relax_size = int(rm.group(1), 16)
                    i += 1
            record_with_relax(source, size, input_base(cm.group(1)), relax_size)
            pending_input = ""
            i += 1
            continue
        am = ADDR_SIZE_SRC_RE.match(stripped)
        if am and pending_input:
            size = int(am.group(2), 16)
            source = am.group(3).strip()
            if ".obj" in source or ".a(" in source:
                relax_size = None
                if i + 1 < n:
                    rm = RELAX_RE.match(lines[i + 1])
                    if rm:
                        relax_size = int(rm.group(1), 16)
                        i += 1
                record_with_relax(source, size, input_base(pending_input), relax_size)
                pending_input = ""
                i += 1
                continue
        sm = SECTION_ONLY_RE.match(stripped)
        if sm:
            pending_input = sm.group(1)
            i += 1
            continue
        if stripped.startswith("LOAD "):
            pending_input = ""
        i += 1
    return {
        "per_object": per_object,
        "per_bucket_flash": per_bucket_flash,
        "per_bucket_ram": per_bucket_ram,
        "per_bucket_detail": per_bucket_detail,
        "total_flash_mapped": total_flash_mapped,
        "total_bss": total_bss,
    }


def parse_nm(elf_path):
    tool = find_tool("xtensa-esp32s3-elf-nm")
    try:
        out = subprocess.run(
            [tool, "--print-size", "--size-sort", "-t", "d", elf_path],
            capture_output=True,
            text=True,
            timeout=300,
        )
    except (OSError, subprocess.SubprocessError) as e:
        return [], "nm failed: %s" % e
    if out.returncode != 0:
        return [], "nm exit %s: %s" % (out.returncode, out.stderr[:500])
    syms = []
    for line in out.stdout.splitlines():
        parts = line.split()
        if len(parts) < 4:
            continue
        try:
            addr = int(parts[0], 10)
            size = int(parts[1], 10)
        except ValueError:
            continue
        if size <= 0:
            continue
        typ, name = parts[2], parts[3]
        if typ in ("T", "t", "R", "r", "D", "d", "W", "w", "O", "o"):
            if 0x3C000000 <= addr < 0x3E000000:
                mem = "flash-rodata"
            elif 0x42000000 <= addr < 0x44000000:
                mem = "flash-text"
            elif 0x40370000 <= addr < 0x40400000:
                mem = "iram"
            elif 0x3FC00000 <= addr < 0x40000000:
                mem = "dram"
            else:
                mem = "other"
            syms.append((size, addr, typ, name, mem))
    syms.sort(reverse=True)
    return syms, ""


def frozen_tree(frozen_dir):
    entries = []
    total = 0
    for root, _dirs, files in os.walk(frozen_dir):
        for fn in files:
            if not fn.endswith(".mpy"):
                continue
            full = os.path.join(root, fn)
            try:
                sz = os.path.getsize(full)
            except OSError:
                continue
            rel = os.path.relpath(full, frozen_dir)
            entries.append((sz, rel))
            total += sz
    entries.sort(reverse=True)
    rollup = {}
    for sz, rel in entries:
        top = rel.split(os.sep)[0] if os.sep in rel else "(top)"
        rollup[top] = rollup.get(top, 0) + sz
    return entries, rollup, total


def section_sizes(elf_path):
    tool = find_tool("xtensa-esp32s3-elf-size")
    try:
        out = subprocess.run([tool, "-A", "-d", elf_path], capture_output=True, text=True, timeout=120)
    except (OSError, subprocess.SubprocessError) as e:
        return "size failed: %s" % e
    if out.returncode != 0:
        return "size exit %s" % out.returncode
    return out.stdout


def sdkconfig_relevant(build_dir):
    path = os.path.join(build_dir, "sdkconfig")
    found = []
    try:
        with open(path, errors="replace") as f:
            for line in f:
                line = line.strip()
                for opt in SIZE_OPTS:
                    if opt in line:
                        found.append(line)
                        break
    except OSError as e:
        return ["sdkconfig unreadable: %s" % e]
    return found


def fmt(n):
    if n >= 1048576:
        return "%d (%0.1f MiB)" % (n, n / 1048576.0)
    return "%d (%0.1f KiB)" % (n, n / 1024.0)


def build_json_tree(label, bin_size, partition_size, bucket_flash, detail, frozen_entries):
    children = []
    buckets = {}
    for (bucket, member), size in detail.items():
        buckets.setdefault(bucket, []).append((size, member))
    for bucket in sorted(buckets, key=lambda b: -sum(s for s, _m in buckets[b])):
        total = sum(s for s, _m in buckets[bucket])
        members = sorted(buckets[bucket], reverse=True)[:40]
        kids = [{"name": m, "size": s} for s, m in members]
        children.append({"name": bucket, "size": total, "children": kids})
    fchildren = [{"name": rel, "size": sz} for sz, rel in frozen_entries[:200]]
    children.append(
        {
            "name": "frozen-mpy-files",
            "size": sum(s for s, _r in frozen_entries),
            "children": fchildren,
        }
    )
    return {
        "name": label,
        "bin_size": bin_size,
        "partition_size": partition_size,
        "headroom": partition_size - bin_size,
        "children": children,
        "bucket_flash": dict(sorted(bucket_flash.items(), key=lambda kv: -kv[1])),
    }


TREEMAP_HTML = """<!DOCTYPE html>
<html><head><meta charset="utf-8"><title>MPOS size drill-down</title>
<style>
body{font-family:sans-serif;margin:16px;background:#111;color:#eee}
#info{margin-bottom:12px}.node{position:absolute;overflow:hidden;border:1px solid #111;
box-sizing:border-box;font-size:11px;line-height:1.2;padding:2px;cursor:pointer}
a{color:#8cf}
</style></head><body>
<h2>MPOS firmware size drill-down</h2>
<div id="info">Click a block to zoom. <a href="size-data.json">size-data.json</a></div>
<div id="crumbs"></div>
<div id="map" style="position:relative;width:100%;height:80vh;background:#222"></div>
<script>
let ROOT=null, PATH=[];
async function load(){const r=await fetch("size-data.json");ROOT=await r.json();draw();}
function kb(n){return (n/1024).toFixed(1)+" KiB";}
function layout(items,x,y,w,h){
  const total=items.reduce((a,c)=>a+c.size,0)||1;let cx=x,cy=y;
  const horiz=w>=h;
  for(const it of items){const f=it.size/total;
    let nw= horiz?w*f:w, nh= horiz?h:h*f;
    it._x=horiz?cx:x; it._y=horiz?y:cy; it._w=nw; it._h=nh;
    if(horiz)cx+=nw; else cy+=nh;}}
function palette(name){
  let h=0;for(let i=0;i<name.length;i++)h=(h*31+name.charCodeAt(i))%360;
  return "hsl("+h+",45%,32%)";}
function node(){let p=ROOT;for(const i of PATH)p=p.children[i];return p;}
function draw(){
  const cur=node(), map=document.getElementById("map");
  const crumbs=document.getElementById("crumbs");
  crumbs.innerHTML=(PATH.length?'<a href="#" id="up">.. up</a> / ':"")+cur.name
    +" — "+kb(cur.size||cur.bin_size||0);
  const up=document.getElementById("up");
  if(up)up.onclick=e=>{e.preventDefault();PATH.pop();draw();};
  map.innerHTML="";
  const items=(cur.children||[]).slice().sort((a,b)=>b.size-a.size);
  const W=map.clientWidth,H=map.clientHeight;
  layout(items,0,0,W,H);
  items.forEach((it,idx)=>{
    const d=document.createElement("div");d.className="node";
    d.style.left=it._x+"px";d.style.top=it._y+"px";
    d.style.width=it._w+"px";d.style.height=it._h+"px";
    d.style.background=palette(it.name);
    d.title=it.name+" — "+kb(it.size);
    d.textContent=(it._w>70&&it._h>22)?it.name+" "+kb(it.size):"";
    if(it.children&&it.children.length)d.onclick=()=>{PATH.push(idx);draw();};
    map.appendChild(d);});
  document.getElementById("info").innerHTML=
    "bin: "+kb(ROOT.bin_size)+" / partition: "+kb(ROOT.partition_size)+
    " / headroom: "+kb(ROOT.headroom)+". Click a block to zoom.";
}
window.onresize=draw;load();
</script></body></html>
"""


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--build-dir", required=True)
    ap.add_argument("--out-dir", required=True)
    ap.add_argument("--label", default="size")
    args = ap.parse_args()

    build_dir = os.path.abspath(args.build_dir)
    out_dir = os.path.abspath(args.out_dir)
    os.makedirs(out_dir, exist_ok=True)

    elf = os.path.join(build_dir, "micropython.elf")
    map_path = os.path.join(build_dir, "micropython.map")
    bin_path = os.path.join(build_dir, "micropython.bin")
    fw_path = os.path.join(build_dir, "firmware.bin")
    frozen_dir = os.path.join(build_dir, "frozen_mpy")
    for p in (elf, map_path, bin_path):
        if not os.path.isfile(p):
            print("missing required file: %s" % p, file=sys.stderr)
            return 2

    bin_size = os.path.getsize(bin_path)
    fw_size = os.path.getsize(fw_path) if os.path.isfile(fw_path) else 0
    part_size, part_src = parse_partitions_size(build_dir)
    main_index = index_main_objects(build_dir)
    parsed = parse_map(map_path, main_index)
    syms, nm_err = parse_nm(elf)
    frozen_entries, frozen_rollup, frozen_total = frozen_tree(frozen_dir)
    sections = section_sizes(elf)
    sdk_lines = sdkconfig_relevant(build_dir)

    bucket_flash = parsed["per_bucket_flash"]
    detail = parsed["per_bucket_detail"]

    with open(os.path.join(out_dir, "objects.csv"), "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["bucket", "member", "output_section", "input_section", "bytes"])
        for (bucket, member, osec, isec), size in sorted(
            parsed["per_object"].items(), key=lambda kv: -kv[1]
        ):
            w.writerow([bucket, member, osec, isec, size])

    with open(os.path.join(out_dir, "symbols.csv"), "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["size", "addr", "type", "mem", "name"])
        for size, addr, typ, name, mem in syms[:500]:
            w.writerow([size, addr, typ, mem, name])

    with open(os.path.join(out_dir, "frozen.csv"), "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["bytes", "path"])
        for size, rel in frozen_entries:
            w.writerow([size, rel])

    with open(os.path.join(out_dir, "sections.txt"), "w") as f:
        f.write(sections)

    with open(os.path.join(out_dir, "sdkconfig-relevant.txt"), "w") as f:
        f.write("\n".join(sdk_lines) + "\n")

    tree = build_json_tree(args.label, bin_size, part_size, bucket_flash, detail, frozen_entries)
    with open(os.path.join(out_dir, "size-data.json"), "w") as f:
        json.dump(tree, f, indent=1)

    with open(os.path.join(out_dir, "size-treemap.html"), "w") as f:
        f.write(TREEMAP_HTML)

    flash_mapped = parsed["total_flash_mapped"]
    lines = []
    lines.append("label: %s" % args.label)
    lines.append("micropython.bin: %s" % fmt(bin_size))
    if fw_size:
        lines.append("firmware.bin:    %s" % fmt(fw_size))
    lines.append("ota_0 partition: %s  (source: %s)" % (fmt(part_size), part_src))
    lines.append("headroom:        %s%s" % (fmt(part_size - bin_size), "" if part_size - bin_size >= 0 else "  OVERFLOW"))
    lines.append("map-attributed flash (text+rodata+data): %s" % fmt(flash_mapped))
    lines.append("")
    lines.append("== flash footprint by bucket (from micropython.map) ==")
    for bucket, size in sorted(bucket_flash.items(), key=lambda kv: -kv[1])[:30]:
        lines.append("  %-28s %s  (%5.1f%% of mapped)" % (bucket, fmt(size), 100.0 * size / flash_mapped))
    lines.append("")
    lines.append("== frozen .mpy rollup (frozen_mpy/, compiled into frozen_content) ==")
    lines.append("  frozen_mpy total: %s in %d files" % (fmt(frozen_total), len(frozen_entries)))
    for top, size in sorted(frozen_rollup.items(), key=lambda kv: -kv[1])[:20]:
        lines.append("  %-28s %s" % (top, fmt(size)))
    lines.append("")
    lines.append("== top frozen .mpy files ==")
    for size, rel in frozen_entries[:30]:
        lines.append("  %-60s %s" % (rel, fmt(size)))
    lines.append("")
    lines.append("== top flash symbols (nm --size-sort) ==")
    if nm_err:
        lines.append("  " + nm_err)
    shown = 0
    for size, addr, typ, name, mem in syms:
        if mem not in ("flash-text", "flash-rodata"):
            continue
        lines.append("  %-8s %-12s %s" % (fmt(size), mem, name))
        shown += 1
        if shown >= 40:
            break
    lines.append("")
    lines.append("== biggest linked objects (flash) ==")
    for (bucket, member), size in sorted(detail.items(), key=lambda kv: -kv[1])[:40]:
        lines.append("  %-28s %-45s %s" % (bucket, member, fmt(size)))
    report = "\n".join(lines) + "\n"

    with open(os.path.join(out_dir, "size-report.txt"), "w") as f:
        f.write(report)

    md = []
    md.append("# Size report: %s" % args.label)
    md.append("")
    md.append("- micropython.bin: %s" % fmt(bin_size))
    md.append("- ota_0 partition: %s" % fmt(part_size))
    md.append("- headroom: %s" % fmt(part_size - bin_size))
    md.append("")
    md.append("## Flash by bucket")
    md.append("")
    md.append("| bucket | bytes | share |")
    md.append("|---|---|---|")
    for bucket, size in sorted(bucket_flash.items(), key=lambda kv: -kv[1])[:30]:
        md.append("| %s | %d | %0.1f%% |" % (bucket, size, 100.0 * size / flash_mapped))
    md.append("")
    md.append("## Frozen rollup")
    md.append("")
    md.append("| top dir | bytes |")
    md.append("|---|---|")
    for top, size in sorted(frozen_rollup.items(), key=lambda kv: -kv[1])[:20]:
        md.append("| %s | %d |" % (top, size))
    with open(os.path.join(out_dir, "size-report.md"), "w") as f:
        f.write("\n".join(md) + "\n")

    print(report)
    return 0


if __name__ == "__main__":
    sys.exit(main())
