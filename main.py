import asyncio
import logging
import logging.handlers
import platform
import subprocess
import time

import yaml

from rest_wrappers import TeleRequester
from pythonjsonlogger import jsonlogger

def main():
    def ping(host):
        if platform.system().lower() == 'windows':
            param = '-n'
        else:
            param = '-c'
        command = ['ping', param, '1', host]
        return subprocess.call(command) == 0

    def send(message, recipients):
        for recipient in recipients:
            telegram.send_message(recipient, message)
            logger.debug(f'Message \'{message}\' sent to {recipient}', extra={'type': 'Output'})

    async def pinger():
        failure_reported = ''
        went_offline = ''
        global is_online
        while True:
            loop = asyncio.get_event_loop()
            future = loop.run_in_executor(None, ping, host)
            response = await future
            base_time = time.time()
            if response:
                is_online = True
                logger.debug('Server is online', extra={'type': 'Status'})
                went_offline = ''
                if failure_reported:
                    message = 'Соединение с роутером восстановлено'
                    send(message, recipients)
                    failure_reported = ''
                    logger.info('Server is online again!', extra={'type': 'Status'})
            else:
                is_online = False
                if not went_offline:
                    logger.info('Server went offline!', extra={'type': 'Status'})
                    went_offline = time.time()
                else:
                    logger.debug('Server is offline', extra={'type': 'Status'})

            if went_offline and not failure_reported and time.time() > went_offline + report_delay:
                message = f'{round(report_delay / 60)} минут назад пропало соединение с вашим роутером'
                send(message, recipients)
                logger.info('Failure reported to telegram recipients', extra={'type': 'Output'})
                failure_reported = time.time()

            if time.time() < base_time + frequency:
                await asyncio.sleep(base_time + frequency - time.time())

    async def telegram_watcher():
        await asyncio.sleep(5)
        while True:
            loop = asyncio.get_event_loop()
            future = loop.run_in_executor(None, telegram.get_updates)
            response = await future
            if response:
                for item in response['result']:
                    user_id = item['message']['from']['id']
                    if user_id not in recipients:
                        logger.info(f'New user request: {user_id}', extra={'type': 'Input'})
                    else:
                        message_text = item['message']['text']
                        if message_text.lower() == 'статус':
                            logger.debug(f'Status request from {user_id}', extra={'type': 'Input', 'user_id': user_id})
                            if is_online:
                                message = 'Роутер работает'
                                send(message, (user_id, ))
                            else:
                                message = 'Роутер не работает'
                                send(message, (user_id, ))

                    telegram.clear_updates(item['update_id']+1)

            await asyncio.sleep(poll_frequency)

    with open('config.yaml') as cfgfile:
        cfg = yaml.safe_load(cfgfile)

    # Setup logging
    logging_level = cfg['debug']['debug level']
    formatter = jsonlogger.JsonFormatter('%(asctime)s %(levelname)s: %(message)s')

    handler = logging.handlers.RotatingFileHandler('powerchecker.log', mode='a', maxBytes=10485760, backupCount=0,
                                                   encoding='utf-8')
    handler.setLevel(logging_level)
    handler.setFormatter(formatter)

    logger = logging.getLogger(__name__)
    logger.setLevel(logging_level)
    logger.addHandler(handler)
    logger.info('Session started', extra={'type': 'Startup'})

    # Init telegram connection
    token = cfg['telegram']['token']
    proxy = {'https': cfg['telegram']['proxy']}
    recipients = cfg['telegram']['recipients']
    poll_frequency = cfg['telegram']['poll frequency']
    telegram = TeleRequester(token, proxies=proxy)
    try:
        if not telegram.self_test():
            logger.error('Error setting up telegram connection', extra={'type': 'Startup'})
    except:
        logger.error('Error setting up telegram connection', extra={'type': 'Startup'})
        quit()

    # Set pinger mode
    host = cfg['pinger']['ip']
    frequency = cfg['pinger']['frequency']
    report_delay = cfg['pinger']['report failure delay']
    initial_delay = cfg['pinger']['initial delay']

    # Delay execution, give vpn clients some time to reconnect after server reboot
    time.sleep(initial_delay)

    # WRYYYYY
    loop = asyncio.get_event_loop()
    loop.create_task(pinger())
    loop.create_task(telegram_watcher())
    loop.run_forever()


if __name__ == '__main__':
    main()