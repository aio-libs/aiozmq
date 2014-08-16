from collections import Set


class _EndpointsSet(Set):

    __slots__ = ('_collection',)

    def __init__(self, collection):
        self._collection = collection

    def __len__(self):
        return len(self._collection)

    def __contains__(self, endpoint):
        return endpoint in self._collection

    def __iter__(self):
        return iter(self._collection)

    def __repr__(self):
        return '{' + ', '.join(sorted(self._collection)) + '}'

    __str__ = __repr__
