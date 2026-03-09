mydir=$(readlink -f "$0")
mydir=$(dirname "$mydir")

cd "$mydir"
rm -rf build

make -f Makefile_amd64 </dev/null
result=$?
[ $result -ne 0 ] && exit $result

mv mpong.mpy "$mydir"/../../internal_filesystem/apps/com.micropythonos.mpong/assets/mpong_amd64.mpy
