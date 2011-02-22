all: mp3 vorbis

clean:
	rm -f *.mp3 *.ogg

mp3: mp3-mono-44.mp3 mp3-mono-48.mp3 mp3-stereo-44.mp3 mp3-stereo-48.mp3

vorbis: vorbis-mono-48.ogg vorbis-stereo-44.ogg

mp3-mono-44.mp3: mp3-mono-44.wav
	lame -m m --resample 44.1 $< $@

mp3-mono-48.mp3: mp3-mono-48.wav
	lame -m m --resample 48 $< $@

mp3-stereo-44.mp3: mp3-stereo-44.wav
	lame -m s --resample 44.1 $< $@

mp3-stereo-48.mp3: mp3-stereo-48.wav
	lame -m s --resample 48 $< $@

vorbis-mono-48.ogg: vorbis-mono-48.wav
	oggenc -o $@ $<

vorbis-stereo-44.ogg: vorbis-stereo-44.wav
	oggenc -o $@ $<

test:
	../ices -C `pwd` -c ices.conf
