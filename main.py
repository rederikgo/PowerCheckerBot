import logging
import logging.handlers
import platform
import subprocess
import time

import yaml

from rest_wrappers import TeleRequester


def ping(host):
    if platform.system().lower() == 'windows':
        param = '-n'
    else:
        param = '-c'
    command = ['ping', param, '1', host]
    return subprocess.call(command) == 0


def main():
    def send(message):
        for recipient in recipients:
            telegram.send_message(recipient, message)
            logger.debug(f'Message {message} sent to {recipient}')

    with open('config.yaml') as cfgfile:
        cfg = yaml.safe_load(cfgfile)

    # Setup logging
    logging_level = cfg['debug']['debug level']
    formatter = logging.Formatter('%(asctime)s: %(message)s')

    handler = logging.handlers.RotatingFileHandler('powerchecker.log', mode='a', maxBytes=10485760, backupCount=0,
                                                   encoding='utf-8')
    handler.setLevel(logging_level)
    handler.setFormatter(formatter)

    logger = logging.getLogger(__name__)
    logger.setLevel(logging_level)
    logger.addHandler(handler)
    logger.info('')
    logger.info('Session started')

    # Init telegram connection
    token = cfg['telegram']['token']
    proxy = {'https': cfg['telegram']['proxy']}
    recipients = cfg['telegram']['recipients']
    telegram = TeleRequester(token, proxies=proxy)
    try:
        if not telegram.self_test():
            logger.error('Error setting up telegram connection')
    except:
        logger.error('Error setting up telegram connection')
        quit()

    # Set pinger mode
    host = cfg['pinger']['ip']
    frequency = cfg['pinger']['frequency']
    report_delay = cfg['pinger']['report failure delay']

    failure_reported = ''
    went_offline = ''
    while 1:
        base_time = time.time()
        if ping(host):
            is_online = True
            logger.debug('Server is online')
            went_offline = ''
            if failure_reported:
                message = 'Соединение с роутером восстановлено'
                send(message)
                failure_reported = ''
                logger.info('Server is online again!')
        else:
            is_online = False
            if not went_offline:
                logger.info('Server went offline!')
                went_offline = time.time()
            else:
                logger.debug('Server is offline')

        if went_offline and not failure_reported and time.time() > went_offline + report_delay:
            message = f'{report_delay/60} минут назад пропало соединение с вашим роутером'
            send(message)
            logger.info('Failure reported to telegram recipients')
            failure_reported = time.time()

        if time.time() < base_time + frequency:
            time.sleep(base_time + frequency - time.time())


if __name__ == '__main__':
    main()