import socket
import selectors
import sys
from statsd import StatsClient

SERVER_LISTEN_PORT = int(sys.argv[1])
APP_LISTEN_PORT = int(sys.argv[2])
STATS_ENABLED = len(sys.argv) >= 4 and sys.argv[3] == 'true'
MAX_DATAGRAM_LENGTH = 4096
MAX_CONSECUTIVE_READS = 1000 # to prevent one stream from starving others

primary_client_address = None

socket.setdefaulttimeout(0)

app_socket = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)

wan_socket = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
wan_socket.bind(("", SERVER_LISTEN_PORT))

class NullStatsClient:
    def incr(self, name, value = 1):
        pass

statsd = StatsClient('localhost', 8125) if STATS_ENABLED else NullStatsClient()

sel = selectors.DefaultSelector()
sel.register(app_socket, selectors.EVENT_READ)
sel.register(wan_socket, selectors.EVENT_READ)

def app_to_wan():
    reads = 0
    while reads < MAX_CONSECUTIVE_READS:
        # non-blocking read to avoid holding up program if no incoming
        app_socket.settimeout(0)
        try:
            (data, (app_ip, app_port)) = app_socket.recvfrom(MAX_DATAGRAM_LENGTH)
        except BlockingIOError:
            break
        reads += 1
        statsd.incr("app_socket.recv_datagram")
        statsd.incr("app_socket.recv_bytes", len(data))
        if len(data) == MAX_DATAGRAM_LENGTH:
            raise OSError("Received max length datagram")

        if primary_client_address:
            # blocking write to avoid unnecessary datagram drops
            wan_socket.settimeout(None)
            len_sent = wan_socket.sendto(bytes([1]) + data, primary_client_address)
            statsd.incr("wan_socket.sent_datagram")
            statsd.incr("wan_socket.sent_bytes", len_sent)
            if len_sent < len(data) + 1:
                print("len_sent", len_sent, "data", len(data))
                raise OSError("len_sent not equal to data + 1")
            # TODO implement sending to secondary address
        else:
            print("primary_client_address not set yet, dropping datagram")
    return reads

def wan_to_app():
    global primary_client_address
    reads = 0
    while reads < MAX_CONSECUTIVE_READS:
        wan_socket.settimeout(0)
        try:
            # assuming data comes from client. TODO guard against non-client
            (datagram, remote_address) = wan_socket.recvfrom(MAX_DATAGRAM_LENGTH)
        except BlockingIOError:
            break
        reads += 1
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

            app_datagram = datagram[1:]
            app_socket.settimeout(None)
            len_sent = app_socket.sendto(app_datagram, ("127.0.0.1", APP_LISTEN_PORT))
            statsd.incr("app_socket.sent_datagram")
            statsd.incr("app_socket.sent_bytes", len_sent)
            if len_sent < len(app_datagram):
                print("len_sent", len_sent, "len(app_datagram)", len(app_datagram))
                raise OSError("len_sent not equal to app_datagram")
        # elif datagram[0] == 0:
            # data is from secondary address
            # TODO implement this
        else:
            print("ignoring non-client datagram, datagram[0]==", datagram[0])
    return reads

while True:
    if app_to_wan() + wan_to_app() == 0:
        sel.select()
