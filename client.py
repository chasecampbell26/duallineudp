import socket
import select
import sys

APP_LOCAL_IP = sys.argv[1] # should have been 127.0.0.1, but our app won't talk to it so listening on a trusted interface instead
APP_LOCAL_PORT = int(sys.argv[2])
PRIMARY_WAN_LOCAL_IP = sys.argv[3]
# SECONDARY_WAN_LOCAL_IP = sys.argv[4]
WAN_LOCAL_PORT = int(sys.argv[5]) # shared by primary and secondary WAN sockets
WAN_REMOTE_IP = sys.argv[6]
WAN_REMOTE_PORT = int(sys.argv[7])
MAX_DATAGRAM_LENGTH = 4096

# We don't know this at the start. App knows our address, and we rely on them to tell us theirs by sending us the first datagram
app_remote_address = None

app_socket = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
app_socket.bind((APP_LOCAL_IP, APP_LOCAL_PORT))

primary_wan_socket = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
primary_wan_socket.bind((PRIMARY_WAN_LOCAL_IP, WAN_LOCAL_PORT))

#secondary_wan_socket = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
#secondary_wan_socket.bind((SECONDARY_WAN_IP, WAN_PORT))


while True:
    sockets = [app_socket, primary_wan_socket]
    (read, dummy, exceptional) = select.select(sockets, [], sockets)
    if exceptional:
        raise OSError

    # TODO use selectors module
    if app_socket in read:
        (data, app_read_address) = app_socket.recvfrom(MAX_DATAGRAM_LENGTH)
        if app_read_address != app_remote_address:
            app_remote_address = app_read_address
            print("app remote address now changed to", app_read_address)
        if len(data) == MAX_DATAGRAM_LENGTH:
            raise OSError("Received max length datagram")

        (dummy, write, dummy) = select.select([], [primary_wan_socket], [], 0)
        if not(primary_wan_socket in write):
            print("primary_wan_socket not ready for write, dropping datagram")
            continue
        len_sent = primary_wan_socket.sendto(bytes([1]) + data, (WAN_REMOTE_IP, WAN_REMOTE_PORT))
        if len_sent < len(data) + 1:
            print("len_sent", len_sent, "data", len(data))
            raise OSError("len_sent not equal to data + 1")

    if primary_wan_socket in read:
        (datagram, primary_wan_read_address) = primary_wan_socket.recvfrom(MAX_DATAGRAM_LENGTH)
        if primary_wan_read_address != (WAN_REMOTE_IP, WAN_REMOTE_PORT):
            print("Received datagram on primary_wan_socket from unexpected address", primary_wan_read_address)
            continue
        if len(datagram) == MAX_DATAGRAM_LENGTH:
            raise OSError("Received max length datagram")

        if app_remote_address == None:
            print("app_remote_address not set yet, dropping datagram")
            continue
        (dummy, write, dummy) = select.select([], [app_socket], [], 0)
        if not(app_socket in write):
            print("app_socket not ready for write, dropping datagram")
            continue
        len_sent = app_socket.sendto(datagram[1:], app_remote_address)
        if len_sent < len(datagram) - 1:
            print("len_sent", len_sent, "datagram", len(datagram))
            raise OSError("len_sent not equal to datagram - 1")
