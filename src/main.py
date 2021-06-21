'''
Detailed documentation of Slack Incoming Webhooks:
https://api.slack.com/incoming-webhooks
Set the webhook_url to the one provided by Slack when you create the webhook at https://my.slack.com/services/new/incoming-webhook/
'''
import json
from os import getenv
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

def mkfmt(wide :int) -> str:
    return '{:<'+str(wide)+'}'

def linode_event_to_table(data: dict, wide :int = 50) -> str:
    right_fmt = '{:>}'
    text = ''

    pk :int = data.get('id')
    action :str = data.get('action')
    created :str = data.get('created')
    status :str = data.get('status')
    username :str = data.get('username')
    message :str = data.get('message', '')
    entity :dict = data.get('entity')

    text += mkfmt(wide+2).format('*Action:*') + right_fmt.format('*When:*') + "\n"
    text += mkfmt(wide).format(action.strip()) + right_fmt.format(created.strip()) + "\n"
    text += mkfmt(wide+2).format('*Status:*') + right_fmt.format('*ID:*') + "\n"
    # Status: failed finished notification scheduled started
    if status == 'finished':
        status = f':white_check_mark: Finished'
        text += mkfmt(wide+14).format(status) + right_fmt.format(pk) + "\n"
    if status == 'notification':
        status = f':warning: Notification'
        text += mkfmt(wide+5).format(status) + right_fmt.format(pk) + "\n"

    text += mkfmt(wide+2).format('*Username:*') + right_fmt.format('*Message:*') + "\n"
    text += mkfmt(wide).format(username.strip()) + right_fmt.format(message.strip()) + "\n"
    labels = ()
    values = ()
    if entity is not None:
        if entity.get('type'):
            labels = ('*Type:*', '')
            values = (entity.get('type'), '')
        if entity.get('label'):
            labels = ('*Type:*', '*Label:*')
            values = (entity.get('type'), entity.get('label'))
    if labels:
        left, right = labels
        text += mkfmt(wide+2).format(left) + right_fmt.format(right) + "\n"
    if values:
        left, right = values
        text += mkfmt(wide).format(left) + right_fmt.format(right) + "\n"

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
            post_to_slack(linode_event_to_table(result))

    conn.close()

if __name__ == '__main__':
    main()
