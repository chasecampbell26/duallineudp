import socket
import select
import sys
from statsd import StatsClient

SERVER_LISTEN_PORT = int(sys.argv[1])
APP_LISTEN_PORT = int(sys.argv[2])
MAX_DATAGRAM_LENGTH = 4096

primary_client_address = None

socket.setdefaulttimeout(0)

app_socket = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)

wan_socket = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
wan_socket.bind(("", SERVER_LISTEN_PORT))

statsd = StatsClient('localhost', 8125)

while True:
    sockets = [app_socket, wan_socket]
    (read, write, exceptional) = select.select(sockets, [], sockets)
    if exceptional:
        raise OSError

    if app_socket in read:
        (data, (app_ip, app_port)) = app_socket.recvfrom(MAX_DATAGRAM_LENGTH)
        statsd.incr("app_socket.recv_datagram")
        statsd.incr("app_socket.recv_bytes", len(data))
        if len(data) == MAX_DATAGRAM_LENGTH:
            raise OSError("Received max length datagram")

        if primary_client_address:
            len_sent = wan_socket.sendto(bytes([1]) + data, primary_client_address)
            statsd.incr("wan_socket.sent_datagram")
            statsd.incr("wan_socket.sent_bytes", len_sent)
            if len_sent < len(data) + 1:
                print("len_sent", len_sent, "data", len(data))
                raise OSError("len_sent not equal to data + 1")
            # TODO implement sending to secondary address
        else:
            print("primary_client_address not set yet, dropping datagram")

    if wan_socket in read:
        # assuming data comes from client. TODO guard against non-client
        (datagram, remote_address) = wan_socket.recvfrom(MAX_DATAGRAM_LENGTH)
        statsd.incr("wan_socket.recv_datagram")
        statsd.incr("wan_socket.recv_bytes", len(datagram))
        if len(datagram) == MAX_DATAGRAM_LENGTH:
            raise OSError("Received max length datagram")

        # determine if data comes from primary or secondary socket
        if datagram[0] == 1:
            # data is from primary socket
            if primary_client_address != remote_address:
                primary_client_address = remote_address
                print("primary client address updated to", primary_client_address)

            data = datagram[1:]
            len_sent = app_socket.sendto(data, ("127.0.0.1", APP_LISTEN_PORT))
            statsd.incr("app_socket.sent_datagram")
            statsd.incr("app_socket.sent_bytes", len_sent)
            if len_sent < len(data):
                print("len_sent", len_sent, "data", len(data))
                raise OSError("len_sent not equal to data")
        # elif datagram[0] == 0:
            # data is from secondary socket
            # TODO implement this
        else:
            print("ignoring non-client datagram, datagram[0]==", datagram[0])
