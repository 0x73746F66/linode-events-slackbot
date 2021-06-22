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

def post_to_slack(message):
    if proxy_url is None:
        http = urllib3.PoolManager(strict=True)
    else:
        http = urllib3.ProxyManager(proxy_url, cert_reqs='CERT_REQUIRED', ca_certs=certifi.where())
    encoded_data = json.dumps({'text': message}).encode('utf-8')
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

def linode_event_to_table(data: dict) -> str:
    text :str = ''
    pk :str = str(data.get('id'))
    action :str = data.get('action')
    created :str = data.get('created')
    status :str = data.get('status')
    username :str = data.get('username')
    message :str = data.get('message', '')
    entity :dict = data.get('entity')
    label :str = ''
    _type :str = ''
    if entity is not None:
        if entity.get('type'):
            _type = entity.get('type')
        if entity.get('label'):
            label = entity.get('label')
    wide :int = len(max([pk, action, created, status, username, message, _type, label, '     Finished', '     Failed', '     Notification'], key=len))+20
    text += '*Action:*'.ljust(wide-4, ' ') + '*When:*'.ljust(wide, ' ') + "\n"
    text += action.ljust(wide-len(action), ' ') + created.ljust(wide, ' ') + "\n"
    text += '*Status:*'.ljust(wide-3, ' ') + '*ID:*'.ljust(wide, ' ') + "\n"
    # Status: failed finished notification scheduled started
    if status == 'started':
        status = f':checkered_flag: Started'
        text += status.ljust(wide+4, ' ') + pk.ljust(wide, ' ') + "\n"
    if status == 'failed':
        status = f':no_entry: Failed'
        text += status.ljust(wide, ' ') + pk.ljust(wide, ' ') + "\n"
    if status == 'finished':
        status = f':white_check_mark: Finished'
        text += status.ljust(wide+5, ' ') + pk.ljust(wide, ' ') + "\n"
    if status == 'scheduled':
        status = f':watch: Scheduled'
        text += status.ljust(wide-8, ' ') + pk.ljust(wide, ' ') + "\n"
    if status == 'notification':
        status = f':warning: Notification'
        text += status.ljust(wide-6, ' ') + pk.ljust(wide, ' ') + "\n"
    text += '*Username:*'.ljust(wide-8, ' ') + '*Message:*'.ljust(wide, ' ') + "\n"
    text += username.ljust(wide-len(username), ' ') + message.ljust(wide, ' ') + "\n\n"
    if label or _type:
        text += '*Label:*'.ljust(wide-4, ' ') + '*Type:*'.ljust(wide, ' ') + "\n"
        text += label.ljust(wide-len(label), ' ') + _type.ljust(wide, ' ') + "\n"

    return text

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
            post_to_slack(linode_event_to_table(result))
            break

    conn.close()

if __name__ == '__main__':
    main()
