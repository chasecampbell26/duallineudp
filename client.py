import socket
import select
import sys

APP_IP = sys.argv[1]
APP_PORT = int(sys.argv[2])
PRIMARY_WAN_IP = sys.argv[3]
SECONDARY_WAN_IP = sys.argv[4]
WAN_PORT = int(sys.argv[5]) # local port, shared by primary and secondary WAN sockets
SERVER_IP = sys.argv[6]
SERVER_PORT = int(sys.argv[7])
MAX_DATAGRAM_LENGTH = 4096

socket.setdefaulttimeout(0)

app_socket = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
app_socket.bind((APP_IP, APP_PORT))

primary_wan_socket = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
primary_wan_socket.bind((PRIMARY_WAN_IP, WAN_PORT))

#secondary_wan_socket = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
#secondary_wan_socket.bind((SECONDARY_WAN_IP, WAN_PORT))


while True:
    sockets = [app_socket, primary_wan_socket]
    (read, write, exceptional) = select.select(sockets, [], sockets)
    if exceptional:
        raise OSError

    # TODO condense sent/received logging
    if app_socket in read:
        (data, (app_ip, app_port)) = app_socket.recvfrom(MAX_DATAGRAM_LENGTH)
        if len(data) == MAX_DATAGRAM_LENGTH:
            raise OSError("Received max length datagram")
        print("data received on app_socket from", app_ip, app_port)

        len_sent = primary_wan_socket.sendto(bytes([1]) + data, (SERVER_IP, SERVER_PORT))
        if len_sent < len(data) + 1:
            print("len_sent", len_sent, "data", len(data))
            raise OSError("len_sent not equal to data + 1")
        print("data sent on primary_wan_socket")

    if primary_wan_socket in read:
        (datagram, (server_ip, server_port)) = primary_wan_socket.recvfrom(MAX_DATAGRAM_LENGTH)
        if len(datagram) == MAX_DATAGRAM_LENGTH:
            raise OSError("Received max length datagram")
        print("data received on primary_wan_socket from", server_ip, server_port)
        
        len_sent = app_socket.sendto(datagram[1:], (app_ip, app_port))
        if len_sent < len(datagram) - 1:
            print("len_sent", len_sent, "datagram", len(datagram))
            raise OSError("len_sent not equal to datagram - 1")
        print("data sent on app_socket to", app_ip, app_port)
