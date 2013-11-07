import logging.config

# logging.basicConfig(level=logging.INFO)

import logging,sys
formatter = logging.Formatter('%(filename)s:%(lineno)s :: %(message)s')
stdout_handler = logging.StreamHandler(sys.stdout)
stdout_handler.setFormatter(formatter)
logger=logging.getLogger('')
logger.addHandler(stdout_handler)
logger.setLevel(logging.INFO)
# logging.debug('A debug message')
# logging.info('Some information')
# logging.warning('A shot across the bows')
