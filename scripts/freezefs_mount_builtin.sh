mydir=$(readlink -f "$0")
mydir=$(dirname "$mydir") # scripts dir

builtindir=$(readlink -f "$mydir"/../internal_filesystem/builtin)

pushd "$mydir"/../freezeFS/
python3 -m freezefs --target /builtin --on-import mount "$builtindir" freezefs_mount_builtin.py
popd
