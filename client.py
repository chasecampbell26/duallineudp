import socket
import selectors
import sys

APP_LOCAL_IP = sys.argv[1] # should have been 127.0.0.1, but our app won't talk to it so listening on a trusted interface instead
APP_LOCAL_PORT = int(sys.argv[2])
PRIMARY_WAN_LOCAL_IP = sys.argv[3]
# SECONDARY_WAN_LOCAL_IP = sys.argv[4]
WAN_LOCAL_PORT = int(sys.argv[5]) # shared by primary and secondary WAN sockets
WAN_REMOTE_IP = sys.argv[6]
WAN_REMOTE_PORT = int(sys.argv[7])
MAX_DATAGRAM_LENGTH = 4096
MAX_CONSECUTIVE_READS = 100 # to prevent one stream from starving others

# We don't know this at the start. App knows our address, and we rely on them to tell us theirs by sending us the first datagram
app_remote_address = None

socket.setdefaulttimeout(0)

app_socket = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
app_socket.bind((APP_LOCAL_IP, APP_LOCAL_PORT))

primary_wan_socket = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
primary_wan_socket.bind((PRIMARY_WAN_LOCAL_IP, WAN_LOCAL_PORT))

#secondary_wan_socket = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
#secondary_wan_socket.bind((SECONDARY_WAN_IP, WAN_PORT))

sel = selectors.DefaultSelector()
sel.register(app_socket, selectors.EVENT_READ)
sel.register(primary_wan_socket, selectors.EVENT_READ)

def app_to_primary_wan():
    global app_remote_address
    reads = 0
    while reads < MAX_CONSECUTIVE_READS:
        try:
            (datagram, app_read_address) = app_socket.recvfrom(MAX_DATAGRAM_LENGTH)
        except BlockingIOError:
            return
        reads += 1

        if app_read_address != app_remote_address:
            app_remote_address = app_read_address
            print("app remote address now changed to", app_read_address)
        if len(datagram) == MAX_DATAGRAM_LENGTH:
            raise OSError("Received max length datagram")

        try:
            len_sent = primary_wan_socket.sendto(bytes([1]) + datagram, (WAN_REMOTE_IP, WAN_REMOTE_PORT))
        except BlockingIOError as bioe:
            print("BlockingIOError on primary_wan_socket send")
            if hasattr(bioe, "characters_written"):
                print("Chars sent:", bioe.characters_written)
            continue
        if len_sent < len(datagram) + 1:
            print("len_sent", len_sent, "len(datagram)", len(datagram))
            raise OSError("len_sent not equal to len(datagram) + 1")

def primary_wan_to_app():
    reads = 0
    while reads < MAX_CONSECUTIVE_READS:
        try:
            (datagram, primary_wan_read_address) = primary_wan_socket.recvfrom(MAX_DATAGRAM_LENGTH)
        except BlockingIOError:
            return
        reads += 1

        if primary_wan_read_address != (WAN_REMOTE_IP, WAN_REMOTE_PORT):
            print("Received datagram on primary_wan_socket from unexpected address", primary_wan_read_address)
            continue
        if len(datagram) == MAX_DATAGRAM_LENGTH:
            raise OSError("Received max length datagram")

        if app_remote_address == None:
            print("app_remote_address not set yet, dropping datagram")
            continue

        try:
            len_sent = app_socket.sendto(datagram[1:], app_remote_address)
        except BlockingIOError as bioe:
            print("BlockingIOError on app_socket send")
            if hasattr(bioe, "characters_written"):
                print("Chars sent:", bioe.characters_written)
            continue
        if len_sent < len(datagram) - 1:
            print("len_sent", len_sent, "datagram", len(datagram))
            raise OSError("len_sent not equal to datagram - 1")

while True:
    ready_sockets = sel.select()
    for key, events in ready_sockets:
        if key.fileobj == app_socket:
            app_to_primary_wan()

        if key.fileobj == primary_wan_socket:
            primary_wan_to_app()
