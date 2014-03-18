from asyncio import BaseProtocol, BaseTransport

__all__ = ['ZmqTransport', 'ZmqProtocol']


class ZmqTransport(BaseTransport):
    """Interface for ZeroMQ transport."""

    def write(self, data, *multipart):
        """Write message to the transport.

        The whole message is `(data,) + multipart`

        This does not block; it buffers the data and arranges for it
        to be sent out asynchronously.
        """
        raise NotImplementedError

    def abort(self):
        """Close the transport immediately.

        Buffered data will be lost.  No more data will be received.
        The protocol's connection_lost() method will (eventually) be
        called with None as its argument.
        """
        raise NotImplementedError

    def getsockopt(self, option):
        """Get ZeroMQ socket option.

        option is a constant like zmq.SUBSCRIBE, zmq.UNSUBSCRIBE, zmq.TYPE etc.

        For list of available options please see:
        http://api.zeromq.org/master:zmq-getsockopt
        """
        raise NotImplementedError

    def setsockopt(self, option, value):
        """Set ZeroMQ socket option.

        option is a constant like zmq.SUBSCRIBE, zmq.UNSUBSCRIBE, zmq.TYPE etc.
        value is a new option value, it's type depend of option name.

        For list of available options please see:
        http://api.zeromq.org/master:zmq-setsockopt
        """
        raise NotImplementedError


class ZmqProtocol(BaseProtocol):
    """Interface for ZeroMQ protocol."""

    def msg_received(self, data, *multipart):
        """Called when some ZeroMQ message is received.

        The whole received message is `(data,) + multipart`
        """
