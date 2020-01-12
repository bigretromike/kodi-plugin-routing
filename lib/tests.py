# -*- coding: utf-8 -*-
#
# Copyright (C) 2015 Thomas Amland
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

from __future__ import absolute_import, division, print_function, unicode_literals

import pytest
import mock
from routing import Plugin, Script, UrlRule, RoutingError


@pytest.fixture()
def plugin():
    return Plugin('plugin://py.test')


@pytest.fixture()
def plugin_convert():
    return Plugin('plugin://py.test', convert_args=True)


# Normally, we'd be testing both, but there's currently nothing that Script does and Plugin doesn't do
@pytest.fixture()
def script():
    return Script('script://py.test')


def test_match():
    assert UrlRule("/p/<foo>").match("/p/bar") == {'foo': 'bar'}


def test_make_path():
    rule = UrlRule("/p/<foo>/<bar>")
    assert rule.make_path(bar=2, foo=1) == "/p/1/2"
    assert rule.make_path(1, 2) == "/p/1/2"
    assert rule.make_path(baz=3, foo=1, bar=2) == "/p/1/2?baz=3"
    assert rule.make_path(1) is None


def test_make_path_should_urlencode_args(plugin):
    f = mock.create_autospec(lambda: None)
    plugin.route('/foo')(f)
    # we wanted double quote for the +, %, and any others that might be in the string
    assert plugin.url_for(f, bar='b a&r+c') == plugin.base_url + '/foo?bar=b+a%26r%2Bc'
    plugin.run(['plugin://py.test/foo', '0', '?bar=b+a%26r%2Bc'])
    f.assert_called_with()
    assert plugin.args['bar'] == ['b a&r+c']


def test_url_for_path():
    plugin = Plugin('plugin://foo.bar')
    assert plugin.url_for_path("/baz") == "plugin://foo.bar/baz"


def test_url_for(plugin):
    f = lambda: None
    plugin.route("/foo")(f)
    assert plugin.url_for(f) == plugin.base_url + "/foo"


def test_url_for_kwargs(plugin):
    f = lambda a, var_with_num_underscore2: None
    plugin.route("/foo/<a>/<var_with_num_underscore2>")(f)
    assert plugin.url_for(f, a=1, var_with_num_underscore2=2) == plugin.base_url + "/foo/1/2"


def test_url_for_args(plugin):
    f = lambda a, var_with_num_underscore2, c, d: None
    plugin.route("/<a>/<var_with_num_underscore2>/<c>/<d>")(f)
    assert plugin.url_for(f, 1, 2.6, True, 'baz') == plugin.base_url + "/1/2.6/True/baz"


def test_route_for(plugin):
    f = lambda: None
    plugin.route("/foo")(f)
    assert plugin.route_for(plugin.base_url + "/foo") is f


def test_route_for_args(plugin):
    f = lambda a, var_with_num_underscore2: None
    g = lambda: (None, None)  # just to make sure that they are easily different
    plugin.route("/foo/<a>/<var_with_num_underscore2>")(f)
    plugin.route("/foo/a/b")(g)

    assert plugin.route_for(plugin.base_url + "/foo/1/2") is f
    assert plugin.route_for(plugin.base_url + "/foo/a/b") is g


def test_path_query(plugin):
    # full test to ensure that a path is both created properly and preserved throughout
    url = 'http://foo.bar:80/baz/bax.json?foo=bar&baz=bay'
    f = mock.create_autospec(lambda a: None)

    plugin.route('/do/<path:a>')(f)
    path = plugin.url_for(f, url)
    assert plugin.route_for(path) is f
    plugin.run([path, '0', '?foo=bar&baz=bay'])
    f.assert_called_with(url)
    assert plugin.args['foo'][0] == 'bar' and plugin.args['baz'][0] == 'bay'


def test_dispatch(plugin):
    f = mock.create_autospec(lambda: None)
    plugin.route("/foo")(f)
    plugin.run(['plugin://py.test/foo', '0', '?bar=baz'])
    f.assert_called_with()
    assert plugin.args['bar'] == ['baz']


def test_path(plugin):
    f = mock.create_autospec(lambda: None)
    plugin.route("/foo")(f)
    plugin.run(['plugin://py.test/foo', '0'])
    assert plugin.path == '/foo'
    plugin.route("/foo/bar/baz")(f)
    plugin.run(['plugin://py.test/foo/bar/baz', '0'])
    assert plugin.path == '/foo/bar/baz'


def test_no_route(plugin):
    f = lambda a: None
    plugin.route("/foo/<a>/<b>")(f)
    with pytest.raises(RoutingError):
        plugin.url_for(f, 1)

    with pytest.raises(RoutingError):
        plugin.run([plugin.base_url + "/foo"])

    assert plugin.route_for(plugin.base_url + "/foo") is None


def test_arg_parsing(plugin):
    f = mock.create_autospec(lambda: None)
    plugin.route("/foo")(f)
    plugin.run(['plugin://py.test/foo', '0', '?bar=baz&bar2=baz2'])
    assert plugin.args['bar'][0] == 'baz' and plugin.args['bar2'][0] == 'baz2'


def test_trailing_slash_in_route_definition(plugin):
    """ Should call registered route with trailing slash. """
    f = mock.create_autospec(lambda: None)
    plugin.route("/foo/")(f)
    plugin.run(['plugin://py.test/foo', '0'])
    assert f.call_count == 1


def test_trailing_slashes_in_run(plugin):
    """ Should call registered route without trailing slash. """
    f = mock.create_autospec(lambda: None)
    plugin.route("/foo")(f)
    plugin.run(['plugin://py.test/foo/', '0'])
    assert f.call_count == 1


def test_trailing_slash_handling_for_root(plugin):
    f = mock.create_autospec(lambda: None)
    plugin.route("/<a>")(lambda: None)
    plugin.route("/")(f)
    plugin.run(['plugin://py.test/', '0'])
    plugin.run(['plugin://py.test', '0'])
    assert f.call_count == 2
    with pytest.raises(RoutingError):
        plugin.run(['plugin://py.test/a/b', '0'])


def test_arg_conversion(plugin_convert):
    f = mock.create_autospec(lambda a, b2, c, d: None)
    plugin_convert.route("/foo/<a>/<b2>/<c>/<d>")(f)
    plugin_convert.run(['plugin://py.test/foo/bar/true/16.4/9', '0', ''])
    f.assert_called_with('bar', True, 16.4, 9)
