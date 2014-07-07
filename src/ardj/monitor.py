#!/usr/bin/env python
# encoding=utf-8

from __future__ import print_function

import logging
import os
import re
import shlex
import subprocess
import sys
import time
import traceback


REQUIRED_PROGRAMS = ["icecast2", "ezstream|ices", "mpg123", "lame", "sox", "oggenc"]

UBUNTU_REQUIREMENTS_MAP = {"icecast2": "icecast2",
    "ezstream|ices": "ezstream",
    "mpg123": "mpg123",
    "lame": "lame",
    "sox": "sox",
    "oggenc": "oggenc"}

CONFIG_EXAMPLES = {
"icecast2.xml": """<icecast>
    <limits>
        <clients>128</clients>
        <sources>3</sources>
        <threadpool>5</threadpool>
        <queue-size>524288</queue-size>
        <client-timeout>30</client-timeout>
        <header-timeout>15</header-timeout>
        <source-timeout>10</source-timeout>
        <burst-on-connect>1</burst-on-connect>
        <burst-size>131072</burst-size>
    </limits>

    <authentication>
        <!-- Sources log in with username 'source' -->
        <source-password>hackme</source-password>

        <!-- Admin logs in with the username given below -->
        <admin-user>admin</admin-user>
        <admin-password>hackme</admin-password>
    </authentication>

    <listen-socket>
        <port>8000</port>
    </listen-socket>

    <mount>
        <mount-name>/music.mp3</mount-name>
        <password>hackme</password>
    </mount>

    <mount>
        <mount-name>/live.mp3</mount-name>
        <password>hackme</password>
        <fallback-mount>/music.mp3</fallback-mount>
        <fallback-override>1</fallback-override>
        <!--
        <dump-file>%(HOME)s/.ardj/dump/last-live-stream.mp3</dump-file>
        <on-connect>%(HOME)s/.ardj/on-live-connected</on-connect>
        <on-disconnect>%(HOME)s/.ardj/on-live-disconnected</on-disconnect>
        -->
    </mount>

    <paths>
        <basedir>/usr/share/icecast2</basedir>
        <logdir>%(HOME)s/.ardj</logdir>
        <webroot>/usr/share/icecast2/web</webroot>
        <adminroot>/usr/share/icecast2/admin</adminroot>
        <alias source="/" dest="/status.xsl"/>
    </paths>

    <logging>
        <accesslog>icecast2-access.log</accesslog>
        <errorlog>icecast2-error.log</errorlog>
        <loglevel>3</loglevel>
        <logsize>10000</logsize>
    </logging>
</icecast>
""",

"ezstream.xml": """<ezstream>
    <url>http://localhost:8000/music.mp3</url>
    <sourcepassword>hackme</sourcepassword>
    <format>MP3</format>
    <playlist_program>1</playlist_program>
    <filename>%(ARDJ_BIN_DIR)s/ardj-next-track</filename>

    <metadata_progname>%(ARDJ_BIN_DIR)s/ezstream-meta</metadata_progname>
    <metadata_format>"@t@" by @a@</metadata_format>

    <svrinfoname>ARDJ based radio</svrinfoname>
    <svrinfourl>http://umonkey.net/ardj/</svrinfourl>
    <svrinfogenre>Music</svrinfogenre>
    <svrinfodescription>This radio is powered by ardj.</svrinfodescription>
    <svrinfobitrate>128</svrinfobitrate>
    <svrinfochannels>2</svrinfochannels>
    <svrinfosamplerate>44100</svrinfosamplerate>
    <svrinfopublic>1</svrinfopublic>

    <reencode>
        <enable>1</enable>
        <encdec>
            <format>FLAC</format>
            <match>.flac</match>
            <decode>flac -s -d --force-raw-format --sign=signed --endian=little -o - "@T@"</decode>
        </encdec>
        <encdec>
            <format>MP3</format>
            <match>.mp3</match>
            <decode>mpg123 --rva-radio --stereo --rate 44100 --stdout "@T@"</decode>
            <encode>lame --preset cbr 128 -r -s 44.1 --bitwidth 16 - -</encode>
        </encdec>
        <encdec>
            <format>VORBIS</format>
            <match>.ogg</match>
            <decode>sox --replay-gain track "@T@" -r 44100 -c 2 -t raw -e signed-integer -</decode>
            <encode>oggenc -r -B 16 -C 2 -R 44100 --raw-endianness 0 -q 1.5 -t "@M@" -</encode>
        </encdec>
    </reencode>
</ezstream>
""",

"ardj.yaml": """# This is the main configuration file for ardj.
# If you have questions even after reading the comments, try reading
# the documentation at <http://umonkey.net/ardj/doc/>
#
# If something doesn't work, write to <hex@umonkey.net>.

# This is where you put the music and jingles that ardj should play.
musicdir: %(ARDJ_CONFIG_DIR)s/music


# This is the folder where files uploaded via Jabber should be stored.
# Should be within musicdir, otherwise files won't be visible until
# operator handles them.
incoming_path: %(ARDJ_CONFIG_DIR)s/music/incoming


# Specify how many recently played artists should be skipped when picking a
# random track.  For example, if this is set to 5, then 5 most recently played
# artists will be ignored.
#
# If ardj can't find new music to play, it will resort to playing a completely
# random track.  So, setting this value too high doesn't break the stream, but
# can effectively render some playlists empty, if they have less than specified
# artists.
dupes: 5


# Default labels for new files.
default_labels: [music, tagme]


# If you want to display a schedule of upcoming events on your web site,
# specify the name of the file where the information should be written to.  The
# file is updated when you run the 'ardj update-events' command, so you'll need
# to add that to your crontab, too.
#event_schedule_path: %(ARDJ_CONFIG_DIR)s/public/upcoming-events.json

# By default event schedule contains artists that have tracks with the "music"
# label.  You can set a different label here.
#event_schedule_label_filter: music

# By default event schedule contains artists which have tracks with weight 1.0
# or higher.  You can change this value here, to widen or narrow the range of
# announced artists.
#event_schedule_weight: 1.0


# If you want to track programs, name a file which will hold the current
# program name.  Program name is the name of a playlist which has the non-empty
# "program" property.  When a track is picked from such playlist, program name
# is updated.  You can use this to display things on your web site, for example.
#program_name_file: %(ARDJ_CONFIG_DIR)s/public/current_ardj_program.txt

# Uncomment this to announce program changes to the chat room.
#program_name_announce: true

# If you want to run a script when program changes, specify its name here.
#program_name_handler: %(ARDJ_CONFIG_DIR)s/on-program-change


# If you plan to use Jabber, uncomment this block and insert the correct values.
#jabber_id: "alice:secret@server.com"

# Here you can specify admin emails.  They have extra privileges when using
# jabber or the CLI console (ardj console).
jabber_admins:
- %(MAIL)s
- console

# Pomote most active users to admins.  You can define how many users from the
# top voters are promoted and how many days count.
#promote_voters: 10
#promote_voters_days: 14

# This adds track info to the bot's status message.
use_jabber_status: yes

# This enables sending XMPP Tunes (doesn't work with Gmail).
#use_jabber_tunes: yes

# If you want to add the bot to a chat room, specify his full jid there.
#
#jabber_chat_room: my_radio@conference.jabber.ru/MyBot


# If you want to be able to send twits using ardj (using the "twit" jabber
# command or "ardj twit" from the command line), you need to register yourself
# an application and get an access token.  This can be done on the
# dev.twitter.com/apps website.  Don't forget to set the read-write permission
# for your application, otherwise you'll only be able to read replies.
#twitter:
#  consumer_key: XXXXXXXXXXXXXXXXXXXXX
#  consumer_secret: XXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXX
#  access_token_key: XXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXX
#  access_token_secret: XXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXX


# If you want to see how many users are currently listening to the stream, enable this.
icecast_stats_url: "http://localhost:8000/status2.xsl"


# If you want to use speech synthesis, upload a random OGG/Vorbis track and
# specify its id here.  You can also specify a custom voice.
#festival_track_id: 1234
#festival_voice: voice_msu_ru_nsh_clunits


# Uncomment this to disable voting (e.g., for database maintenance).
#enable_voting: no

# This is where the messages will be logged.
log: %(ARDJ_CONFIG_DIR)s/ardj.log
log_level: debug
log_format_string: "ardj[%%(process)d]: %%(levelname)s %%(message)s"

# Comment out after the playlists are tuned and work well.
debug_playlist: yes


# This is the database where the runtime data is stored.
#
database_path: %(ARDJ_CONFIG_DIR)s/ardj.sqlite


# The socket that the database server listens to.  On a typical installation
# you would use a local server, so no need to change anythint.  However, if for
# some reason you wish to move the database server outside, you can specify a
# different location.
#webapi_socket: 127.0.0.1:8080


# The root folder of your WebAPI site.  That's where the static files are.
webapi_root: %(ARDJ_CONFIG_DIR)s/website


# Here you can customize token verification emails, sent by WebAPI when
# a user requests access.
#TokenMailer_subject: "OMG! token"
#TokenMailer_plain: "Your token [{token}] is ready. Open <{link}> to activate it."
#TokenMailer_html: "<p>Your token [{token}] is ready. Open <{link}> to activate it.</p>"
""",

"playlist.yaml": """# Play a jingle every 15 minutes.
- name: jingles
  labels: [jingle]
  delay: 15


# Unless other rules apply, play everything with the "music" label.
- name: music
  labels: [music]
""",

"ices.conf": """<?xml version="1.0"?>
<ices:Configuration xmlns:ices="http://www.icecast.org/projects/ices">
  <Playlist>
    <Randomize>0</Randomize>
    <Type>python</Type>
    <Module>ardj_ices</Module>
    <Crossfade>5</Crossfade>
  </Playlist>

  <Execution>
    <Background>0</Background>
    <Verbose>1</Verbose>
    <BaseDirectory>%(ARDJ_CONFIG_DIR)s</BaseDirectory>
  </Execution>

  <Stream>
    <Server>
      <!-- Hostname or ip of the icecast server you want to connect to -->
      <Hostname>localhost</Hostname>
      <!-- Port of the same -->
      <Port>8000</Port>
      <!-- Encoder password on the icecast server -->
      <Password>hackme</Password>
      <!-- Header protocol to use when communicating with the server.
           Shoutcast servers need "icy", icecast 1.x needs "xaudiocast", and
       icecast 2.x needs "http". -->
      <Protocol>http</Protocol>
    </Server>

    <!-- The name of the mountpoint on the icecast server -->
    <Mountpoint>/music.mp3</Mountpoint>
    <!-- The name of the dumpfile on the server for your stream. DO NOT set
     this unless you know what you're doing.
    <Dumpfile>ices.dump</Dumpfile>
    -->
    <!-- The name of you stream, not the name of the song! -->
    <Name>Default stream</Name>
    <!-- Genre of your stream, be it rock or pop or whatever -->
    <Genre>Default genre</Genre>
    <!-- Longer description of your stream -->
    <Description>Default description</Description>
    <!-- URL to a page describing your stream -->
    <URL>http://localhost/</URL>
    <!-- 0 if you don't want the icecast server to publish your stream on
     the yp server, 1 if you do -->
    <Public>0</Public>

    <!-- Stream bitrate, used to specify bitrate if reencoding, otherwise
     just used for display on YP and on the server. Try to keep it
     accurate -->
    <Bitrate>128</Bitrate>
    <!-- If this is set to 1, and ices is compiled with liblame support,
     ices will reencode the stream on the fly to the stream bitrate. -->
    <Reencode>1</Reencode>
    <!-- Number of channels to reencode to, 1 for mono or 2 for stereo -->
    <!-- Sampe rate to reencode to in Hz. Leave out for LAME's best choice
    <Samplerate>44100</Samplerate>
    -->
    <Channels>2</Channels>
  </Stream>
</ices:Configuration>
"""
}


def log_error(message):
    logging.error(message)


def log_warning(message):
    logging.warning(message)


class ProcessMonitor(object):
    def __init__(self, name, command, config_dir):
        self.name = name
        self.command = command

        self.pidfile = None
        self.logname = None
        self.logfile = None

        self.pidfile = os.path.join(config_dir, name + ".pid")

        self.logname = os.path.join(config_dir, name + ".log")
        self.logfile = open(self.logname, "ab")
        os.fchmod(self.logfile.fileno(), 0640)

        self.p = None
        self.run()

    def __del__(self):
        self.remove_pid_file()

        if self.logfile:
            self.logfile.flush()

        if os.stat(self.logname).st_size == 0:
            os.unlink(self.logname)

    def remove_pid_file(self):
        if os.path.exists(self.pidfile):
            os.unlink(self.pidfile)

    def run(self):
        env = os.environ.copy()
        env["PATH"] += os.pathsep + os.path.dirname(sys.argv[0])

        if "ardj_python_path" in os.environ:
            env["PYTHONPATH"] = os.environ["ardj_python_path"]

        self.p = subprocess.Popen(self.command,
            stdout=self.logfile,
            stderr=self.logfile,
            env=env)
        self.log("> %s" % " ".join(self.command))

        with open(self.pidfile, "wb") as f:
            f.write(str(self.p.pid) + "\n")
            os.fchmod(f.fileno(), 0640)

    def check(self):
        if self.p.returncode is None:
            self.p.poll()
        else:
            ok = " (bad)" if self.p.returncode else " (this seems OK)"
            self.log("exited with status %d%s, restarting; logs are in %s" \
                % (self.p.returncode, ok, self.get_log_name()))

            self.remove_pid_file()
            self.run()

    def get_log_name(self):
        if self.name == "icecast2":
            return "~/.ardj/icecast2-error.log"
        else:
            return "~/.ardj/%s.log" % self.name

    def stop(self):
        if self.p is not None:
            self.log("terminating.")
            try:
                self.p.kill()
            except Exception:
                pass

    def log(self, message):
        ts = time.strftime("%H:%M:%S")
        if message:
            for line in message.rstrip().split("\n"):
                name = self.name
                if self.p:
                    name += "(%s)" % self.p.pid
                print("%s [%s] %s" % (ts, name, line))


class WebServerMonitor(ProcessMonitor):
    @classmethod
    def start(cls, threads, config_dir):
        path = get_config_option("webapi_root")
        if not path:
            return

        if not os.path.exists(path):
            os.makedirs(path)

        threads.append(cls(
            "web-server",
            [sys.argv[0], "web", "serve"],
            config_dir))


class ScrobblerMonitor(ProcessMonitor):
    @classmethod
    def start(cls, threads, config_dir):
        if not get_config_option("last.fm"):
            return

        threads.append(cls(
            "scrobbler",
            [sys.argv[0], "scrobbler", "start"],
            config_dir))


class JabberMonitor(ProcessMonitor):
    @classmethod
    def start(cls, threads, config_dir):
        if not get_config_option("jabber_id"):
            return

        threads.append(cls(
            "jabber",
            [sys.argv[0], "jabber", "run-bot"],
            config_dir))


class PlayerMonitor(ProcessMonitor):
    @classmethod
    def start(cls, threads, config_dir):
        cmd = get_config_option("bg_player")
        if not cmd:
            return

        threads.append(cls(
            "audio-player",
            shlex.split(cmd),
            config_dir))


class ServerMonitor(ProcessMonitor):
    @classmethod
    def start(cls, threads, config_dir):
        threads.append(cls(
            "icecast2",
            ["icecast2", "-c", get_config("icecast2.xml")],
            config_dir))


class SourceMonitor(ProcessMonitor):
    """Runs ices or ezstream"""
    @classmethod
    def start(cls, threads, config_dir):
        threads.append(cls.get_command(config_dir))

    @classmethod
    def get_command(cls, config_dir):
        if have_program("ices"):
            name = "ices"
            args = ["ices", "-c", get_config("ices.conf")]
        else:
            name = "ezstream"
            args = ["ezstream", "-c", get_config("ezstream.xml")]

        return cls(name, args, config_dir)


def have_program(commands):
    for command in commands.split("|"):
        for path in os.getenv("PATH").split(os.pathsep):
            fn = os.path.join(path, command)
            if os.path.exists(fn):
                return True
    return False


def check_required_programs():
    missing = []
    for program in REQUIRED_PROGRAMS:
        if not have_program(program):
            missing.append(program)

    if missing:
        print("Please install %s." % ", ".join(missing),
            file=sys.stderr)

        if have_program("apt-get"):
            print("Try this command: sudo apt-get install %s" % (
                " ".join([UBUNTU_REQUIREMENTS_MAP[r] for r in missing])))

        sys.exit(1)


def get_config(name):
    from ardj import settings
    config_dir = settings.get_config_dir()

    path = os.path.join(config_dir, name)
    if not os.path.exists(path):
        if name in CONFIG_EXAMPLES:
            env = os.environ.copy()
            env["ARDJ_PATH"] = sys.argv[0]
            env["ARDJ_BIN_DIR"] = os.path.dirname(sys.argv[0])
            env["ARDJ_CONFIG_DIR"] = config_dir
            try:
                data = CONFIG_EXAMPLES[name] % env
            except Exception, e:
                raise Exception("Unable to format %s: %s" % (name, e))
            with open(path, "wb") as f:
                f.write(data)
            os.chmod(path, 0640)
            print("Created file %s with default contents." % path)
        else:
            raise Exception("Config file %s not found." % path)

    try:
        os.chmod(path, 0640)
    except OSError, e:
        log_error("Could not set permissions on %s: %s" % (path, e))

    return path


def get_config_option(name):
    try:
        from ardj import settings
        return settings.get(name)
    except Exception, e:
        log_error("Error getting config option %s: %s" % (name, e))
        log_error(traceback.format_exc(e))
    return None


def autocreate_configs():
    """Create missing config files and directories."""
    data = {}
    for filename in CONFIG_EXAMPLES.keys():
        data[filename] = get_config(filename)
    return data


def get_threads():
    threads = []

    from ardj import settings
    config_dir = settings.get_config_dir()

    os.putenv("ARDJ_CONFIG_DIR", config_dir)

    get_config("ardj.yaml")
    get_config("playlist.yaml")

    ServerMonitor.start(threads, config_dir)
    SourceMonitor.start(threads, config_dir)
    WebServerMonitor.start(threads, config_dir)
    ScrobblerMonitor.start(threads, config_dir)
    JabberMonitor.start(threads, config_dir)
    PlayerMonitor.start(threads, config_dir)

    return threads


def print_welcome():
    """Prints the welcome message, which currently contains a link to the MP3
    stream."""
    config_name = get_config("ezstream.xml")

    with open(config_name, "rb") as f:
        matches = re.search("<url>(.+)</url>", f.read())
        if matches:
            print("You can listen to your stream at %s" % matches.group(1))
        else:
            print("Could not find stream URL in ezstream.xml :(", file=sys.stderr)

    from ardj import tracks
    count = tracks.count_available()
    if not count:
        from ardj import settings
        music_dir = settings.get_music_dir()
        log_warning("The music database is empty. Put some files in %s and run 'ardj tracks scan'." % music_dir)


def cmd_run(*args):
    """
    Run all server components.
    """
    check_required_programs()
    #check_file_permissions()

    from database import init_database
    init_database()

    try:
        threads = get_threads()
    except Exception, e:
        print("Error: %s" % e, file=sys.stderr)
        print(traceback.format_exc(e), file=sys.stderr)
        sys.exit(1)

    print_welcome()
    os.umask(044)

    while True:
        for t in threads:
            try:
                t.check()
            except Exception, e:
                print("Error: %s" % e, file=sys.stderr)
                print(traceback.format_exc(e), file=sys.stderr)

        try:
            time.sleep(1)
        except KeyboardInterrupt:
            print("Interrupted.")
            for t in threads:
                t.stop()
            sys.exit(1)
