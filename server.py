import socket
import select
import sys

SERVER_LISTEN_PORT = int(sys.argv[1])
APP_LISTEN_PORT = int(sys.argv[2])
primary_client_ip = None
primary_client_port = None

socket.setdefaulttimeout(0)

app_socket = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)

wan_socket = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
wan_socket.bind(("", SERVER_LISTEN_PORT))

while True:
    sockets = [app_socket, wan_socket]
    (read, write, exceptional) = select.select(sockets, [], sockets)
    if exceptional:
        raise OSError
        
    if app_socket in read:
        (data, (app_ip, app_port)) = app_socket.recvfrom(4096)
        print("data received on app_socket from", app_ip, app_port)
        if primary_client_ip and primary_client_port:
            wan_socket.sendto(bytes([1]) + data, (primary_client_ip, primary_client_port))
            print("data sent on wan_socket to primary client address", primary_client_ip, primary_client_port)
            # TODO implement sending to secondary address
        else:
            print("primary client address not set yet, dropping data")
        
    if wan_socket in read:
        # assuming data comes from client. TODO guard against non-client
        (datagram, (remote_ip, remote_port)) = app_socket.recvfrom(4096)
        print("data received on wan_socket from", remote_ip, remote_port)
        # determine if data comes from primary or secondary socket
        if datagram[0] == 1:
            # data is from primary socket
            primary_client_ip = remote_ip
            primary_client_port = remote_port
            data = datagram[1:]
            app_socket.sendto(data, ("127.0.0.1", APP_LISTEN_PORT))
            print("data is from primary client address, sent on app_socket")
        # elif datagram[0] == 0:
            # data is from secondary socket
            # TODO implement this
        else:
            print("ignoring non-client datagram, datagram[0]==", datagram[0])