mydir=$(readlink -f "$0")
mydir=$(dirname "$mydir") # scripts dir

builtindir=$(readlink -f "$mydir"/../internal_filesystem/builtin)

tempdir=$(mktemp -d)

"$mydir"/compile_dir.sh "$builtindir" "$tempdir"

pushd "$mydir"/../freezeFS/
python3 -m freezefs --target /builtin --on-import mount "$tempdir" freezefs_mount_builtin.py
#python3 -m freezefs --target /builtin --on-import mount --compress --wbits 14 "$tempdir" freezefs_mount_builtin.py
popd

rm -rf "$tempdir"
