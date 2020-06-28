import socket
import selectors
import sys
from statsd import StatsClient
from constants import MAX_DATAGRAM_LENGTH

SERVER_LISTEN_PORT = int(sys.argv[1])
APP_LISTEN_PORT = int(sys.argv[2])
STATS_ENABLED = len(sys.argv) >= 4 and sys.argv[3] == 'true'

primary_client_address = None
app_to_wan_pending = None
wan_to_app_pending = None

socket.setdefaulttimeout(0)

app_socket = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)

wan_socket = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
wan_socket.bind(("", SERVER_LISTEN_PORT))

class NullStatsClient:
    def incr(self, name, value = 1):
        pass

statsd = StatsClient('localhost', 8125) if STATS_ENABLED else NullStatsClient()

sel = selectors.DefaultSelector()

# returns if program should block before next call
def app_to_wan():
    global app_to_wan_pending
    if not(app_to_wan_pending):
        try:
            (data, (app_ip, app_port)) = app_socket.recvfrom(MAX_DATAGRAM_LENGTH)
        except BlockingIOError:
            return True
        statsd.incr("app_socket.recv_datagram")
        statsd.incr("app_socket.recv_bytes", len(data))
        if len(data) == MAX_DATAGRAM_LENGTH:
            raise OSError("Received max length datagram")
        if not(primary_client_address):
            print("primary_client_address not set yet, dropping datagram")
            return False
        app_to_wan_pending = bytes([1]) + data

    try:
        len_sent = wan_socket.sendto(app_to_wan_pending, primary_client_address)
    except BlockingIOError:
        return True
    statsd.incr("wan_socket.sent_datagram")
    statsd.incr("wan_socket.sent_bytes", len_sent)
    if len_sent < len(app_to_wan_pending):
        print("len_sent", len_sent, "app_to_wan_pending", len(app_to_wan_pending))
        raise OSError("len_sent not equal to app_to_wan_pending")
    app_to_wan_pending = None
    return False

    # TODO implement sending to secondary address

# returns if program should block before next call
def wan_to_app():
    global primary_client_address
    global wan_to_app_pending
    if not(wan_to_app_pending):
        try:
            # assuming data comes from client. TODO guard against non-client
            (datagram, remote_address) = wan_socket.recvfrom(MAX_DATAGRAM_LENGTH)
        except BlockingIOError:
            return True
        statsd.incr("wan_socket.recv_datagram")
        statsd.incr("wan_socket.recv_bytes", len(datagram))
        if len(datagram) == MAX_DATAGRAM_LENGTH:
            raise OSError("Received max length datagram")

        # determine if data comes from primary or secondary address
        if datagram[0] == 1:
            # data is from primary address
            if primary_client_address != remote_address:
                primary_client_address = remote_address
                print("primary client address updated to", primary_client_address)
        # elif datagram[0] == 0:
            # data is from secondary address
            # TODO implement this
        else:
            print("ignoring non-client datagram, datagram[0]==", datagram[0])
            return False
        wan_to_app_pending = datagram[1:]

    try:
        len_sent = app_socket.sendto(wan_to_app_pending, ("127.0.0.1", APP_LISTEN_PORT))
    except BlockingIOError:
        return True
    statsd.incr("app_socket.sent_datagram")
    statsd.incr("app_socket.sent_bytes", len_sent)
    if len_sent < len(wan_to_app_pending):
        print("len_sent", len_sent, "wan_to_app_pending", len(wan_to_app_pending))
        raise OSError("len_sent not equal to wan_to_app_pending")
    wan_to_app_pending = None
    return False

while True:
    # not inlining to avoid short-circuiting wan_to_app
    app_to_wan_should_block = app_to_wan()
    wan_to_app_should_block = wan_to_app()
    if app_to_wan_should_block and wan_to_app_should_block:
        mapping = sel.get_map()
        if app_socket in mapping:
            sel.unregister(app_socket)
        if wan_socket in mapping:
            sel.unregister(wan_socket)

        app_socket_events = 0
        wan_socket_events = 0
        if app_to_wan_pending:
            wan_socket_events |= selectors.EVENT_WRITE
        else:
            app_socket_events |= selectors.EVENT_READ
        if wan_to_app_pending:
            app_socket_events |= selectors.EVENT_WRITE
        else:
            wan_socket_events |= selectors.EVENT_READ

        if app_socket_events:
            sel.register(app_socket, app_socket_events)
        if wan_socket_events:
            sel.register(wan_socket, wan_socket_events)
        sel.select()
