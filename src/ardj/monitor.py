#!/usr/bin/env python
# encoding=utf-8

from __future__ import print_function

import os
import re
import shlex
import subprocess
import sys
import time
import traceback


REQUIRED_PROGRAMS = ["icecast2", "ezstream", "mpg123", "lame", "sox", "oggenc"]

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

# This is where the music will be stored.  You MUST NOT put the music there
# manually, see the incoming folder below.
musicdir: %(ARDJ_CONFIG_DIR)s/music


# This is the folder where you should put music that you want to add to the
# database (will be moved to the internal location in few minutes).  This
# folder is typically accessible over ftp or sftp.
incoming_path: %(ARDJ_CONFIG_DIR)s/music/incoming


# Define labels that will be applied to all uploaded files.  This is typically
# one label which lets you later find untagged tracks.
incoming_labels: [music, tagme]


# Specify how many recently played artists should be skipped when picking a
# random track.  For example, if this is set to 5, then 5 most recently played
# artists will be ignored.
#
# Caution: only enable this when you have enough music to play without
# repeating, otherwise ardj will go into failure mode.
dupes: 0


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
#icecast_stats_url: "http://admin:hackme@localhost:8000/admin/stats.xml"


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
""",

"playlist.yaml": """# Play a jingle every 15 minutes.
- name: jingles
  labels: [jingle]
  delay: 15


# Unless other rules apply, play everything with the "music" label.
- name: music
  labels: [music]
"""
}


def log_error(message):
    print(message, file=sys.stderr)


class ProcessMonitor(object):
    def __init__(self, name, command, config_dir):
        self.name = name
        self.command = command
        self.pidfile = os.path.join(config_dir, name + ".pid")

        self.logname = os.path.join(config_dir, name + ".log")
        self.logfile = open(self.logname, "ab")

        self.p = None
        self.run()

    def __del__(self):
        if os.path.exists(self.pidfile):
            os.unlink(self.pidfile)

        self.logfile.flush()
        if os.stat(self.logname).st_size == 0:
            os.unlink(self.logname)

    def run(self):
        env = os.environ.copy()
        env["PATH"] += os.pathsep + os.path.dirname(sys.argv[0])

        self.p = subprocess.Popen(self.command,
            stdout=self.logfile,
            stderr=self.logfile,
            env=env)
        self.log("> %s" % " ".join(self.command))

        with open(self.pidfile, "wb") as f:
            f.write(str(self.p.pid) + "\n")

    def check(self):
        if self.p.returncode is None:
            self.p.poll()
        else:
            self.log("%s exited with status %d, restarting." \
                % (self.command[0], self.p.returncode))
            self.run()

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


def have_program(command):
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
            return path
        raise Exception("Config file %s not found." % path)
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

    threads.append(ProcessMonitor("icecast2",
        ["icecast2", "-c", get_config("icecast2.xml")],
        config_dir))
    threads.append(ProcessMonitor("ezstream",
        ["ezstream", "-c", get_config("ezstream.xml")],
        config_dir))
    threads.append(ProcessMonitor("web-server",
        [sys.argv[0], "start-web-server"],
        config_dir))
    threads.append(ProcessMonitor("scrobbler",
        [sys.argv[0], "start-scrobbler"],
        config_dir))
    threads.append(ProcessMonitor("jabber",
        [sys.argv[0], "jabber"],
        config_dir))

    player_cmd = get_config_option("bg_player")
    if player_cmd is not None:
        threads.append(ProcessMonitor(name="audio-player",
            command=shlex.split(player_cmd),
            config_dir=config_dir))

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
        log_error("WARNING: the music database is empty. Put some files in %s and run 'ardj find-new-files'." % music_dir)


def run_cli(*args):
    check_required_programs()

    try:
        threads = get_threads()
    except Exception, e:
        print("Error: %s" % e, file=sys.stderr)
        print(traceback.format_exc(e), file=sys.stderr)
        sys.exit(1)

    print_welcome()

    while True:
        for t in threads:
            try:
                t.check()
            except Exception, e:
                print("Error: %s" % e, file=sys.stderr)
                print(traceback.format_exc(e), file=sys.stderr)

        try:
            time.sleep(5)
        except KeyboardInterrupt:
            print("Interrupted.")
            for t in threads:
                t.stop()
            sys.exit(1)
