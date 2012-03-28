#!/usr/bin/env python

import subprocess
import time

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt


now = time.strftime("%Y-%m")

def filter_data(kind, text):
    data = {}
    for line in text.strip().split("\n"):
        x, k, v = line.split(",")
        if x == kind:
            data[int(k)] = int(v)
    return data


def plot_data(filename, data, prefix, xtitle="Time", title="Vote distribution"):
    # some optimization
    if os.path.exists(filename):
        return

    fig = plt.figure(1, (10, 5))
    ax = fig.add_subplot(111)

    data = filter_data(prefix, data)

    _min = min(data.keys())
    _max = max(data.keys())

    for k, v in data.items():
        ax.bar(k - 0.5, v, 1, 0)

    ax.set_xlabel(xtitle)
    ax.set_ylabel("Votes")
    ax.set_title(title)

    ax.set_xlim(_min - 0.5, _max + 0.5)
    ax.set_ylim(0, max(data.values()))
    ax.grid(True)

    plt.savefig(filename, dpi=80)
    plt.clf()



def save_stats(prefix, filename):
    p = subprocess.Popen(["ardj", "dump-votes", prefix], stdout=subprocess.PIPE)
    data = p.communicate()[0].strip() or None
    if data is not None:
        file(filename, "wb").write(data)

        png = filename.replace(".csv", "-daily.png")
        plot_data(png, data, "D", "Days", "Vote distribution, %s" % (prefix or "overall"))

        png = filename.replace(".csv", "-hourly.png")
        plot_data(png, data, "H", "Hours", "Vote distribution, %s" % (prefix or "overall"))


save_stats("", "votes.csv")

for year in range(2011, 3000):
    save_stats(str(year), "votes-%u.csv" % year)

    for month in range(1, 13):
        stamp = "%u-%02u" % (year, month)
        if stamp > now:
            exit(0)
        save_stats(stamp, "votes-%s.csv" % stamp)
