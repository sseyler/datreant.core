"""
The Bundle object is the primary manipulator for Treants in aggregate. They are
returned as queries to Groups and other Bundles. They offer convenience methods
for dealing with many Treants at once.

"""

from __future__ import absolute_import

import os
from collections import namedtuple, defaultdict

import multiprocessing as mp
import glob
import fnmatch

from six import string_types
from six.moves import zip

from . import backends
from . import filesystem
from . import _LIMBS, _AGGLIMBS


class Bundle(object):
    """An indexable set of treants.

    """
    _fields = ['uuid', 'treanttype']
    _memberpaths = ['abspath']
    _fields.extend(_memberpaths)

    def __init__(self, *treants, **kwargs):
        """Generate a Bundle from any number of Treants.

        :Arguments:
            *treants*
                treants to be added, which may be nested lists of treants;
                treants can be given as either objects or paths to directories
                that contain treant statefiles; glob patterns are also allowed,
                and all found treants will be added to the collection
        """
        self._state = list()
        self._cache = dict()

        self.add(*treants)

    def __repr__(self):
        return "<Bundle({})>".format(self._list())

    def __len__(self):
        return len(self._list())

    def __getitem__(self, index):
        """Get member corresponding to the given index or slice.

        """
        if isinstance(index, int):
            out = self._list()[index]
        else:
            out = Bundle(*self._list()[index])

        return out

    def __add__(a, b):
        """Addition of collections with collections or treants yields Bundle.

        """
        from .treants import Treant

        if (isinstance(a, (Treant, Bundle)) and
                isinstance(b, (Treant, Bundle))):
            return Bundle(a, b)
        else:
            raise TypeError("Operands must be Treant-derived or Bundles.")

    @classmethod
    def _attach_agglimb_class(cls, limb):
        """Attach a agglimb to the class.

        """
        # property definition
        def getter(self):
            if not hasattr(self, "_"+limb._name):
                setattr(self, "_"+limb._name, limb(self))
            return getattr(self, "_"+limb._name)

        # set the property
        setattr(cls, limb._name,
                property(getter, None, None, limb.__doc__))

    def _attach_agglimb(self, limb):
        """Attach an agglimb.

        """
        setattr(self, limb._name, limb(self))

    def attach(self, *agglimbname):
        """Attach agglimbs by name to this collection. Attaches corresponding limb
        to member Treants.

        """
        for ln in agglimbname:
            # try and get the agglimb class specified
            try:
                agglimb = _AGGLIMBS[ln]
            except KeyError:
                raise KeyError("No such agglimb '{}'".format(ln))

            # attach agglimb; if it's already there, that's okay
            try:
                self._attach_agglimb(agglimb)
            except AttributeError:
                pass

            # attach limb to each member
            for member in self._list():
                member.attach(ln)

    def add(self, *treants):
        """Add any number of members to this collection.

        :Arguments:
            *treants*
                treants to be added, which may be nested lists of treants;
                treants can be given as either objects or paths to directories
                that contain treant statefiles; glob patterns are also allowed,
                and all found treants will be added to the collection
        """
        from .treants import Treant

        outconts = list()
        for treant in treants:
            if treant is None:
                pass
            elif isinstance(treant,
                            (list, tuple, Bundle)):
                self.add(*treant)
            elif isinstance(treant, Treant):
                outconts.append(treant)
            elif os.path.exists(treant):
                tre = filesystem.path2treant(treant)
                for t in tre:
                    outconts.append(t)
            else:
                tre = filesystem.path2treant(*glob.glob(treant))
                for t in tre:
                    outconts.append(t)

        for treant in outconts:
            # check if uuid already present
            uuids = [member['uuid'] for member in self._state]
    
            if treant.uuid not in uuids:
                self._state.append({
                    'uuid': treant.uuid,
                    'treanttype': treant.treanttype,
                    'abspath': os.path.abspath(treant.path)})
    
    def remove(self, *members):
        """Remove any number of members from the collection.

        :Arguments:
            *members*
                instances or indices of the members to remove

        """
        from .treants import Treant

        uuids = self.uuids

        remove = list()
        for member in members:
            if isinstance(member, int):
                remove.append(uuids[member])
            elif isinstance(member, Treant):
                remove.append(member.uuid)
            elif isinstance(member, string_types):
                names = fnmatch.filter(self.names, member)
                uuids = [member.uuid for member in self
                         if (member.name in names)]
                remove.extend(uuids)

            else:
                raise TypeError('Only an integer or treant acceptable')

        # remove redundant uuids from given list if present
        uuids = set([str(uuid) for uuid in uuids])

        # get matching rows
        # TODO: possibly faster to use table.where
        memberlist = list()
        for i, member in enumerate(self._state):
            for uuid in uuids:
                if (member['uuid'] == uuid):
                    memberlist.append(i)

        memberlist.sort()
        j = 0
        # delete matching entries; have to use j to shift the register as
        # we remove entries
        for i in memberlist:
            self._state.pop(i - j)
            j = j + 1

        # remove from cache
        for uuid in remove:
            self._cache.pop(uuid, None)

    def purge(self):
        """Remove all members.

        """
        self._state = list()

    @property
    def treanttypes(self):
        """Return a list of member treanttypes.

        """
        return [member['treanttype'] for member in self._state]

    @property
    def names(self):
        """Return a list of member names.

        Members that can't be found will have name ``None``.

        :Returns:
            *names*
                list giving the name of each member, in order;
                members that are missing will have name ``None``

        """
        names = list()
        for member in self._list():
            if member:
                names.append(member.name)
            else:
                names.append(None)

        return names

    @property
    def paths(self):
        """Return a list of member basedir paths.

        Members that can't be found will have basedir path ``None``.

        :Returns:
            *names*
                list giving the basedir path of each member, in order;
                members that are missing will have basedir path ``None``

        """
        return [member.path if member else None for member in self._list()]

    @property
    def filepath(self):
        """Return a list of member filepaths.

        Members that can't be found will have filepath ``None``.

        :Returns:
            *names*
                list giving the filepath of each member, in order;
                members that are missing will have filepath ``None``

        """
        filepaths = list()
        for member in self._list():
            if member:
                filepaths.append(member.filepath)
            else:
                filepaths.append(None)

        return filepaths

    @property
    def uuids(self):
        """Return a list of member uuids.

        :Returns:
            *uuids*
                list giving the uuid of each member, in order

        """
        return [member['uuid'] for member in self._state]

    def _list(self):
        """Return a list of members.

        Note: modifications of this list won't modify the members of the
        collection!

        Missing members will be present in the list as ``None``. This method is
        not intended for user-level use.

        """
        members = defaultdict(list)

        for member in self._state:
            for key in self._fields:
                members[key].append(member[key])

        uuids = members['uuid']

        findlist = list()
        memberlist = list()

        for uuid in uuids:
            if uuid in self._cache and self._cache[uuid]:
                memberlist.append(self._cache[uuid])
            else:
                memberlist.append(None)
                findlist.append(uuid)

        # track down our non-cached treants
        paths = {path: members[path]
                 for path in self._memberpaths}
        foxhound = filesystem.Foxhound(self, findlist, paths)
        foundconts = foxhound.fetch(as_treants=True)

        # add to cache, and ensure we get updated paths with a re-add
        # in case of an IOError, skip (probably due to permissions, but will
        # need something more robust later
        self._cache.update(foundconts)
        try:
            self.add(*foundconts.values())
        except OSError:
            pass

        # insert found treants into output list
        for uuid in findlist:
            result = foundconts[uuid]
            if not result:
                ind = list(members['uuid']).index(uuid)
                raise IOError("Could not find member" +
                              " {} (uuid: {});".format(ind, uuid) +
                              " re-add or remove it.")

            memberlist[list(uuids).index(uuid)] = result

        return memberlist

    def map(self, function, processes=1, **kwargs):
        """Apply a function to each member, perhaps in parallel.

        A pool of processes is created for *processes* > 1; for example,
        with 40 members and 'processes=4', 4 processes will be created,
        each working on a single member at any given time. When each process
        completes work on a member, it grabs another, until no members remain.

        *kwargs* are passed to the given function when applied to each member

        :Arguments:
            *function*
                function to apply to each member; must take only a single
                treant instance as input, but may take any number of keyword
                arguments

        :Keywords:
            *processes*
                how many processes to use; if 1, applies function to each
                member in member order

        :Returns:
            *results*
                list giving the result of the function for each member,
                in member order; if the function returns ``None`` for each
                member, then only ``None`` is returned instead of a list
            """
        if processes > 1:
            pool = mp.Pool(processes=processes)
            results = dict()
            for member in self:
                results[member.uuid] = pool.apply_async(
                        function, args=(member,), kwds=kwargs).get()
            pool.close()
            pool.join()

            # sort by member order
            results = [results[uuid] for uuid in self.uuids]
        else:
            results = [function(member, **kwargs) for member in self]

        # check if list is all ``None``: if so, we return ``None``
        if all([(i is None) for i in results]):
            results = None

        return results
