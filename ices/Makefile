COMPILE_FLAGS=-g -O2 -Wall -Werror -pthread -c -I/usr/include/libxml2
LINK_FLAGS=-ldl -lm -lmp3lame -logg -lpthread -lpython2.6 -lshout -lutil -lvorbis -lvorbisfile -lxml2

build: ices.ardj

clean:
	rm -f ices src/*.o src/*/*.o

ices.ardj: src/crossfade.o src/cue.o src/ices.o src/ices_config.o src/id3.o src/in_flac.o src/in_mp4.o src/in_vorbis.o src/log.o src/metadata.o src/mp3.o src/playlist/playlist.o src/playlist/pm_builtin.o src/playlist/pm_perl.o src/playlist/pm_python.o src/playlist/rand.o src/reencode.o src/replaygain.o src/setup.o src/signals.o src/stream.o src/util.o
	gcc -o $@ ${LINK_FLAGS} $^

src/definitions.h: src/cue.h src/ices_config.h src/icestypes.h src/id3.h src/log.h src/mp3.h src/reencode.h src/setup.h src/signals.h src/stream.h src/util.h
src/cue.c: src/metadata.h
src/id3.c: src/metadata.h src/replaygain.h
src/in_flac.c: src/in_flac.h src/metadata.h src/replaygain.h
src/in_mp4.c: src/in_mp4.h src/metadata.h
src/in_vorbis.c: src/in_vorbis.h src/metadata.h src/replaygain.h
src/replaygain.c: src/replaygain.h
src/setup.c: src/metadata.h
src/stream.c: src/id3.h src/in_mp4.h src/in_vorbis.h src/metadata.h src/replaygain.h

%.o: %.c src/definitions.h
	gcc -o $@ ${COMPILE_FLAGS} $<

test:
	make -C testing test

ubuntu-depends:
	sudo apt-get -y install libshout3-dev python2.6-dev libmp3lame-dev
