"""REST API wrappers

Wrappers for Telegram, Last.fm(in future) and Discogs(in future) APIs

"""
import logging
import sys
import time

import requests


# Wrapper parent class
class Requester:
    def __init__(self, token, proxies={}, rate_limit=1, error_retries=3):
        # Setup logging
        self.logger = logging.getLogger(__name__)

        self.token = token
        self.headers = {'User-Agent': 'PowerChecker/alpha'}
        self.proxies = proxies

        self.error_retries = error_retries
        self.rate_limit = rate_limit

        self.request_time = 0

    # Get url via requests. Return response with status 200 or raise an error
    def _get_url(self, url, params={}):
        for _ in range(self.error_retries):
            self._request_throttle()
            self.request_time = time.time()
            try:
                response = requests.get(url, headers=self.headers, proxies=self.proxies, params=params)
                self.last_response = response
                if response.status_code == 200:
                    self.logger.debug('{}: {}'.format(response.status_code, url))
                    return response.json()
                else:
                    self.logger.warning('{}: {}'.format(response.status_code, url))
            except:
                self.logger.error('{} on {}'.format(sys.exc_info(), url))
        else:
            self.logger.error('Too many request errors in a row')
            raise UserWarning('Too many request errors in a row')

    # Rate limiter, no more than n requests per second
    def _request_throttle(self):
        n = self.rate_limit
        since_last_request = time.time() - self.request_time
        if since_last_request < 1/n:
            time.sleep(1/n - since_last_request)


# Telegram wrapper subclass
class TeleRequester(Requester):
    api_endpoint = 'https://api.telegram.org'

    # Construct url string from parameters
    def _make_url(self, method):
        url = '/'.join([self.api_endpoint, 'bot' + self.token, method])
        return url

    # Check and report response status
    def _check_response_status(self, response):
        if response['ok'] is True:
            return True
        else:
            return False

    # Self-test bot, return status
    def self_test(self):
        url = self._make_url('getMe')
        response = self._get_url(url)
        return self._check_response_status(response)

    # Send specified message to the specified chat, return status
    def send_message(self, chat_id, text):
        method = 'sendMessage'
        params = {
            'chat_id': chat_id,
            'text': text
        }
        url = self._make_url(method)
        response = self._get_url(url, params=params)
        return self._check_response_status(response)

    # Get updates
    def get_updates(self):
        url = self._make_url('getUpdates')
        return self._get_url(url)

    # Clear updates
    def clear_updates(self, offset):
        method = 'getUpdates'
        params = {
            'offset': offset
        }
        url = self._make_url(method)
        response = self._get_url(url, params=params)
        return self._check_response_status(response)