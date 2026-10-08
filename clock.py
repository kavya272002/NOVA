"""Clock abstraction.

The seed script moves this clock backwards so that sample campaigns are produced by the
*real* workflow functions with realistic historical timestamps. In normal use the clock
simply returns the current time.
"""
from datetime import datetime, timedelta

_override = None


def now():
    return _override or datetime.now()


def set_time(dt):
    global _override
    _override = dt


def clear():
    global _override
    _override = None


def ts(dt=None):
    return (dt or now()).strftime("%Y-%m-%d %H:%M:%S")


def today():
    return now().date()


def parse_ts(s):
    return datetime.strptime(s, "%Y-%m-%d %H:%M:%S")


def minutes_between(a, b):
    return (parse_ts(b) - parse_ts(a)).total_seconds() / 60.0
