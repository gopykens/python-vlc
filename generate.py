#! /usr/bin/python
debug=False

#
# Code generator for python ctypes bindings for VLC
# Copyright (C) 2009 the VideoLAN team
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
#

"""This module parses VLC public API include files and generates
corresponding python/ctypes code. Moreover, it generates class
wrappers for most methods.
"""

import sys
import os
import re
import time
import operator
import itertools
from optparse import OptionParser

# Methods not decorated/not referenced
blacklist=[
    "libvlc_set_exit_handler",
    "libvlc_video_set_callbacks",
    ]

# Precompiled regexps
api_re=re.compile('VLC_PUBLIC_API\s+(\S+\s+.+?)\s*\(\s*(.+?)\s*\)')
param_re=re.compile('\s*(const\s*|unsigned\s*|struct\s*)?(\S+\s*\**)\s+(.+)')
paramlist_re=re.compile('\s*,\s*')
comment_re=re.compile('\\param\s+(\S+)')
python_param_re=re.compile('(@param\s+\S+)(.+)')
forward_re=re.compile('.+\(\s*(.+?)\s*\)(\s*\S+)')
enum_re=re.compile('(?:typedef\s+)?(enum)\s*(\S+)\s*\{\s*(.+)\s*\}\s*(?:\S+)?;')


# Parameter direction definitions.
class Flag(object):
    """Enum-like, parameter direction flag constants.
    """
    In = 1     # input only
    Out = 2    # output only
    InOut = 3  # in- and output
    InZero = 4 # input, default int 0
    def __init__(self):
        raise TypeError('Constants only')

# Parameter passing flags for types.  This shouldn't
# be hardcoded this way, but works all right ATM.
def paramFlag3(typ):
    # return the parameter flags as 1-, 2- or 3-tuple for the
    # given type and optional parameter name and default value
    t=( { 'int*':                Flag.Out,  # _video_get_cursor
          'unsigned*':           Flag.Out,  # _video_get_size
          'libvlc_exception_t*': Flag.InOut,
          }.get(typ, Flag.In), )
    return t


class Parser(object):
    def __init__(self, list_of_files):
        self.methods=[]
        self.enums=[]

        for name in list_of_files:
            self.enums.extend(self.parse_typedef(name))
            self.methods.extend(self.parse_include(name))

    def parse_param(self, s):
        """Parse a C parameter expression.

        It is used to parse both the type/name for methods, and type/name
        for their parameters.

        It returns a tuple (type, name).
        """
        s=s.strip()
        s=s.replace('const', '')
        if 'VLC_FORWARD' in s:
            m=forward_re.match(s)
            s=m.group(1)+m.group(2)
        m=param_re.search(s)
        if m:
            const, typ, name=m.groups()
            while name.startswith('*'):
                typ += '*'
                name=name[1:]
            if name == 'const*':
                # K&R definition: const char * const*
                name=''
            typ=typ.replace(' ', '')
            return typ, name
        else:
            # K&R definition: only type
            return s.replace(' ', ''), ''

    def parse_typedef(self, name):
        """Parse include file for typedef expressions.

        This generates a tuple for each typedef:
        (type, name, value_list, comment)
        with type == 'enum' (for the moment) and value_list being a list of (name, value)
        Note that values are string, since this is intended for code generation.
        """
        f=open(name, 'r')
        accumulator=''
        comment=""
        simple_comment=None
        for l in f:
            # Note: lstrip() should not be necessary, but there is 1 badly
            # formatted comment in vlc1.0.0 includes
            if l.lstrip().startswith('/**'):
                comment = l[3:]
                continue
            elif l.startswith(' * '):
                comment = comment + l[3:]
                continue

            l=l.strip()

            if l.startswith('/*'):
                # Simple comment start
                if l.endswith('*/'):
                    simple_comment = None
                else:
                    simple_comment = l[2:]
                continue
            elif simple_comment is not None:
                # We are in a comment
                if l.endswith('*/'):
                    simple_comment = None
                else:
                    simple_comment += l
                continue

            if re.match('^(?:typedef\s+)?enum', l) and not l.endswith(';'):
                # Multiline definition. Accumulate until end of definition
                accumulator=l
                continue
            elif accumulator:
                # Strip possible trailing comments
                if '/*' in l:
                    l = l[:l.index('/*')]
                accumulator=" ".join( (accumulator, l) )
                if l.endswith(';'):
                    # End of definition
                    l=accumulator
                    accumulator=''
                else:
                    continue

            m=enum_re.match(l)
            if m:
                values=[]
                (typ, name, data)=m.groups()
                val=0
                for l in paramlist_re.split(data):
                    l=l.strip()
                    if l.startswith('/*'):
                        continue
                    if '=' in l:
                        # A value was specified. Use it.
                        n, v = re.split('\s*=\s*', l)
                        values.append( (n, v) )
                        if v.startswith("0x"):
                            val=int(v, 16)
                        else:
                            val=int(v)
                    else:
                        if l:
                            values.append( (l, str(val)) )
                    val = val + 1
                if name is None:
                    # Anonymous enum. Use a dummy name.
                    name="libvlc_enum_t"
                else:
                    name=name.strip()

                # Clean up comment text
                if comment.endswith('*/'):
                    comment = comment[:-2]
                comment = comment.strip()
                if comment:
                    comment = comment.capitalize().rstrip('.') + '.'

                yield (typ, name, values, comment)
                comment=""
        f.close()

    def parse_include(self, name):
        """Parse include file.

        This generates a tuple for each function:
        (return_type, method_name, parameter_list, comment)
        with parameter_list being a list of tuples (parameter_type, parameter_name).
        """
        f=open(name, 'r')
        accumulator=''
        comment=''
        for l in f:
            # Note: lstrip() should not be necessary, but there is 1 badly
            # formatted comment in vlc1.0.0 includes
            if l.lstrip().startswith('/**'):
                comment=''
                continue
            elif l.startswith(' * '):
                comment += l[3:]
                continue

            l=l.strip()

            if accumulator:
                accumulator=" ".join( (accumulator, l) )
                if l.endswith(');'):
                    # End of definition
                    l=accumulator
                    accumulator=''
            elif l.startswith('VLC_PUBLIC_API') and not l.endswith(');'):
                # Multiline definition. Accumulate until end of definition
                accumulator=l
                continue

            m=api_re.match(l)
            if m:
                (ret, param)=m.groups()

                rtype, method=self.parse_param(ret)

                params=[]
                for p in paramlist_re.split(param):
                    params.append( self.parse_param(p) )

                if len(params) == 1 and params[0][0] == 'void':
                    # Empty parameter list
                    params=[]

                if list(p for p in params if not p[1]):
                    # Empty parameter names. Have to poke into comment.
                    names=comment_re.findall(comment)
                    if len(names) < len(params):
                        # Bad description: all parameters are not specified.
                        # Generate default parameter names
                        badnames=[ "param%d" % i for i in xrange(len(params)) ]
                        # Put in the existing ones
                        for (i, p) in enumerate(names):
                            badnames[i]=names[i]
                        names=badnames
                        print "### Error ###"
                        print "### Cannot get parameter names from comment for %s: %s" % (method, comment.replace("\n", ' '))
                        # Note: this was previously
                        # raise Exception("Cannot get parameter names from comment for %s: %s" % (method, comment))
                        # but it prevented code generation for a minor detail (some bad descriptions).
                    params=[ (p[0], names[i]) for (i, p) in enumerate(params) ]

                if debug:
                    print '********************'
                    print l
                    print '-------->'
                    print "%s (%s)" % (method, rtype)
                    for typ, name in params:
                        print "        %s (%s)" % (name, typ)
                    print '********************'
                yield (rtype,
                       method,
                       params,
                       comment)
                comment=''
        f.close()

    def dump_methods(self):
        print "** Defined functions **"
        for (rtype, name, params, comment) in self.methods:
            print "%(name)s (%(rtype)s):" % locals()
            for t, n in params:
                print "    %(n)s (%(t)s)" % locals()

    def dump_enums(self):
        print "** Defined enums **"
        for (typ, name, values, comment) in self.enums:
            print "%(name)s (%(typ)s):" % locals()
            for k, v in values:
                print "    %(k)s=%(v)s" % locals()

class PythonGenerator(object):
    # C-type to ctypes/python type conversion.
    # Note that enum types conversions are generated (cf convert_enum_names)
    type2class={
        'libvlc_media_player_t*': 'MediaPlayer',
        'libvlc_instance_t*': 'Instance',
        'libvlc_media_t*': 'Media',
        'libvlc_log_t*': 'Log',
        'libvlc_log_iterator_t*': 'LogIterator',
        'libvlc_log_message_t*': 'ctypes.POINTER(LogMessage)',
        'libvlc_event_type_t': 'ctypes.c_uint',
        'libvlc_event_manager_t*': 'EventManager',
        'libvlc_media_discoverer_t*': 'MediaDiscoverer',
        'libvlc_media_library_t*': 'MediaLibrary',
        'libvlc_media_list_t*': 'MediaList',
        'libvlc_media_list_player_t*': 'MediaListPlayer',
        'libvlc_media_list_view_t*': 'MediaListView',
        'libvlc_track_description_t*': 'ctypes.POINTER(TrackDescription)',
        'libvlc_audio_output_t*': 'ctypes.POINTER(AudioOutput)',
        'libvlc_media_stats_t*': 'ctypes.POINTER(MediaStats)',
        'libvlc_media_track_info_t**': 'ctypes.POINTER(ctypes.POINTER(MediaTrackInfo))',

        'libvlc_drawable_t': 'ctypes.c_uint',  # FIXME?
        'libvlc_rectangle_t*': 'ctypes.POINTER(Rectangle)',  # FIXME?

        'WINDOWHANDLE': 'ctypes.c_ulong',

        'void': 'None',
        'void*': 'ctypes.c_void_p',
        'short': 'ctypes.c_short',
        'char*': 'ctypes.c_char_p',
        'char**': 'ListPOINTER(ctypes.c_char_p)',
        'uint32_t': 'ctypes.c_uint32',
        'int64_t': 'ctypes.c_int64',
        'float': 'ctypes.c_float',
        'unsigned': 'ctypes.c_uint',
        'unsigned*': 'ctypes.POINTER(ctypes.c_uint)',  # _video_get_size
        'int': 'ctypes.c_int',
        'int*': 'ctypes.POINTER(ctypes.c_int)',  # _video_get_cursor
        '...': 'FIXME_va_list',
        'libvlc_callback_t': 'ctypes.c_void_p',
        'libvlc_time_t': 'ctypes.c_longlong',
        }

    # Defined python classes, i.e. classes for which we want to generate
    # class wrappers around libvlc functions
    defined_classes=(
        'MediaPlayer',
        'Instance',
        'Media',
        'Log',
        'LogIterator',
        'EventManager',
        'MediaDiscoverer',
        'MediaLibrary',
        'MediaList',
        'MediaListPlayer',
        'MediaListView',
        )

    def __init__(self, parser=None):
        self.parser=parser

        # Generate python names for enums
        self.type2class.update(self.convert_enum_names(parser.enums))
        self.check_types()

        # Definition of prefixes that we can strip from method names when
        # wrapping them into class methods
        self.prefixes=dict( (v, k[:-2])
                            for (k, v) in self.type2class.iteritems()
                            if  v in self.defined_classes )

    def save(self, filename=None):
        if filename is None or filename == '-':
            self.fd=sys.stdout
        else:
            self.fd=open(filename, 'w')

        self.insert_code('header.py')
        wrapped_methods=self.generate_wrappers(self.parser.methods)  # set
        unwrapped_methods=[]
        for l in self.parser.methods:
            self.output_ctypes(*l)
            m = l[1] # is method wrapped?
            if m not in wrapped_methods:
                unwrapped_methods.append("#  " + m)
        self.insert_code('footer.py')

        if unwrapped_methods:
            self.output("# %d methods not wrapped :" % len(unwrapped_methods))
            self.output("\n".join(sorted(unwrapped_methods)))

        if self.fd != sys.stdout:
            self.fd.close()

    def output(self, *p):
        self.fd.write(" ".join(p))
        self.fd.write("\n")

    def check_types(self):
        """Make sure that all types are properly translated.

        This method must be called *after* convert_enum_names, since
        the latter populates type2class with converted enum names.
        """
        for (rt, met, params, c) in self.parser.methods:
            for typ, name in params:
                if not typ in self.type2class:
                    raise Exception("No conversion for %s (from %s:%s)" % (typ, met, name))

    def insert_code(self, filename):
        """Generate header/footer code.
        """
        f=open(filename, 'r')
        for l in f:
            if l.startswith('build_date'):
                self.output('build_date="%s"' % time.ctime())
            elif l.startswith('# GENERATED_ENUMS'):
                self.generate_enums(self.parser.enums)
            else:
                self.output(l.rstrip())

        f.close()

    def convert_enum_names(self, enums):
        res={}
        for (typ, name, values, comment) in enums:
            if typ != 'enum':
                raise Exception('This method only handles enums')
            pyname=re.findall('libvlc_(.+?)(_t)?$', name)[0][0]
            if name == 'libvlc_event_e':
                pyname='EventType'
            elif '_' in pyname:
                pyname=pyname.title().replace('_', '')
            elif not pyname[0].isupper():
                pyname=pyname.capitalize()
            res[name]=pyname
        return res

    def generate_enums(self, enums):
        self.output("""
class _Enum(ctypes.c_ulong):
    '''Base class
    '''
    _names={}

    def __str__(self):
        n=self._names.get(self.value, '') or ('FIXME_(%r)' % (self.value,))
        return '.'.join((self.__class__.__name__, n))

    def __repr__(self):
        return '.'.join((self.__class__.__module__, self.__str__()))

    def __eq__(self, other):
        return ( (isinstance(other, _Enum)       and self.value == other.value)
              or (isinstance(other, (int, long)) and self.value == other) )

    def __ne__(self, other):
        return not self.__eq__(other)
""")
        for (typ, name, values, comment) in enums:
            if typ != 'enum':
                raise Exception('This method only handles enums')

            pyname = self.type2class[name]

            self.output("class %s(_Enum):" % pyname)
            self.output('    """%s\n    """' % comment)

            self.output("    _names={")
            l = []
            # Convert symbol names
            for k, v in values:
                k = k.split('_')
                n = k[-1]
                if len(n) <= 1:  # Single character name
                    n = '_'.join( k[-2:] )  # Some use 1_1, 5_1, etc.
                if n[0].isdigit(): # Cannot start with a number
                    n = '_' + n
                self.output("        %s: '%s'," % (v, n))
                l.append("%(class)s.%(attribute)s=%(class)s(%(value)s)" % {
                        'class': pyname,
                        'attribute': n,
                        'value': v,
                        })
            self.output("    }")
            self.output("\n".join(sorted(l)))
            self.output("")

    def output_ctypes(self, rtype, method, params, comment):
        """Output ctypes decorator for the given method.
        """
        if method in blacklist:
            # FIXME
            return

         # return value and arg types
        args = ", ".join( [self.type2class.get(rtype, 'FIXME_%s' % (rtype,))]
                          + [self.type2class[p[0]] for p in params] )

         # tuple of arg flag tuples
        flags = ", ".join( str(paramFlag3(p[0])) for p in params )
        if flags:
            flags += ','

        comment = self.epydoc_comment(comment)

        self.output('''if hasattr(dll, '%(method)s'):
    p = ctypes.CFUNCTYPE(%(args)s)
    f = (%(flags)s)
    %(method)s = p( ('%(method)s', dll), f )
    %(method)s.__doc__ = """%(comment)s
"""
''' % locals())

    def parse_override(self, name):
        """Parse override definitions file.

        It is possible to override methods definitions in classes.

        It returns a tuple
        (code, overriden_methods, docstring)
        """
        code={}

        data=[]
        current=None
        f=open(name, 'r')
        for l in f:
            m=re.match('class (\S+):', l)
            if m:
                # Dump old data
                if current is not None:
                    code[current]="".join(data)
                current=m.group(1)
                data=[]
                continue
            data.append(l)
        code[current]="".join(data)
        f.close()

        docstring={}
        for k, v in code.iteritems():
            if v.lstrip().startswith('"""'):
                # Starting comment. Use it as docstring.
                dummy, docstring[k], code[k]=v.split('"""', 2)

        # Not robust wrt. internal methods, but this works for the moment.
        overridden_methods=dict( (k, re.findall('^\s+def\s+(\w+)', v, re.MULTILINE)) for (k, v) in code.iteritems() )

        return code, overridden_methods, docstring

    def epydoc_comment(self, comment, fix_first=False):
        """Transform Doxygen into epydoc syntax and fix first parameter.
        """
        lines=comment.replace('@{', '').replace('\\ingroup', '') \
                     .replace('@see', 'See').replace('\\see', 'See') \
                     .replace('\\note', 'NOTE:').replace('\\warning', 'WARNING:') \
                     .replace('\\param', '@param').replace('\\return', '@return') \
                     .strip().splitlines()

        doc = [ l for l in lines if '@param' not in l and '@return' not in l ]
        ret = [ l.replace('@return', '@return:') for l in lines if '@return' in l ]

        params = [ python_param_re.sub('\\1:\\2', l) for l in lines if '@param' in l and not '[OUT]' in l ]
        outparams = [ python_param_re.findall(l)[0][0] for l in lines if '@param' in l and '[OUT]' in l ]
        if outparams:
            # Replace the @return line
            ret = [ '@return %s' % ", ".join(p.strip("@param ") for p in outparams) ]
        
        if fix_first and params:  # remove (self)
            params = params[1:]

        return "\n".join( doc + params + ret )

    def generate_wrappers(self, methods):
        """Generate class wrappers for all appropriate methods.

        @return: the set of wrapped method names
        """
        ret=set()
        # Sort methods against the element they apply to.
        elements=sorted( ( (self.type2class.get(params[0][0]), rt, met, params, c)
                           for (rt, met, params, c) in methods
                           if params and self.type2class.get(params[0][0], '_') in self.defined_classes
                           ),
                         key=operator.itemgetter(0))

        overrides, overriden_methods, docstring=self.parse_override('override.py')

        for classname, el in itertools.groupby(elements, key=operator.itemgetter(0)):
            self.output('class %s(object):' % classname)
            if classname in docstring:
                self.output('    """%s\n    """' % docstring[classname].strip())

            if not 'def __new__' in overrides.get(classname, ''):
                self.output("""
    def __new__(cls, pointer=None):
        '''Internal method used for instanciating wrappers from ctypes.
        '''
        if pointer is None:
            raise Exception("Internal method. Surely this class cannot be instanciated by itself.")
        if pointer == 0:
            return None
        o=object.__new__(cls)
        o._as_parameter_=ctypes.c_void_p(pointer)
        return o
""")

            self.output("""
    @staticmethod
    def from_param(arg):
        '''(INTERNAL) ctypes parameter conversion method.
        '''
        return arg._as_parameter_
""")

            if classname in overrides:
                self.output(overrides[classname])

            prefix = self.prefixes.get(classname, '')

            for cl, rtype, method, params, comment in el:
                if method in blacklist:
                    continue
                # Strip prefix
                name = method.replace(prefix, '').replace('libvlc_', '')
                ret.add(method)
                if name in overriden_methods.get(cl, []):
                    # Method already defined in override.py
                    continue

                if params:
                    params[0] = (params[0][0], 'self')
                args = ", ".join( p[1] for p in params if paramFlag3(p[0])[0] != Flag.Out )

                comment = self.epydoc_comment(comment, fix_first=True)

                self.output('''    if hasattr(dll, '%(method)s'):
        def %(name)s(%(args)s):
            """%(comment)s
            """
            return %(method)s(%(args)s)
''' % locals())

                # Check for standard methods
                if name == 'count':
                    # There is a count method. Generate a __len__ one.
                    self.output("""    def __len__(self):
        return %s(self)
""" % method)
                elif name.endswith('item_at_index'):
                    # Indexable (and thus iterable)"
                    self.output("""    def __getitem__(self, i):
        return %s(self, i)

    def __iter__(self):
        for i in xrange(len(self)):
            yield self[i]
""" % method)
        return ret

class JavaGenerator(object):
    # C-type to java/jna type conversion.
    # Note that enum types conversions are generated (cf convert_enum_names)
    type2class={
        'libvlc_media_player_t*': 'LibVlcMediaPlayer',
        'libvlc_instance_t*': 'LibVlcInstance',
        'libvlc_media_t*': 'LibVlcMedia',
        'libvlc_log_t*': 'LibVlcLog',
        'libvlc_log_iterator_t*': 'LibVlcLogIterator',
        'libvlc_log_message_t*': 'libvlc_log_message_t',
        'libvlc_event_type_t': 'int',
        'libvlc_event_manager_t*': 'LibVlcEventManager',
        'libvlc_media_discoverer_t*': 'LibVlcMediaDiscoverer',
        'libvlc_media_library_t*': 'LibVlcMediaLibrary',
        'libvlc_media_list_t*': 'LibVlcMediaList',
        'libvlc_media_list_player_t*': 'LibVlcMediaListPlayer',
        'libvlc_media_list_view_t*': 'LibVlcMediaListView',
        'libvlc_media_stats_t*': 'LibVlcMediaStats',
        'libvlc_media_track_info_t**': 'LibVlcMediaTrackInfo',

        'libvlc_track_description_t*': 'LibVlcTrackDescription',
        'libvlc_audio_output_t*': 'LibVlcAudioOutput',

        'void': 'void',
        'void*': 'Pointer',
        'short': 'short',
        'char*': 'String',
        'char**': 'String[]',
        'uint32_t': 'uint32',
        'float': 'float',
        'unsigned': 'int',
        'unsigned*': 'Pointer',
        'int': 'int',
        'int*': 'Pointer',
        '...': 'FIXMEva_list',
        'libvlc_callback_t': 'LibVlcCallback',
        'libvlc_time_t': 'long',

        }

    def __init__(self, parser=None):
        self.parser=parser

        # Generate Java names for enums
        self.type2class.update(self.convert_enum_names(parser.enums))
        self.check_types()

    def save(self, dirname=None):
        if dirname is None or dirname == '-':
            dirname='internal'
            if not os.path.isdir(dirname):
                os.mkdir(dirname)

        print "Generating java code in %s/" % dirname

        # Generate enum files
        self.generate_enums(dirname, self.parser.enums)

        # Generate LibVlc.java code
        self.generate_libvlc(dirname)

    def output(self, fd, *p):
        fd.write(" ".join(p))
        fd.write("\n")

    def check_types(self):
        """Make sure that all types are properly translated.

        This method must be called *after* convert_enum_names, since
        the latter populates type2class with converted enum names.
        """
        for (rt, met, params, c) in self.parser.methods:
            if met in blacklist:
                continue
            for typ, name in params:
                if not typ in self.type2class:
                    raise Exception("No conversion for %s (from %s:%s)" % (typ, met, name))

    def convert_enum_names(self, enums):
        """Convert enum names into Java names.
        """
        res={}
        for (typ, name, values, comment) in enums:
            if typ != 'enum':
                raise Exception('This method only handles enums')
            pyname=re.findall('libvlc_(.+?)(_[te])?$', name)[0][0]
            if '_' in pyname:
                pyname=pyname.title().replace('_', '')
            elif not pyname[0].isupper():
                pyname=pyname.capitalize()
            res[name]=pyname
        return res

    def insert_code(self, fd, filename):
        """Generate header/footer code.
        """
        f=open(filename, 'r')
        for l in f:
            if l.startswith('build_date'):
                self.output(fd, 'build_date="%s";' % time.ctime())
            else:
                self.output(fd, l.rstrip())
        f.close()

    def generate_header(self, fd):
        """Generate LibVlc header.
        """
        for (c_type, jna_type) in self.type2class.iteritems():
            if c_type.endswith('*') and jna_type.startswith('LibVlc'):
                self.output(fd, '''    public class %s extends PointerType
    {
    }
''' % jna_type)

    def generate_libvlc(self, dirname):
        """Generate LibVlc.java JNA glue code.
        """
        filename=os.path.join(dirname, 'LibVlc.java')
        fd=open(filename, 'w')

        self.insert_code(fd, 'boilerplate.java')
        self.insert_code(fd, 'LibVlc-header.java')
        #wrapped_methods=self.generate_wrappers(self.parser.methods)
        self.generate_header(fd)
        for (rtype, method, params, comment) in self.parser.methods:
            if method in blacklist:
                # FIXME
                continue
            self.output(fd, "%s %s(%s);\n" % (self.type2class.get(rtype, 'FIXME_%s' % rtype),
                                          method,
                                          ", ".join( ("%s %s" % (self.type2class[p[0]],
                                                                 p[1])) for p in params )))
        self.insert_code(fd, 'LibVlc-footer.java')
        fd.close()

    def generate_enums(self, dirname, enums):
        """Generate JNA glue code for enums
        """
        for (typ, name, values, comment) in enums:
            if typ != 'enum':
                raise Exception('This method only handles enums')
            javaname=self.type2class[name]

            filename=javaname+".java"

            fd=open(os.path.join(dirname, filename), 'w')

            self.insert_code(fd, 'boilerplate.java')
            self.output(fd, """package org.videolan.jvlc.internal;


public enum %s
{
""" % javaname)
            # FIXME: write comment

            for k, v in values:
                self.output(fd, "        %s (%s)," % (k, v))
            self.output(fd, "");
            self.output(fd, "        private final int _value;");
            self.output(fd, "        %s(int value) { this._value = value; }" % javaname);
            self.output(fd, "        public int value() { return this._value; }");
            self.output(fd, "}")
            fd.close()


def process(output, list_of_includes):
    p=Parser(list_of_includes)
    g=PythonGenerator(p)
    g.save(output)

if __name__ == '__main__':
    opt=OptionParser(usage="""Parse VLC include files and generate bindings code.
%prog [options] include_file.h [...]""")

    opt.add_option("-d", "--debug", dest="debug", action="store_true",
                      default=False,
                      help="Debug mode")

    opt.add_option("-c", "--check", dest="check", action="store_true",
                      default=False,
                      help="Check mode")

    opt.add_option("-j", "--java", dest="java", action="store_true",
                      default=False,
                      help="Generate java bindings (default is python)")

    opt.add_option("-o", "--output", dest="output", action="store",
                      type="str", default="-",
                      help="Output filename(python)/dirname(java)")

    (options, args) = opt.parse_args()

    if not args:
        opt.print_help()
        sys.exit(1)

    p=Parser(args)
    if options.check:
        # Various consistency checks.
        for (rt, name, params, comment) in p.methods:
            if not comment.strip():
                print "No comment for %s" % name
                continue
            names=comment_re.findall(comment)
            if len(names) != len(params):
                print "Docstring comment parameters mismatch for %s" % name

    if options.debug:
        p.dump_methods()
        p.dump_enums()

    if options.check or options.debug:
        sys.exit(0)

    if options.java:
        g=JavaGenerator(p)
    else:
        g=PythonGenerator(p)

    g.save(options.output)
