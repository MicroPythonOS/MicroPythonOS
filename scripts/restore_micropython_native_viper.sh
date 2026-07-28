#echo "Running scripts/restore_micropython_native_viper.sh to 'git restore' files that were modified to disable micropython.native or micropython.viper..."

echo "Check the diff to make sure it's only native and viper stuff!"
sleep 3

git diff internal_filesystem/apps/com.micropythonos.draw/draw.py internal_filesystem/lib/mpos/audio/adpcm_ima.py internal_filesystem/lib/mpos/audio/stream_wav.py internal_filesystem/builtin/apps/com.micropythonos.appstore/blurhash.py

echo "restoring in 3 seconds..."
sleep 3

git restore internal_filesystem/apps/com.micropythonos.draw/draw.py \
internal_filesystem/lib/mpos/audio/adpcm_ima.py \
internal_filesystem/lib/mpos/audio/stream_wav.py \
internal_filesystem/builtin/apps/com.micropythonos.appstore/blurhash.py

# not these?
#internal_filesystem/apps/com.micropythonos.duke_launcher/retrogo_launcher.py \
#internal_filesystem/apps/com.micropythonos.retrocore_launcher/retrogo_launcher.py \
#internal_filesystem/builtin/apps/com.micropythonos.appstore/appstore.py \

cd micropython-nostr/
git restore nostr/nip44.py
cd -
