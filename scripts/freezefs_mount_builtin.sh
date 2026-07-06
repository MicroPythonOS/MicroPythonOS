mydir=$(readlink -f "$0")
mydir=$(dirname "$mydir") # scripts dir

march=""
while [ $# -gt 0 ]; do
	case "$1" in
		-march)
			march="$2"
			shift 2
			;;
		-march=*)
			march="${1#-march=}"
			shift
			;;
		*)
			echo "Usage: $0 [-march <arch>]"
			exit 1
			;;
	esac
done

builtindir=$(readlink -f "$mydir"/../internal_filesystem/builtin)

tempdir=$(mktemp -d)

if [ -n "$march" ]; then
	"$mydir"/compile_dir.sh -march "$march" "$builtindir" "$tempdir"
	result=$?
else
	"$mydir"/compile_dir.sh "$builtindir" "$tempdir"
	result=$?
fi
if [ $result -ne 0 ]; then
	echo "aborting because compile_dir.sh failed"
	exit 1
fi

pushd "$mydir"/../freezeFS/
python3 -m freezefs --target /builtin --on-import mount "$tempdir" freezefs_mount_builtin.py
#python3 -m freezefs --target /builtin --on-import mount --compress --wbits 14 "$tempdir" freezefs_mount_builtin.py
popd

rm -rf "$tempdir"
