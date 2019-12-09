import asyncio
import json
import logging
import logging.handlers
import platform
import subprocess
import time

from pythonjsonlogger import jsonlogger
import sentry_sdk
import yaml

from rest_wrappers import TeleRequester


class Pinger:
    def __init__(self, ip, handle, frequency, persisted):
        self.logger = logging.getLogger(__name__)
        self.ip = ip
        self.handle = handle
        self.frequency = frequency
        self.status = persisted[0]
        self.last_status_change = persisted[1]

    def ping(self, ip):
        if platform.system().lower() == 'windows':
            param = '-n'
        else:
            param = '-c'
        command = ['ping', param, '1', ip]
        return subprocess.call(command) == 0

    async def run(self):
        first_run = True
        while True:
            loop = asyncio.get_event_loop()
            future = loop.run_in_executor(None, self.ping, self.ip)
            response = await future
            if response:
                if self.status:
                    self.logger.debug('Server is online', extra={'type': 'Status', 'ip': self.ip})
                elif not self.status and first_run:
                    self.status = True
                    self.logger.debug('Server is online', extra={'type': 'Status', 'ip': self.ip})
                elif not self.status and not first_run:
                    self.status = True
                    self.last_status_change = time.time()
                    self.logger.debug('Server went online', extra={'type': 'Status', 'ip': self.ip})
            else:
                if not self.status:
                    self.logger.debug('Server is offline', extra={'type': 'Status', 'ip': self.ip})
                elif not self.status and first_run:
                    self.status = False
                    self.logger.debug('Server is offline', extra={'type': 'Status', 'ip': self.ip})
                elif self.status and not first_run:
                    self.status = False
                    self.last_status_change = time.time()
                    self.logger.debug('Server went offline', extra={'type': 'Status', 'ip': self.ip})
            first_run = False
            await asyncio.sleep(self.frequency)


def main():
    def send(message, recipients):
        if not isinstance(recipients, list):
            recipients = [recipients, ]
        for recipient in recipients:
            telegram.send_message(recipient, message)
            logger.debug(f'Message \'{message}\' sent to {recipient}', extra={'type': 'Output'})

    async def run_telegram_watcher():
        await asyncio.sleep(5)
        host_states = {}
        for pinger in pinger_stack:
            host_states[pinger.handle] = persisted_statuses[pinger.handle][0]

        while True:
            loop = asyncio.get_event_loop()
            future = loop.run_in_executor(None, telegram.get_updates)
            response = await future
            if response:
                for item in response['result']:
                    user_id = item['message']['from']['id']
                    message_text = item['message']['text']
                    process_telegram_command(message_text, user_id)
                    telegram.clear_updates(item['update_id']+1)

            for pinger in pinger_stack:
                if pinger.status != host_states[pinger.handle]:
                    if pinger.status is False:
                        if time.time() - pinger.last_status_change >= report_delay:
                            send(f'{report_delay/60} минут назад пропало соединение с роутером \'{pinger.handle}\'', recipients)
                            host_states[pinger.handle] = pinger.status
                            persist_reported_statuses(host_states)
                    else:
                        send(f'Соединение с роутером \'{pinger.handle}\' восстановлено', recipients)
                        host_states[pinger.handle] = pinger.status
                        persist_reported_statuses(host_states)

            await asyncio.sleep(poll_frequency)

    def process_telegram_command(command, user_id):
        if user_id not in recipients:
            if command.lower() == f'регистрация {reg_pin}':
                recipients.append(user_id)
                logger.info(f'Temporary registration granted to user {user_id}', extra={'type': 'Input', 'user_id': user_id})
                send('Временная регистрация завершена', user_id)
                return
            else:
                return

        if command.lower() == 'статус':
            logger.debug(f'Status request from {user_id}', extra={'type': 'Input', 'user_id': user_id})
            for pinger in pinger_stack:
                if pinger.status:
                    status = 'есть связь'
                else:
                    status = 'нет связи'
                send(f'{pinger.handle}: {status}', user_id)

    def persist_reported_statuses(host_states):
        export = json.dumps(host_states)
        with open(persist_file, 'w') as output:
            output.write(export)

    with open('config.yaml') as cfgfile:
        cfg = yaml.safe_load(cfgfile)

    # Setup sentry.io reporting
    sentry_dsn = cfg['debug']['sentry dsn']
    sentry_app_name = cfg['debug']['sentry appname']
    sentry_environment = cfg['debug']['sentry environment']
    sentry_sdk.init(sentry_dsn, release=sentry_app_name, environment=sentry_environment)

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
    reg_pin = cfg['telegram']['pin']
    poll_frequency = cfg['telegram']['poll frequency']
    telegram = TeleRequester(token, proxies=proxy)
    try:
        if not telegram.self_test():
            logger.error('Error setting up telegram connection', extra={'type': 'Startup'})
    except:
        logger.error('Error setting up telegram connection', extra={'type': 'Startup'})
        quit()

    # Set pinger mode
    ips = cfg['pinger']['ips']
    handles = cfg['pinger']['handles']
    locations = zip(ips, handles)
    ping_frequency = cfg['pinger']['frequency']
    report_delay = cfg['pinger']['report failure delay']
    initial_delay = cfg['pinger']['initial delay']
    persist_file = 'reported.json'

    # Load persisted report statuses from the last session
    try:
        with open(persist_file) as inp:
            persisted_statuses = json.loads(inp)[0]
    except:
        persisted_statuses = {}
        for handle in handles:
            persisted_statuses[handle] = [True, '']

    # Delay execution, give vpn clients some time to reconnect after server reboot
    time.sleep(initial_delay)

    # Spawn a pinger for every ip
    pinger_stack = []
    for location in locations:
        ip = location[0]
        handle = location[1]
        pinger_stack.append(Pinger(ip, handle, ping_frequency, persisted_statuses[handle]))

    # WRYYYYY
    loop = asyncio.get_event_loop()
    for pinger in pinger_stack:
        loop.create_task(pinger.run())
    loop.create_task(run_telegram_watcher())
    loop.run_forever()


if __name__ == '__main__':
    main()
