import socket
import selectors
import sys
from constants import MAX_DATAGRAM_LENGTH, MAX_CONSECUTIVE_READS

APP_LOCAL_IP = sys.argv[1] # should have been 127.0.0.1, but our app won't talk to it so listening on a trusted interface instead
APP_LOCAL_PORT = int(sys.argv[2])
PRIMARY_WAN_LOCAL_IP = sys.argv[3]
# SECONDARY_WAN_LOCAL_IP = sys.argv[4]
WAN_LOCAL_PORT = int(sys.argv[5]) # shared by primary and secondary WAN sockets
WAN_REMOTE_IP = sys.argv[6]
WAN_REMOTE_PORT = int(sys.argv[7])

# We don't know this at the start. App knows our address, and we rely on them to tell us theirs by sending us the first datagram
app_remote_address = None

socket.setdefaulttimeout(0)

app_socket = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
app_socket.bind((APP_LOCAL_IP, APP_LOCAL_PORT))

primary_wan_socket = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
primary_wan_socket.bind((PRIMARY_WAN_LOCAL_IP, WAN_LOCAL_PORT))

#secondary_wan_socket = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
#secondary_wan_socket.bind((SECONDARY_WAN_IP, WAN_PORT))

app_to_primary_wan_pending = None
primary_wan_to_app_pending = None

sel = selectors.DefaultSelector()
sel.register(app_socket, selectors.EVENT_READ)
sel.register(primary_wan_socket, selectors.EVENT_READ)

# returns True if program should block before next call
def app_to_primary_wan():
    global app_to_primary_wan_pending
    global app_remote_address
    if not(app_to_primary_wan_pending):
        try:
            (datagram, app_read_address) = app_socket.recvfrom(MAX_DATAGRAM_LENGTH)
        except BlockingIOError:
            return True

        if app_read_address != app_remote_address:
            app_remote_address = app_read_address
            print("app remote address now changed to", app_read_address)
        if len(datagram) == MAX_DATAGRAM_LENGTH:
            raise OSError("Received max length datagram")
        app_to_primary_wan_pending = bytes([1]) + datagram

    try:
        len_sent = primary_wan_socket.sendto(app_to_primary_wan_pending, (WAN_REMOTE_IP, WAN_REMOTE_PORT))
    except BlockingIOError as bioe:
        return True
    if len_sent < len(app_to_primary_wan_pending):
        print("len_sent", len_sent, "app_to_primary_wan_pending", len(app_to_primary_wan_pending))
        raise OSError("len_sent not equal to len(app_to_primary_wan_pending)")
    app_to_primary_wan_pending = None
    return False

# returns True if program should block before next call
def primary_wan_to_app():
    global primary_wan_to_app_pending
    if not(primary_wan_to_app_pending):
        try:
            (datagram, primary_wan_read_address) = primary_wan_socket.recvfrom(MAX_DATAGRAM_LENGTH)
        except BlockingIOError:
            return True

        if primary_wan_read_address != (WAN_REMOTE_IP, WAN_REMOTE_PORT):
            print("Received datagram on primary_wan_socket from unexpected address", primary_wan_read_address)
            return False
        if len(datagram) == MAX_DATAGRAM_LENGTH:
            raise OSError("Received max length datagram")

        if app_remote_address == None:
            print("app_remote_address not set yet, dropping datagram")
            return False
        primary_wan_to_app_pending = datagram[1:]

    try:
        len_sent = app_socket.sendto(primary_wan_to_app_pending, app_remote_address)
    except BlockingIOError as bioe:
        return True
    if len_sent < len(primary_wan_to_app_pending):
        print("len_sent", len_sent, "primary_wan_to_app_pending", len(primary_wan_to_app_pending))
        raise OSError("len_sent not equal to primary_wan_to_app_pending")
    primary_wan_to_app_pending = None
    return False

while True:
    # not inlining to avoid short-circuiting primary_wan_to_app
    app_to_primary_wan_should_block = app_to_primary_wan()
    primary_wan_to_app_should_block = primary_wan_to_app()
    if app_to_primary_wan_should_block and primary_wan_to_app_should_block:
        mapping = sel.get_map()
        if app_socket in mapping:
            sel.unregister(app_socket)
        if primary_wan_socket in mapping:
            sel.unregister(primary_wan_socket)

        app_socket_events = 0
        primary_wan_socket_events = 0
        if app_to_primary_wan_pending:
            primary_wan_socket_events |= selectors.EVENT_WRITE
        else:
            app_socket_events |= selectors.EVENT_READ
        if primary_wan_to_app_pending:
            app_socket_events |= selectors.EVENT_WRITE
        else:
            primary_wan_socket_events |= selectors.EVENT_READ

        if app_socket_events:
            sel.register(app_socket, app_socket_events)
        if primary_wan_socket_events:
            sel.register(primary_wan_socket, primary_wan_socket_events)
        sel.select()
