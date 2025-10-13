builtindir=$(readlink -f "MicroPythonOS/internal_filesystem/builtin")

pushd ../freezeFS/
python3 -m freezefs --target /builtin --on-import mount "$builtindir" freezefs_mount_builtin.py
popd
