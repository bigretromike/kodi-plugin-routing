# -*- coding: utf-8 -*-
#
# Copyright (C) 2014-2015 Thomas Amland
#
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with this program.  If not, see <http://www.gnu.org/licenses/>.

import re
import sys
try:
    from urlparse import urlsplit, parse_qs
except ImportError:
    from urllib.parse import urlsplit, parse_qs
try:
    from urllib import urlencode
except ImportError:
    from urllib.parse import urlencode

try:
    import xbmc
    import xbmcaddon
    _addon_id = xbmcaddon.Addon().getAddonInfo('id')

    def log(msg):
        msg = "[%s][routing] %s" % (_addon_id, msg)
        xbmc.log(msg, level=xbmc.LOGDEBUG)
except ImportError:
    def log(msg):
        print(msg)


class RoutingError(Exception):
    pass


class Addon(object):
    """
    The base class for routing.Plugin, Script, and any others that may be added
    :ivar args: The parsed query string.
    :type args: dict of byte strings

    :ivar base_url: the base_url of the addon, ex. plugin://plugin.video.something_plugin
    :type base_url: str

    :ivar convert_args: Convert arguments to basic types
    :type convert_args: bool
    """

    def __init__(self, base_url=None, convert_args=False):
        self._rules = {}  # function to list of rules
        self.args = {}
        self.base_url = base_url
        self.convert_args = convert_args
        if self.base_url is None:
            self.base_url = xbmcaddon.Addon().getAddonInfo('id')

    def route_for(self, path):
        """
        Returns the view function for path.

        :type path: byte string.
        """
        if path.startswith(self.base_url):
            path = path.split(self.base_url, 1)[1]

        # first, search for exact matches
        for view_fun, rules in iter(self._rules.items()):
            for rule in rules:
                if rule.exact_match(path):
                    return view_fun

        # then, search for regex matches
        for view_fun, rules in iter(self._rules.items()):
            for rule in rules:
                if rule.match(path) is not None:
                    return view_fun
        return None

    def url_for(self, func, *args, **kwargs):
        """
        Construct and returns an URL for view function with give arguments.
        """
        if func in self._rules:
            for rule in self._rules[func]:
                path = rule.make_path(*args, **kwargs)
                if path is not None:
                    return self.url_for_path(path)
        raise RoutingError("No known paths to '{0}' with args {1} and "
                           "kwargs {2}".format(func.__name__, args, kwargs))

    def url_for_path(self, path):
        """
        Returns the complete URL for a path.
        """
        path = path if path.startswith('/') else '/' + path
        return self.base_url + path

    def route(self, pattern):
        """ Register a route. """
        def decorator(func):
            self.add_route(func, pattern)
            return func
        return decorator

    def add_route(self, func, pattern):
        """ Register a route. """
        rule = UrlRule(pattern)
        if func not in self._rules:
            self._rules[func] = []
        self._rules[func].append(rule)

    def run(self, argv=sys.argv):
        if len(argv) > 2:
            self.args = parse_qs(argv[2].lstrip('?'))
        path = urlsplit(argv[0]).path or '/'
        self._dispatch(path)

    def redirect(self, path):
        self._dispatch(path)

    def _dispatch(self, path):
        for view_func, rules in iter(self._rules.items()):
            for rule in rules:
                if not rule.exact_match(path):
                    continue
                log("Dispatching to '%s', exact match" % view_func.__name__)
                view_func()
                return

        # then, search for regex matches
        for view_func, rules in iter(self._rules.items()):
            for rule in rules:
                kwargs = rule.match(path)
                if kwargs is None:
                    continue
                if self.convert_args:
                    for k, v in kwargs.items():
                        new_val = try_convert(v)
                        if new_val:
                            kwargs[k] = new_val
                log("Dispatching to '%s', args: %s" % (view_func.__name__, kwargs))
                view_func(**kwargs)
                return
        raise RoutingError('No route to path "%s"' % path)


class Plugin(Addon):
    """
    A routing handler bound to a kodi plugin
    :ivar handle: The plugin handle from kodi
    :type handle: int
    """

    def __init__(self, base_url=None, convert_args=False):
        self.base_url = base_url
        if self.base_url is None:
            self.base_url = "plugin://" + xbmcaddon.Addon().getAddonInfo('id')
        Addon.__init__(self, self.base_url, convert_args)
        if len(sys.argv) < 2:
            # we are probably not dealing with a plugin, or it was called incorrectly from an addon
            raise TypeError('There was no handle provided. This needs to be called from a Kodi Plugin.')
        self.handle = int(sys.argv[1]) if sys.argv[1].isdigit() else -1


class Script(Addon):
    """
    A routing handler bound to a kodi script
    """

    def __init__(self, base_url=None, convert_args=False):
        Addon.__init__(self, base_url, convert_args)


class UrlRule(object):
    def __init__(self, pattern):
        arg_regex = re.compile('<([A-z][A-z0-9]*)>')
        self._has_args = bool(arg_regex.search(pattern))

        kw_pattern = r'<(?:[^:]+:)?([A-z][A-z0-9]*)>'
        self._pattern = re.sub(kw_pattern, '{\\1}', pattern)
        self._keywords = re.findall(kw_pattern, pattern)

        p = re.sub('<([A-z][A-z0-9]*)>', '<string:\\1>', pattern)
        p = re.sub('<string:([A-z][A-z0-9]*)>', '(?P<\\1>[^/]+?)', p)
        p = re.sub('<path:([A-z][A-z0-9]*)>', '(?P<\\1>.*)', p)
        self._compiled_pattern = p
        self._regex = re.compile('^' + p + '$')

    def match(self, path):
        """
        Check if path matches this rule. Returns a dictionary of the extracted
        arguments if match, otherwise None.
        """
        # match = self._regex.search(urlsplit(path).path)
        match = self._regex.search(path)
        return match.groupdict() if match else None

    def exact_match(self, path):
        return not self._has_args and self._pattern == path

    def make_path(self, *args, **kwargs):
        """Construct a path from arguments."""
        if args and kwargs:
            return None  # can't use both args and kwargs
        if args:
            # Replace the named groups %s and format
            try:
                return re.sub(r'{[A-z][A-z0-9]*}', r'%s', self._pattern) % args
            except TypeError:
                return None

        # We need to find the keys from kwargs that occur in our pattern.
        # Unknown keys are pushed to the query string.
        url_kwargs = dict(((k, v) for k, v in kwargs.items() if k in self._keywords))
        qs_kwargs = dict(((k, v) for k, v in kwargs.items() if k not in self._keywords))

        query = '?' + urlencode(qs_kwargs) if qs_kwargs else ''
        try:
            return self._pattern.format(**url_kwargs) + query
        except KeyError:
            return None

    def __str__(self):
        return b"Rule(pattern=%s, keywords=%s)" % (self._pattern, self._keywords)


def try_convert(value):
    """
    Try to convert to some common types
    :param value: the string to convert
    :type value: str
    """
    # for some of these, they are simplistic and not the generally preferred way
    # this is a special case, so I don't care

    # try to convert to int
    if all(x.isdigit() for x in value):
        return int(value)

    # try to convert to float. We've already check ints, so just try/except
    try:
        return float(value)
    except:
        pass

    # try to convert to bool
    if value.lower() == 'true':
        return True
    if value.lower() == 'false':
        return False

    return None
