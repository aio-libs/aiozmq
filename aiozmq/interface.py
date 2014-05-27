from asyncio import BaseProtocol, BaseTransport

__all__ = ['ZmqTransport', 'ZmqProtocol']


class ZmqTransport(BaseTransport):
    """Interface for ZeroMQ transport."""

    def write(self, data):
        """Write message to the transport.

        data is iterable to send as multipart message.

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

    def pause_reading(self):
        """Pause the receiving end.

        No data will be passed to the protocol's msg_received()
        method until resume_reading() is called.
        """
        raise NotImplementedError

    def resume_reading(self):
        """Resume the receiving end.

        Data received will once again be passed to the protocol's
        msg_received() method.
        """
        raise NotImplementedError

    def bind(self, endpoint):
        """Bind transpot to endpoint.

        endpoint is a string in format transport://address as ZeroMQ requires.

        Return bound endpoint, unwinding wildcards if needed.
        """
        raise NotImplementedError

    def unbind(self, endpoint):
        """Unbind transpot from endpoint.
        """
        raise NotImplementedError

    def bindings(self):
        """Return immutable set of endpoints bound to transport.

        N.B. returned endpoints includes only ones that has been bound
        via transport.bind or event_loop.create_zmq_connection calls
        and does not includes bindings that has been done to zmq_sock
        before create_zmq_connection has been called.
        """
        raise NotImplementedError

    def connect(self, endpoint):
        """Connect transpot to endpoint.

        endpoint is a string in format transport://address as ZeroMQ requires.

        For TCP connections endpoint should specify IPv4 or IPv6 address,
        not DNS name.
        Use yield from get_event_loop().getaddrinfo(host, port)
        for translating DNS into address.

        Raise ValueError if endpoint is tcp DNS address.
        Return bound connection, unwinding wildcards if needed.
        """
        raise NotImplementedError

    def disconnect(self, endpoint):
        """Disconnect transpot from endpoint.
        """
        raise NotImplementedError

    def connections(self):
        """Return immutable set of endpoints connected to transport.

        N.B. returned endpoints includes only ones that has been connected
        via transport.connect or event_loop.create_zmq_connection calls
        and does not includes connections that has been done to zmq_sock
        before create_zmq_connection has been called.
        """
        raise NotImplementedError

    def subscribe(self, value):
        """Establish a new message filter on SUB transport.

        Newly created SUB transports filters out all incoming
        messages, therefore you should to call this method to
        establish an initial message filter.

        Value should be bytes.

        An empty (b'') value subscribes to all incoming messages. A
        non-empty value subscribes to all messages beginning with the
        specified prefix. Multiple filters may be attached to a single
        SUB transport, in which case a message shall be accepted if it
        matches at least one filter.
        """
        raise NotImplementedError

    def unsubscribe(self, value):
        """Remove an existing message filter on a SUB transport.

        Value should be bytes.

        The filter specified must match an existing filter previously
        established with the .subscribe(). If the transport has
        several instances of the same filter attached the
        .unsubscribe() removes only one instance, leaving
        the rest in place and functional.
        """
        raise NotImplementedError

    def subscriptions(self):
        """Return immutable set of subscriptions (bytes) subscribed on
        transport.

        N.B. returned subscriptions includes only ones that has been
        subscribed via transport.subscribe call and does not includes
        subscribtions that has been done to zmq_sock before
        create_zmq_connection has been called.
        """
        raise NotImplementedError


class ZmqProtocol(BaseProtocol):
    """Interface for ZeroMQ protocol."""

    def msg_received(self, data):
        """Called when some ZeroMQ message is received.

        data is the multipart tuple of bytes with at least one item.
        """
