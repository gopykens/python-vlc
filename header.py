#! /usr/bin/python

# Python ctypes bindings for VLC
#
# Copyright (C) 2009-2010 the VideoLAN team
# $Id: $
#
# Authors: Olivier Aubert <olivier.aubert at liris.cnrs.fr>
#
# This program is free software; you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation; either version 2 of the License, or
# (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with this program; if not, write to the Free Software
# Foundation, Inc., 51 Franklin Street, Fifth Floor, Boston MA 02110-1301, USA.

"""This module provides bindings for the LibVLC public API, see
U{http://wiki.videolan.org/LibVLC}.

You can find the documentation and a README file with some examples
at U{http://www.advene.org/download/python-ctypes/}.

Basically, the most important class is L{Instance}, which is used
to create a libvlc instance.  From this instance, you then create
L{MediaPlayer} and L{MediaListPlayer} instances.

Alternatively, you may create instances of the L{MediaPlayer} and
L{MediaListPlayer} class directly and an instance of L{Instance}
will be implicitly created.  The latter can be obtained using the
C{get_instance} method of L{MediaPlayer} and L{MediaListPlayer}.
"""

import ctypes
import os
import sys

# Used by EventManager in override.py
try:
    from inspect import getargspec
except ImportError:
    getargspec = None

build_date  = ''  # build time stamp and __version__, see generate.py

 # Used on win32 and MacOS in override.py
plugin_path = None

if sys.platform.startswith('linux'):
    try:
        dll = ctypes.CDLL('libvlc.so')
    except OSError:  # may fail
        dll = ctypes.CDLL('libvlc.so.5')

elif sys.platform.startswith('win'):
    import ctypes.util as u
    p = u.find_library('libvlc.dll') 
    if p is None:
        try:  # some registry settings
            import _winreg as w  # leaner than win32api, win32con
            for r in w.HKEY_LOCAL_MACHINE, w.HKEY_CURRENT_USER:
                try:
                    r = w.OpenKey(r, 'Software\\VideoLAN\\VLC')
                    plugin_path, _ = w.QueryValueEx(r, 'InstallDir')
                    w.CloseKey(r)
                    break
                except w.error:
                    pass
            del r, w
        except ImportError:  # no PyWin32
            pass
        if plugin_path is None:
             # try some standard locations.
            for p in ('Program Files\\VideoLan\\', 'VideoLan\\',
                      'Program Files\\',           ''):
                p = 'C:\\' + p + 'VLC\\libvlc.dll'
                if os.path.exists(p):
                    plugin_path = os.path.dirname(p)
                    break
        if plugin_path is not None:  # try loading
            p = os.getcwd()
            os.chdir(plugin_path)
             # if chdir failed, this will raise an exception
            dll = ctypes.CDLL('libvlc.dll')
             # restore cwd after dll has been loaded
            os.chdir(p)
        else:  # may fail
            dll = ctypes.CDLL('libvlc.dll')
    else:
        plugin_path = os.path.dirname(p)
        dll = ctypes.CDLL(p)
    del p, u

elif sys.platform.startswith('darwin'):
    # FIXME: should find a means to configure path
    d = '/Applications/VLC.app/Contents/MacOS/'
    p = d + 'lib/libvlc.dylib'
    if os.path.exists(p):
        dll = ctypes.CDLL(p)
        d += 'modules'
        if os.path.isdir(d):
            plugin_path = d
    else:  # hope, some PATH is set...
        dll = ctypes.CDLL('libvlc.dylib')
    del d, p

else:
    raise NotImplementedError('%s: %s not supported' % (sys.argv[0], sys.platform))

#
# Generated enum types.
#

# GENERATED_ENUMS

#
# End of generated enum types.
#

class ListPOINTER(object):
    '''Just like a POINTER but accept a list of ctype as an argument.
    '''
    def __init__(self, etype):
        self.etype = etype

    def from_param(self, param):
        if isinstance(param, (list, tuple)):
            return (self.etype * len(param))(*param)

class LibVLCException(Exception):
    """Python exception raised by libvlc methods.
    """
    pass

# From libvlc_structures.h

class MediaStats(ctypes.Structure):
    _fields_= [
                ('read_bytes',          ctypes.c_int  ),
                ('input_bitrate',       ctypes.c_float),
                ('demux_read_bytes',    ctypes.c_int  ),
                ('demux_bitrate',       ctypes.c_float),
                ('demux_corrupted',     ctypes.c_int  ),
                ('demux_discontinuity', ctypes.c_int  ),
                ('decoded_video',       ctypes.c_int  ),
                ('decoded_audio',       ctypes.c_int  ),
                ('displayed_pictures',  ctypes.c_int  ),
                ('lost_pictures',       ctypes.c_int  ),
                ('played_abuffers',     ctypes.c_int  ),
                ('lost_abuffers',       ctypes.c_int  ),
                ('sent_packets',        ctypes.c_int  ),
                ('sent_bytes',          ctypes.c_int  ),
                ('send_bitrate',        ctypes.c_float),
                ]

    def __str__(self):
        return "\n".join( [ self.__class__.__name__ ]
                          + [" %s:\t%s" % (n, getattr(self, n)) for n in self._fields_] )

class MediaTrackInfo(ctypes.Structure):
    _fields_= [
        ('codec'   , ctypes.c_uint32),
        ('id'      , ctypes.c_int),
        ('type'    , TrackType),
        ('profile' , ctypes.c_int),
        ('level'   , ctypes.c_int),
        ('channels_or_height',  ctypes.c_uint),
        ('rate_or_width'    , ctypes.c_uint),
        ]

    def __str__(self):
        return "\n".join( [self.__class__.__name__]
                          + [" %s:\t%s" % (n, getattr(self, n)) for n in self._fields_])

class PlaylistItem(ctypes.Structure):
    _fields_= [
                ('id', ctypes.c_int),
                ('uri', ctypes.c_char_p),
                ('name', ctypes.c_char_p),
                ]

    def __str__(self):
        return "%s #%d %s (uri %s)" % (self.__class__.__name__, self.id, self.name, self.uri)

class LogMessage(ctypes.Structure):
    _fields_= [
                ('size', ctypes.c_uint),
                ('severity', ctypes.c_int),
                ('type', ctypes.c_char_p),
                ('name', ctypes.c_char_p),
                ('header', ctypes.c_char_p),
                ('message', ctypes.c_char_p),
                ]

    def __init__(self):
        super(LogMessage, self).__init__()
        self.size=ctypes.sizeof(self)

    def __str__(self):
        return "%s(%d:%s): %s" % (self.__class__.__name__, self.severity, self.type, self.message)


class AudioOutput(ctypes.Structure):
    def __str__(self):
        return "%s(%s:%s)" % (self.__class__.__name__, self.name, self.description)
AudioOutput._fields_= [
    ('name', ctypes.c_char_p),
    ('description', ctypes.c_char_p),
    ('next', ctypes.POINTER(AudioOutput)),
    ]

class TrackDescription(ctypes.Structure):
    def __str__(self):
        return "%s(%d:%s)" % (self.__class__.__name__, self.id, self.name)
TrackDescription._fields_= [
    ('id', ctypes.c_int),
    ('name', ctypes.c_char_p),
    ('next', ctypes.POINTER(TrackDescription)),
    ]
def track_description_list(head):
    """Convert a TrackDescription linked list to a python list, and release the linked list.
    """
    l = []
    if head:
        item = head
        while item:
            l.append( (item.contents.id, item.contents.name) )
            item = item.contents.next
        libvlc_track_description_release(head)
    return l

class MediaEvent(ctypes.Structure):
    _fields_ = [
        ('media_name', ctypes.c_char_p),
        ('instance_name', ctypes.c_char_p),
        ]

class EventUnion(ctypes.Union):
    _fields_ = [
        ('meta_type', ctypes.c_uint),
        ('new_child', ctypes.c_uint),
        ('new_duration', ctypes.c_longlong),
        ('new_status', ctypes.c_int),
        ('media', ctypes.c_void_p),
        ('new_state', ctypes.c_uint),
        # Media instance
        ('new_position', ctypes.c_float),
        ('new_time', ctypes.c_longlong),
        ('new_title', ctypes.c_int),
        ('new_seekable', ctypes.c_longlong),
        ('new_pausable', ctypes.c_longlong),
        # FIXME: Skipped MediaList and MediaListView...
        ('filename', ctypes.c_char_p),
        ('new_length', ctypes.c_longlong),
        ('media_event', MediaEvent),
        ]

class Event(ctypes.Structure):
    _fields_ = [
        ('type', EventType),
        ('object', ctypes.c_void_p),
        ('u', EventUnion),
        ]

class Rectangle(ctypes.Structure):
    _fields_ = [
        ('top',    ctypes.c_int),
        ('left',   ctypes.c_int),
        ('bottom', ctypes.c_int),
        ('right',  ctypes.c_int),
        ]

class Position(object):
    """Enum-like, position constants for VideoMarqueePosition option.
    """
    Center=0
    Left=1
    CenterLeft=1
    Right=2
    CenterRight=2
    Top=4
    TopCenter=4
    TopLeft=5
    TopRight=6
    Bottom=8
    BottomCenter=8
    BottomLeft=9
    BottomRight=10

    def __init__(self):
        raise TypeError('Constants only')

### End of header.py ###
