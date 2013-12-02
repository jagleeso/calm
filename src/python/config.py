import config
import os

ROOT = os.path.abspath(os.path.join(os.path.basename(config.__file__), '..'))
RESOURCE = os.path.join(ROOT, 'resource')
IMG = os.path.join(RESOURCE, 'img')

DEFAULT_CMDSERVER_PORT = 2525
DEFAULT_NOTIFY_PORT = 2526
DEFAULT_CONTEXT_PORT = 2527
DEFAULT_STATUS_PORT = 2528
DEFAULT_HOST = 'localhost'

NOTIFY_CONNECT_RETRY_TIMEOUT = 0.5
# If a notification arrives within this many seconds of the last, append it to the previous 
# notification (using it's image), otherwise make a new one.
NOTIFY_APPEND_TIME = 2
