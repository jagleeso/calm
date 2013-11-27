import json
import struct
import logging
from StringIO import StringIO

import logconfig
logger = logging.getLogger(__name__)

def serialize_msg(msg):
    return json.dumps(msg)

def deserialize_msg(msg):
    return json.loads(msg)

def is_cmd(cmd):
    return type(cmd) == list and cmd[0][0] == 'cmd'
def is_request(request):
    return type(request) == list and request[0] == 'request'
def is_response(response):
    return type(response) == list and response[0] == 'response'
def is_notification(notification):
    return type(notification) == list and notification[0] == 'notification' and \
            len(notification) == 4 and notification[1] is not None

def _check_valid_cmd(cmd):
    """
    [['cmd', ...], ...]
    """
    return is_cmd(cmd)

def _check_valid_request(request):
    """
    ['request', (('TRACK'), 1)]  
    """
    return is_request(request)

def _check_valid_response(response):
    """
    ['response', 'recorded']  
    """
    return is_response(response)

def _check_valid_candidates(candidates):
    """
    ['candidates', [list of valid args]]
    """
    return type(candidates) == list and candidates[0] == 'candidates' and (
            candidates[1] is None or type(candidates[1]) == list)

def _check_valid_notification(notification):
    """
    ['notification', 'hello', None, None]  
    ['notification', 'hello', 'there', None]  
    ['notification', 'hello', 'there', '/usr/share/icons/hicolor/scalable/apps/application-x-clementine.svg']  
    """
    return is_notification(notification)

# cmdserver stuff

def send_cmd(socket, cmd):
    assert _check_valid_cmd(cmd)
    msg = serialize_msg(cmd)
    return send(socket, msg)

def send_request(socket, request):
    assert _check_valid_request(request)
    msg = serialize_msg(request)
    return send(socket, msg)

def recv_candidates(socket):
    msg = recv(socket)
    candidates = deserialize_msg(msg)
    assert _check_valid_candidates(candidates)
    return candidates

def recv_response(socket):
    msg = recv(socket)
    response = deserialize_msg(msg)
    assert _check_valid_response(response)
    return response

# cmdproc stuff

def send_candidates(socket, candidates):
    assert _check_valid_candidates(candidates)
    msg = serialize_msg(candidates)
    return send(socket, msg)

def recv_cmd(socket):
    msg = recv(socket)
    cmd = deserialize_msg(msg)
    assert _check_valid_cmd(cmd)
    return cmd

def recv_cmd_or_request(socket):
    msg = recv(socket)
    cmd_or_request = deserialize_msg(msg)
    assert _check_valid_cmd(cmd_or_request) or _check_valid_request(cmd_or_request)
    return cmd_or_request

def send_response(socket, response):
    assert _check_valid_response(response)
    msg = serialize_msg(response)
    return send(socket, msg)

# either cmdproc or cmdserver stuff

# TODO: def send_notification(socket, title, message=None, imgpath=None):
def send_notification(socket, notification):
    assert _check_valid_notification(notification)
    msg = serialize_msg(notification)
    return send(socket, msg)

# notify server stuff

def recv_notification(socket):
    msg = recv(socket)
    notification = deserialize_msg(msg)
    assert _check_valid_notification(notification)
    return notification

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

    buf = StringIO()
    l = 0
    while l != length:
        s = socket.recv(length)
        l += len(s)
        buf.write(s)

    msg = buf.getvalue()
    logger.info("RECV %s: %s", length, msg)
    return msg

def recv_msg(socket):
    return deserialize_msg(recv(socket))

def send_msg(socket, data):
    return send(socket, serialize_msg(data))
