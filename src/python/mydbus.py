# import subprocess
# from StringIO import StringIO

import procutil

import logging
import logconfig
logger = logging.getLogger(__name__)

class WrappedCalledProcessError(Exception):
    pass

def send_dbus(service, path, method, args=[]):
    """
    So basically, I can't figure out threading with dbus in python, so just invoke qdbus command line program instead to send a reply...

    qdbus im.pidgin.purple.PurpleService /im/pidgin/purple/PurpleObject im.pidgin.purple.PurpleInterface.PurpleConvIm $conversation
    qdbus im.pidgin.purple.PurpleService /im/pidgin/purple/PurpleObject im.pidgin.purple.PurpleInterface.PurpleConvImSend $convIMResult 'hello world'
    """
    cmd = ["qdbus", service, path, method] + [str(a) for a in args]
    return procutil.call(cmd)

# def send_dbus(service, path, method, args=[]):
#     """
#     So basically, I can't figure out threading with dbus in python, so just invoke qdbus command line program instead to send a reply...
# 
#     qdbus im.pidgin.purple.PurpleService /im/pidgin/purple/PurpleObject im.pidgin.purple.PurpleInterface.PurpleConvIm $conversation
#     qdbus im.pidgin.purple.PurpleService /im/pidgin/purple/PurpleObject im.pidgin.purple.PurpleInterface.PurpleConvImSend $convIMResult 'hello world'
#     """
#     # stderr = StringIO()
#     # stdout = StringIO()
#     try:
#         cmd = ["qdbus", service, path, method] + [str(a) for a in args]
#         return subprocess.check_output(cmd)
#         # result = subprocess.check_output(cmd, stderr=stderr, stdout=stdout)
#         # stderr.close()
#         # stdout.close()
#         # return stdout.getvalue()
#     except subprocess.CalledProcessError as e:
#         # stderr.close()
#         # stdout.close()
#         cmd_str = " ".join(cmd)
#         exit_code = e.returncode
#         # stderr_str = stderr.getvalue()
#         stderr_str = e.output
#         raise WrappedCalledProcessError("Failed to execute \"{cmd_str}\" (exit code {exit_code}).  Standard error was:\n{stderr_str}".format(**locals()))
