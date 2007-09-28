#!/usr/bin/python
#
# CDDL HEADER START
#
# The contents of this file are subject to the terms of the
# Common Development and Distribution License (the "License").
# You may not use this file except in compliance with the License.
#
# You can obtain a copy of the license at usr/src/OPENSOLARIS.LICENSE
# or http://www.opensolaris.org/os/licensing.
# See the License for the specific language governing permissions
# and limitations under the License.
#
# When distributing Covered Code, include this CDDL HEADER in each
# file and include the License file at usr/src/OPENSOLARIS.LICENSE.
# If applicable, add the following below this CDDL HEADER, with the
# fields enclosed by brackets "[]" replaced with your own identifying
# information: Portions Copyright [yyyy] [name of copyright owner]
#
# CDDL HEADER END
#

#
# Copyright 2007 Sun Microsystems, Inc.  All rights reserved.
# Use is subject to license terms.
#

"""module describing a generic packaging object

This module contains the Action class, which represents a generic packaging
object.  It also contains a helper function, gunzip_from_stream(), which actions
may use to decompress their data payloads."""

import os
import sha
import zlib

import pkg.actions

def gunzip_from_stream(gz, outfile):
        """Decompress a gzipped input stream into an output stream.

        The argument 'gz' is an input stream of a gzipped file (XXX make it do
        either a gzipped file or raw zlib compressed data), and 'outfile' is is
        an output stream.  gunzip_from_stream() decompresses data from 'gz' and
        writes it to 'outfile', and returns the hexadecimal SHA-1 sum of that
        data.
        """

        FHCRC = 2
        FEXTRA = 4
        FNAME = 8
        FCOMMENT = 16

        # Read the header
        magic = gz.read(2)
        if magic != "\037\213":
                raise IOError, "Not a gzipped file"
        method = ord(gz.read(1))
        if method != 8:
                raise IOError, "Unknown compression method"
        flag = ord(gz.read(1))
        gz.read(6) # Discard modtime, extraflag, os

        # Discard an extra field
        if flag & FEXTRA:
                xlen = ord(gz.read(1))
                xlen = xlen + 256 * ord(gz.read(1))
                gz.read(xlen)

        # Discard a null-terminated filename
        if flag & FNAME:
                while True:
                        s = gz.read(1)
                        if not s or s == "\000":
                                break

        # Discard a null-terminated comment
        if flag & FCOMMENT:
                while True:
                        s = gz.read(1)
                        if not s or s == "\000":
                                break

        # Discard a 16-bit CRC
        if flag & FHCRC:
                gz.read(2)

        shasum = sha.new()
        dcobj = zlib.decompressobj(-zlib.MAX_WBITS)

        while True:
                buf = gz.read(64 * 1024)
                if buf == "":
                        ubuf = dcobj.flush()
                        shasum.update(ubuf)
                        outfile.write(ubuf)
                        break
                ubuf = dcobj.decompress(buf)
                shasum.update(ubuf)
                outfile.write(ubuf)

        return shasum.hexdigest()

class Action(object):
        """Class representing a generic packaging object.

        An Action is a very simple wrapper around two dictionaries: a named set
        of data streams and a set of attributes.  Data streams generally
        represent files on disk, and attributes represent metadata about those
        files.
        """

        # 'name' is the name of the action, as specified in a manifest.
        name = "generic"
        # 'attributes' is a list of the known usable attributes.  Or something.
        # There probably isn't a good use for it.
        attributes = ()
        # 'key_attr' is the name of the attribute whose value must be unique in
        # the namespace of objects represented by a particular action.  For
        # instance, a file's key_attr would be its pathname.  Or a driver's
        # key_attr would be the driver name.  When 'key_attr' is None, it means
        # that all attributes of the action are distinguishing.
        key_attr = None

        def __init__(self, data=None, **attrs):
                """Action constructor.

                The optional 'data' argument may be either a string, a file-like
                object, or a callable.  If it is a string, then it will be
                substituted with a callable that will return an open handle to
                the file represented by the string.  Otherwise, if it is not
                already a callable, it is assumed to be a file-like object, and
                will be substituted with a callable that will return the object.
                If it is a callable, it will not be replaced at all.

                Any remaining named arguments will be treated as attributes.
                """
                self.attrs = attrs

                if isinstance(data, str):
                        def file_opener():
                                return open(data)
                        self.data = file_opener
                elif not callable(data) and data != None:
                        def data_opener():
                                return data
                        self.data = data_opener
                else:
                        self.data = data

        def __str__(self):
                """Serialize the action into manifest form.

                The form is the name, followed by the hash, if it exists,
                followed by attributes in the form 'key=value'.  All fields are
                space-separated, which for now means that no tokens may have
                spaces (though they may have '=' signs).

                Note that an object with a datastream may have been created in
                such a way that the hash field is not populated, or not
                populated with real data.  The action classes do not guarantee
                that at the time that __str__() is called, the hash is properly
                computed.  This may need to be done externally.
                """
                str = self.name
                if hasattr(self, "hash"):
                        str += " " + self.hash

                def q(s):
                        if " " in s:
                                return '"%s"' % s
                        else:
                                return s

                stringattrs = [
                    "%s=%s" % (k, q(self.attrs[k]))
                    for k in self.attrs
                    if not isinstance(self.attrs[k], list)
                ]

                listattrs = [
                    " ".join([
                        "%s=%s" % (k, q(lmt))
                        for lmt in self.attrs[k]
                    ])
                    for k in self.attrs
                    if isinstance(self.attrs[k], list)
                ]

                return " ".join([str] + stringattrs + listattrs)

        def __cmp__(self, other):
                types = pkg.actions.types

                # Sort directories by path
                if type(self) == types["dir"] == type(other):
                        return cmp(self.attrs["path"], other.attrs["path"])
                # Directories come before anything else
                elif type(self) == types["dir"] != type(other):
                        return -1
                elif type(self) != types["dir"] == type(other):
                        return 1
                # Hard links come after files.
                # XXX We order them after everything, though, so that they
                # really do show up after files.  Otherwise they could get
                # sorted only through comparisons with things that don't care
                # how they're sorted with regard to files, and they could end up
                # before the files they need to be before.  :(
                elif type(self) == types["hardlink"] != type(other):
                        return 1
                elif type(self) != types["hardlink"] == type(other):
                        return -1
                # Resort to the default comparison
                else:
                        return cmp(id(self), id(other))

        def different(self, other):
                """Returns True if other represents a non-ignorable change from self.
                
                By default, this means two actions are different if any of their
                attributes are different.  Subclasses should override this
                behavior when appropriate.
                """

                # We could ignore key_attr, or possibly assert that it's the
                # same.
                sset = set(self.attrs.keys())
                oset = set(other.attrs.keys())
                if sset.symmetric_difference(oset):
                        return True

                for a in self.attrs:
                        if self.attrs[a] != other.attrs[a]:
                                return True

                if hasattr(self, "hash"):
                        assert(hasattr(other, "hash"))
                        if self.hash != other.hash:
                                return True

                return False

        def generate_indices(self):
                """Generate for the reverse index database data for this action.

                See pkg.client.pkgplan.make_indices for more information about
                the reverse index database.
                
                This method returns a dictionary mapping attribute names to
                their values.  This is not simply the action attribute
                dictionary, 'attrs', as not necessarily all of these attributes
                are interesting to look up, and there may be others which are
                derived from the canonical attributes (like the path's basename).
                """

                indices = {}

                # XXX What about derived indices -- those which aren't one of
                # the attributes, such as basename?  Just push computing them
                # into the subclasses?  Or is this simple enough that we have no
                # need for a generic.generate_indices() that does anything
                # interesting?
                if hasattr(self, "reverse_indices"):
                        indices.update(
                            (idx, self.attrs[idx])
                            for idx in self.reverse_indices
                        )

                if hasattr(self, "hash"):
                        indices["content"] = self.hash

                return indices

        @staticmethod
        def makedirs(path, leafmode):
                """Make directory specified by 'path' with mode 'leafmode', as
                well as all missing parent directories.

                The difference between this and os.makedirs() is that 'leafmode'
                specifies only the mode of the leaf directory.  Missing parent
                directories are created with the permissions of the deepest
                existing directory."""

                pathlist = path.split("/")
                pathlist[0] = "/"

                g = enumerate(pathlist)
                for i, e in g:
                        if not os.path.isdir(os.path.join("/", *pathlist[:i + 1])):
                                break

                # XXX need to set owner/group, too
                mode = os.stat(os.path.join("/", *pathlist[:i])).st_mode
                for i, e in g:
                        os.mkdir(os.path.join("/", *pathlist[:i]), mode)

                os.mkdir(path, leafmode)

        def needsdata(self, orig):
                """Returns True if the action transition requires a
                datastream."""
                return False

        def attrlist(self, name):
                """return list containing value of named attribute."""
	        value = self.attrs[name]
		if isinstance(value, list):
		        return value
                else:
                        return [ value ]

        def preinstall(self, image, orig):
                """Client-side method that performs pre-install actions."""
                pass

        def install(self, image, orig):
                """Client-side method that installs the object."""
                pass

        def postinstall(self, image, orig):
                """Client-side method that performs post-install actions."""
                pass

        def preremove(self, image):
                """Client-side method that performs pre-remove actions."""
                pass

        def remove(self, image):
                """Client-side method that removes the object."""
                pass

        def postremove(self, image):
                """Client-side method that performs post-remove actions."""
                pass
