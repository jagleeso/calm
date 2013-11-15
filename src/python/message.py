import json
import struct
import logging

import logconfig
logger = logging.getLogger(__name__)

def serialize_msg(msg):
    return json.dumps(msg)

def deserialize_msg(msg):
    return json.loads(msg)

def _check_cmd(cmd):
    assert type(cmd) == list and cmd[0][0] == 'cmd'
    pass

def send_cmd(socket, cmd):
    _check_cmd(cmd)
    msg = serialize_msg(cmd)
    return send(socket, msg)

def recv_cmd(socket):
    msg = recv(socket)
    cmd = deserialize_msg(msg)
    _check_cmd(cmd)
    return cmd

"""
Use a dumb protocol for sending fixed size messages:
1. send size of msg (4 bytes)
1. send msg
"""

# Number of bytes in msg length size.
MSG_SIZE_BYTES = 4

def send(socket, msg):
    length = len(msg)
    # pack as 4 bytes
    packed = struct.pack("I", length)
    logger.info("SEND: %s", msg)
    socket.send(packed)
    return socket.send(msg)

def recv(socket):
    packed = socket.recv(MSG_SIZE_BYTES)
    length = struct.unpack("I", packed)[0]
    msg = socket.recv(length)
    logger.info("RECV %s: %s", length, msg)
    return msg

def recv_msg(socket):
    return deserialize_msg(recv(socket))

def send_msg(socket, data):
    return send(socket, serialize_msg(data))
