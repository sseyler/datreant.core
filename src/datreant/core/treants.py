"""
Basic Treant objects: the organizational units for :mod:`datreant`.

"""
import os
import sys
import shutil
from uuid import uuid4
import logging
import functools
import six

from . import limbs
from . import filesystem
from . import collections
from .util import makedirs
from .trees import TreeMixin, Tree

from .backends.statefiles import treantfile

from . import _TREANTS
from . import _LIMBS


class MultipleTreantsError(Exception):
    pass


class NoTreantsError(Exception):
    pass


class _Treantmeta(type):
    def __init__(cls, name, bases, classdict):
        type.__init__(type, name, bases, classdict)

        treanttype = classdict['_treanttype']
        _TREANTS[treanttype] = cls


@functools.total_ordering
class Treant(six.with_metaclass(_Treantmeta, TreeMixin)):
    """Core class for all Treants.

    """
    # required components
    _treanttype = 'Treant'

    def __init__(self, treant, new=False, categories=None, tags=None):
        """Generate a new or regenerate an existing (on disk) Treant object.

        :Required arguments:
            *treant*
                base directory of a new or existing Treant; will regenerate
                a Treant if a state file is found, but will genereate a new
                one otherwise

                if multiple Treant state files are in the given directory,
                will raise :exception:`MultipleTreantsError`; specify
                the full path to the desired state file to regenerate the
                desired Treant in this case

                use the *new* keyword to force generation of a new Treant
                at the given path

        :Optional arguments:
            *new*
                generate a new Treant even if one already exists at the given
                location *treant*
            *categories*
                dictionary with user-defined keys and values; used to give
                Treants distinguishing characteristics
            *tags*
                list with user-defined values; like categories, but useful for
                adding many distinguishing descriptors
        """
        if new:
            self._generate(treant, categories=categories, tags=tags)
        else:
            try:
                self._regenerate(treant, categories=categories, tags=tags)
            except NoTreantsError:
                self._generate(treant, categories=categories, tags=tags)

    @classmethod
    def _attach_limb_class(cls, limb):
        """Attach a limb to the class.

        """
        # property definition
        def getter(self):
            if not hasattr(self, "_"+limb._name):
                setattr(self, "_"+limb._name, limb(self))
            return getattr(self, "_"+limb._name)

        # set the property
        setattr(cls, limb._name,
                property(getter, None, None, limb.__doc__))

    def _attach_limb(self, limb):
        """Attach a limb.

        """
        try:
            setattr(self, limb._name, limb(self))
        except AttributeError:
            pass

    def attach(self, *limbname):
        """Attach limbs by name to this Treant.

        """
        for ln in limbname:
            try:
                limb = _LIMBS[ln]
            except KeyError:
                raise KeyError("No such limb '{}'".format(ln))
            else:
                self._attach_limb(limb)

    @property
    def _state(self):
        return self._backend._state

    @property
    def _read(self):
        return self._backend.read()

    @property
    def _write(self):
        return self._backend.write()

    def __repr__(self):
        return "<Treant: '{}'>".format(self.name)

    def __getstate__(self):
        return self.filepath

    def __setstate__(self, state):
        self._regenerate(state)

    def __eq__(self, other):
        try:
            return (self.name + self.uuid) == (other.name + other.uuid)
        except AttributeError:
            return NotImplemented

    def __lt__(self, other):
        try:
            return (self.name + self.uuid) < (other.name + other.uuid)
        except AttributeError:
            return NotImplemented

    def __add__(a, b):
        """Addition of treants with collections or treants yields Bundle.

        """
        if (isinstance(a, (Treant, collections.Bundle)) and
           isinstance(b, (Treant, collections.Bundle))):
            return collections.Bundle(a, b)
        else:
            raise TypeError("Operands must be Treant-derived or Bundles.")

    def _generate(self, treant, categories=None, tags=None):
        """Generate new Treant object.

        """

        # process keywords
        if not categories:
            categories = dict()
        if not tags:
            tags = list()

        # build basedir; stop if we hit a permissions error
        try:
            makedirs(treant)
        except OSError as e:
            if e.errno == 13:
                raise OSError(13, "Permission denied; " +
                              "cannot create '{}'".format(treant))
            else:
                raise

        filename = filesystem.statefilename(self._treanttype, str(uuid4()))

        statefile = os.path.join(treant, filename)

        # generate state file
        self._backend = treantfile(statefile)

        # add categories, tags
        self.categories.add(categories)
        self.tags.add(tags)

    def _regenerate(self, treant, categories=None, tags=None):
        """Re-generate existing Treant object.

        """

        # process keywords
        if not categories:
            categories = dict()
        if not tags:
            tags = list()

        # convenient to give only name of object (its directory name)
        if os.path.isdir(treant):
            statefile = filesystem.glob_treant(treant)

            # if only one state file, load it; otherwise, complain loudly
            if len(statefile) == 1:
                self._backend = treantfile(statefile[0])
                # try to add categories, tags
                try:
                    self.categories.add(categories)
                    self.tags.add(tags)
                except (OSError, IOError):
                    pass

            elif len(statefile) == 0:
                raise NoTreantsError('No Treants found in directory.')
            else:
                raise MultipleTreantsError('Multiple Treants found in '
                                           'directory. Give path to a '
                                           'specific state file.')

        # if a state file is given, try loading it
        elif os.path.exists(treant):
            self._backend = treantfile(treant)
            # try to add categories, tags
            try:
                self.categories.add(categories)
                self.tags.add(tags)
            except (OSError, IOError):
                pass
        else:
            raise NoTreantsError('No Treants found in path.')

    @property
    def name(self):
        """The name of the Treant.

        The name of a Treant need not be unique with respect to other
        Treants, but is used as part of Treant's displayed
        representation.

        """
        return os.path.basename(os.path.dirname(self._backend.filename))

    @name.setter
    def name(self, name):
        """The name of the Treant.

        The name of a Treant need not be unique with respect to other
        Treants, but is used as part of Treant's displayed
        representation.

        """
        olddir = os.path.dirname(self._backend.filename)
        newdir = os.path.join(os.path.dirname(olddir), name)
        statefile = os.path.join(newdir,
                                 filesystem.statefilename(
                                     self._treanttype, self.uuid))

        os.rename(olddir, newdir)
        self._regenerate(statefile)

    @property
    def uuid(self):
        """Get Treant uuid.

        A Treant's uuid is used by other Treants to identify it. The uuid
        is given in the Treant's state file name for fast filesystem
        searching. For example, a Treant with state file::

            'Treant.7dd9305a-d7d9-4a7b-b513-adf5f4205e09.h5'

        has uuid::

            '7dd9305a-d7d9-4a7b-b513-adf5f4205e09'

        Changing this string will alter the Treant's uuid. This is not
        generally recommended.

        :Returns:
            *uuid*
                unique identifier string for this Treant
        """
        return os.path.basename(self._backend.filename).split('.')[1]

    @property
    def treanttype(self):
        """The type of the Treant.

        """
        return os.path.basename(self._backend.filename).split('.')[0]

    @property
    def location(self):
        """The location of the Treant.

        Setting the location to a new path physically moves the Treant to
        the given location. This only works if the new location is an empty or
        nonexistent directory.

        """
        return os.path.dirname(self._backend.get_location())

    @location.setter
    def location(self, value):
        """Set location of Treant.

        Physically moves the Treant to the given location.
        Only works if the new location is an empty or nonexistent
        directory.

        """
        makedirs(value)
        oldpath = self._backend.get_location()
        newpath = os.path.join(value, self.name)
        statefile = os.path.join(newpath,
                                 filesystem.statefilename(
                                     self._treanttype, self.uuid))
        os.rename(oldpath, newpath)
        self._regenerate(statefile)

    @property
    def path(self):
        """Absolute path to the Treant's base directory.

        This is a convenience property; the same result can be obtained by
        joining :attr:`location` and :attr:`name`.

        """
        return self._backend.get_location()

    @property
    def filepath(self):
        """Absolute path to the Treant's state file.

        """
        return self._backend.filename

    @property
    def tree(self):
        return Tree(self.path)
