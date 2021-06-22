'''
Detailed documentation of Slack Incoming Webhooks:
https://api.slack.com/incoming-webhooks
Set the webhook_url to the one provided by Slack when you create the webhook at https://my.slack.com/services/new/incoming-webhook/
'''
import json
from os import getenv, stat
from pprint import pprint
from urllib.parse import urlencode
import sqlite3
import urllib3
import certifi


TABLENAME = 'notifications'
proxy_url = getenv('PROXY_URL', default=None)
linode_token = getenv('LINODE_TOKEN')
if not linode_token:
    print('LINODE_TOKEN is empty')
    exit(1)

webhook_url = getenv('SLACK_WEBHOOK_URL')
if not webhook_url:
    print('SLACK_WEBHOOK_URL is empty')
    exit(1)

def get_connection() -> sqlite3.Connection:
    conn = sqlite3.connect("/srv/app/sqlite/linode.db", detect_types=sqlite3.PARSE_DECLTYPES | sqlite3.PARSE_COLNAMES, timeout=10)
    cursor = conn.cursor()
    cursor.execute(f'''
    CREATE TABLE IF NOT EXISTS {TABLENAME} (
        id INTEGER PRIMARY KEY,
        created TEXT,
        action TEXT,
        username TEXT,
        status TEXT,
        label TEXT,
        type TEXT,
        message TEXT
    );''')

    return conn

def query_linode(uri :str, version :str = '/v4', hostname :str = 'api.linode.com', protocol :str = 'https://', parameters :dict = None) -> list:
    query_string = ''
    if parameters is not None:
        query_string = f'?{urlencode(parameters)}'
    query_url = f'{protocol}{hostname}{version}{uri}{query_string}'
    if proxy_url is None:
        http = urllib3.PoolManager(strict=True)
    else:
        http = urllib3.ProxyManager(proxy_url, cert_reqs='CERT_REQUIRED', ca_certs=certifi.where())

    response = http.request("GET", query_url, headers={'Authorization': f'Bearer {linode_token}'})
    if response.status != 200:
        raise ValueError(f'Request to slack returned an error {response.status}, the response is:\n{str(response.data, "utf8")}')

    resp_json = json.loads(str(response.data, 'utf8'))
    if 'errors' in resp_json:
        raise ValueError(json.dumps(resp_json['errors']))

    return resp_json.get('data', [])

def post_to_slack(fields :list, header :str, button_text :str, button_url :str):
    if proxy_url is None:
        http = urllib3.PoolManager(strict=True)
    else:
        http = urllib3.ProxyManager(proxy_url, cert_reqs='CERT_REQUIRED', ca_certs=certifi.where())

    blocks :list = [
        {
            'type': 'header',
            'text': {
                'type': 'plain_text',
                'text': header,
            }
        }, {
            'type': 'divider'
        }, {
            'type': 'section',
            'fields': fields
        }, {
            'type': 'actions',
            'elements': [
                {
                    'type': 'button',
                    "style": "primary",
                    'text': {
                        'type': 'plain_text',
                        'text': button_text
                    },
                    'url': button_url
                }
            ]
        }
    ]
    encoded_data = json.dumps({ 'blocks': blocks }).encode('utf-8')
    response = http.request("POST", webhook_url, body=encoded_data, headers={'Content-Type': 'application/json'})
    if response.status != 200:
        raise ValueError(
            f'Request to slack returned an error {str(response.status)}, the response is:\n{str(response.data)}'
        )

def linode_event_to_row(data: dict) -> tuple:
    entity = data.get('entity')
    return (
        data.get('id'),
        data.get('created'),
        data.get('action'),
        data.get('username'),
        data.get('status'),
        '' if entity is None else entity.get('label', ''),
        '' if entity is None else entity.get('type', ''),
        data.get('message', '')
    )

def parse_linode_event(data: dict) -> str:
    pk :str             = str(data.get('id'))
    action :str         = data.get('action')
    created :str        = data.get('created')
    status :str         = data.get('status')
    username :str       = data.get('username')
    message :str        = data.get('message', '')
    entity :dict        = data.get('entity')
    label :str          = ''
    resource_type :str  = ''
    resource_id :str    = ''
    header :str         = ''
    button_url :str     = 'https://cloud.linode.com/'
    button_text :str    = 'Launch Console'

    if status == 'started':
        header = f':checkered_flag: Started'
    if status == 'failed':
        header = f':no_entry: Failed'
    if status == 'finished':
        header = f':white_check_mark: Finished'
    if status == 'scheduled':
        header = f':watch: Scheduled'
    if status == 'notification':
        header = f':warning: Notification'

    if entity is not None:
        if entity.get('id'):
            resource_id = entity.get('id')
        if entity.get('type'):
            resource_type = entity.get('type')
        if entity.get('label'):
            label = entity.get('label')

    fields :list = []
    fields.append({'type': 'mrkdwn', 'text': f'*Action:*\n{action}'})
    fields.append({'type': 'mrkdwn', 'text': f'*When:*\n{created}'})
    fields.append({'type': 'mrkdwn', 'text': f'*ID:*\n{pk}'})
    fields.append({'type': 'mrkdwn', 'text': f'*Username:*\n{username}'})
    if message:
        fields.append({'type': 'mrkdwn', 'text': f'*Message:*\n{message}'})
    if label:
        fields.append({'type': 'mrkdwn', 'text': f'*Label:*\n{label}'})
    if resource_type:
        fields.append({'type': 'mrkdwn', 'text': f'*Type:*\n{resource_type}'.strip()})
        if resource_type == 'linode':
            button_url = f'https://cloud.linode.com/linodes/{resource_id}'
            button_text = 'View Linode'
        if resource_type == 'user_ssh_key':
            button_url = 'https://cloud.linode.com/profile/keys'
            button_text = 'View SSH Keys'
        if resource_type == 'token':
            button_url = 'https://cloud.linode.com/profile/tokens'
            button_text = 'View API Tokens'
        if resource_type == 'stackscript':
            button_url = f'https://cloud.linode.com/stackscripts/{resource_id}'
            button_text = 'View StackScript'

    post_to_slack(fields, header, button_text, button_url)

def main():
    conn = get_connection()
    cursor = conn.cursor()
    for result in query_linode('/account/events'):
        cursor.execute(f"SELECT * FROM {TABLENAME} WHERE id=? ;", (result.get('id'), ))
        row = cursor.fetchone()
        if row is None:
            cursor.execute(f"INSERT INTO {TABLENAME} VALUES (?,?,?,?,?,?,?,?)", linode_event_to_row(result))
            conn.commit()
        else:
            parse_linode_event(result)
            break

    conn.close()

if __name__ == '__main__':
    main()
