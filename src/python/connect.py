import socket
import time
import os
import errno

import config

import logging
import logconfig
logger = logging.getLogger(__name__)

def connect_to_listener(server, port):
    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    try:
        s.connect((server, port))
    except:
        s.close()
        raise
    return s

def listen_for_client(host, port, server_name='Server', client_name='Client'):
    listen_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    listen_socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    listen_socket.setsockopt(socket.IPPROTO_TCP, socket.TCP_NODELAY, 1)
    listen_socket.bind((host, port))
    listen_socket.listen(1)
    (s, address) = listen_socket.accept()
    listen_socket.close()
    logger.info("%s connected to %s", client_name, server_name)
    return s

def fork_listener(name, path, host, port):
    try:
        pid = os.fork()
    except OSError, e:
        sys.exit(1)
    if pid == 0:
        os.execv(path, [path])
    while True:
        try: 
            sock = connect_to_listener(host, port)
            break
        except (OSError, socket.error) as e:
            if e.errno != errno.ECONNREFUSED:
                raise
        time.sleep(config.NOTIFY_CONNECT_RETRY_TIMEOUT)
            
    logger.info("%s \"%s\" (PID: %s) connected", name, path, pid)
    return (sock, pid)

