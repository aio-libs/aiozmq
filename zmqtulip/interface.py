from asyncio import BaseProtocol, BaseTransport

__all__ = ['ZmqTransport', 'ZmqProtocol']


class ZmqTransport(BaseTransport):

    def write(self, data, *multipart):
        pass

    def abort(self):
        """Close the transport immediately.

        Buffered data will be lost.  No more data will be received.
        The protocol's connection_lost() method will (eventually) be
        called with None as its argument.
        """
        raise NotImplementedError

    def getopt(self, option):
        pass

    def setopt(self, option, value):
        pass


class ZmqProtocol(BaseProtocol):

    def msg_received(self, data, *multipart):
        pass
