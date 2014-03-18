from asyncio import BaseProtocol, BaseTransport

__all__ = ['ZmqTransport', 'ZmqProtocol']


class ZmqTransport(BaseTransport):
    """Interface for ZeroMQ transport."""

    def write(self, *data):
        """Write message to the transport.

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

    def set_write_buffer_limits(self, high=None, low=None):
        """Set the high- and low-water limits for write flow control.

        These two values control when to call the protocol's
        pause_writing() and resume_writing() methods.  If specified,
        the low-water limit must be less than or equal to the
        high-water limit.  Neither value can be negative.

        The defaults are implementation-specific.  If only the
        high-water limit is given, the low-water limit defaults to a
        implementation-specific value less than or equal to the
        high-water limit.  Setting high to zero forces low to zero as
        well, and causes pause_writing() to be called whenever the
        buffer becomes non-empty.  Setting low to zero causes
        resume_writing() to be called only once the buffer is empty.
        Use of zero for either limit is generally sub-optimal as it
        reduces opportunities for doing I/O and computation
        concurrently.
        """
        raise NotImplementedError

    def get_write_buffer_size(self):
        """Return the current size of the write buffer."""
        raise NotImplementedError


class ZmqProtocol(BaseProtocol):
    """Interface for ZeroMQ protocol."""

    def msg_received(self, *data):
        """Called when some ZeroMQ message is received.

        data is the multipart tuple of bytes with at least one item.
        """
