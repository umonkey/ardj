/* definitions.h
 * - All declarations and defines for ices
 * Copyright (c) 2000 Alexander Hav?ng
 *
 * This program is free software; you can redistribute it and/or
 * modify it under the terms of the GNU General Public License
 * as published by the Free Software Foundation; either version 2
 * of the License, or (at your option) any later version.
 * 
 * This program is distributed in the hope that it will be useful,
 * but WITHOUT ANY WARRANTY; without even the implied warranty of
 * MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
 * GNU General Public License for more details.
 * 
 * You should have received a copy of the GNU General Public License
 * along with this program; if not, write to the Free Software
 * Foundation, Inc., 59 Temple Place - Suite 330, Boston, MA  02111-1307, USA.
 *
 */

#ifndef _ICES_DEFINITIONS_H
#define _ICES_DEFINITIONS_H

#ifdef _WIN32
# include <win32config.h>
#else
# include "config.h"
#endif

/**
 * Defaults for Ubuntu.
 */
#undef HAVE_LIBPYTHON
#undef HAVE_LIBXML
#define HAVE_DLFCN_H 1
#define HAVE_ERRNO_H 1
#define HAVE_FCNTL_H 1
#define HAVE_INTTYPES_H 1
#define HAVE_SETLINEBUF 1
#define HAVE_SETSID 1
#define HAVE_SIGNAL_H 1
#define HAVE_STDINT_H 1
#define HAVE_STDLIB_H 1
#define HAVE_STRFTIME 1
#define HAVE_STRINGS_H 1
#define HAVE_STRING_H 1
#define HAVE_SYS_SIGNAL_H 1
#define HAVE_SYS_SOCKET_H 1
#define HAVE_SYS_STAT_H 1
#define HAVE_SYS_TIME_H 1
#define HAVE_SYS_TYPES_H 1
#define HAVE_SYS_WAIT_H 1
#define HAVE_UNISTD_H 1
#define HAVE_VSNPRINTF 1
#define STDC_HEADERS 1
#define TIME_WITH_SYS_TIME 1

/**
 * Support for python playlist generators.
 * Ubuntu package: python2.6-dev
 */
#ifndef HAVE_LIBPYTHON
# define HAVE_LIBPYTHON
# define ICES_MODULEDIR "/usr/share/ices/modules"
#endif

/**
 * Support for perl playlist generators.
 * Ubuntu package:
 */
/*
#ifndef HAVE_LIBPERL
# define HAVE_LIBPERL
#endif
*/

/**
 * Support for XML based config files.
 * Ubuntu package: libxml2-dev
 */
#ifndef HAVE_LIBXML
# define HAVE_LIBXML
# define ICES_ETCDIR "/etc"
#endif

/**
 * Ubuntu package: libshout3-dev
 */
#ifndef HAVE_SHOUT_SHOUT_H
# define HAVE_SHOUT_SHOUT_H
#endif

/**
 * MP3 support.
 * Ubuntu package:
 */
#ifndef HAVE_LIBLAME
# define HAVE_LIBLAME
# define HAVE_LAME_LAME_H
#endif

/**
 * Ubuntu package: libflac-dev
 */
#undef HAVE_LIBFLAC

/**
 * MP4 support.
 * Ubuntu package: libfaad-dev
 */
#undef HAVE_LIBFAAD

#ifdef VERSION
# undef VERSION
#endif
#define VERSION "0.4-ardj"

#ifndef __USE_MISC
# define __USE_MISC
#endif

#ifndef __USE_GNU
# define __USE_GNU
#endif

#ifndef __USE_BSD
# define __USE_BSD
#endif

/*
#ifndef __EXTENSIONS__
# define __EXTENSIONS__
#endif
*/

/*
#ifndef _GNU_SOURCE
# define _GNU_SOURCE
#endif
*/

#ifndef __USE_POSIX
# define __USE_POSIX
#endif

#include <stdio.h>
#include <stdarg.h>
#ifdef HAVE_SHOUT_SHOUT_H
# include <shout/shout.h>
#else
# include <shout.h>
#endif
#include <stdlib.h>
#include <string.h>
#include <ctype.h>

#ifdef HAVE_ERRNO_H
#include <errno.h>
#endif

#ifdef HAVE_UNISTD_H
#include <unistd.h>
#endif

#ifdef HAVE_SYS_TYPES_H
#include <sys/types.h>
#endif

#ifdef HAVE_SYS_STAT_H
#include <sys/stat.h>
#endif

#ifdef HAVE_FCNTL_H
#include <fcntl.h>
#endif

/* This has all the datatypes */
#include "icestypes.h"

#include "setup.h"
#include "stream.h"
#include "log.h"
#include "util.h"
#include "cue.h"
#include "id3.h"
#include "mp3.h"
#include "signals.h"
#include "reencode.h"
#include "ices_config.h"
#include "playlist/playlist.h"

ices_plugin_t *crossfade_plugin(int secs);
void rg_set_track_gain(double);
void rg_set_track_gain(double gain);
double rg_get_track_gain(void);

#define BUFSIZE 8192
#define ICES_DEFAULT_HOST "127.0.0.1"
#define ICES_DEFAULT_PORT 8000
#define ICES_DEFAULT_MOUNT "/ices"
#define ICES_DEFAULT_PASSWORD "letmein"
#define ICES_DEFAULT_PROTOCOL http_protocol_e
#define ICES_DEFAULT_NAME "Default stream name"
#define ICES_DEFAULT_GENRE "Default genre"
#define ICES_DEFAULT_DESCRIPTION "Default description"
#define ICES_DEFAULT_URL "http://www.icecast.org/"
#define ICES_DEFAULT_BITRATE 128
#define ICES_DEFAULT_ISPUBLIC 1
#define ICES_DEFAULT_MODULE "ices"
#define ICES_DEFAULT_CONFIGFILE "ices.conf"
#define ICES_DEFAULT_PLAYLIST_FILE "playlist.txt"
#define ICES_DEFAULT_RANDOMIZE_PLAYLIST 0
#define ICES_DEFAULT_DAEMON 0
#define ICES_DEFAULT_BASE_DIRECTORY "/tmp"
#define ICES_DEFAULT_PLAYLIST_TYPE ices_playlist_builtin_e;
#define ICES_DEFAULT_VERBOSE 0
#define ICES_DEFAULT_REENCODE 0

#endif
