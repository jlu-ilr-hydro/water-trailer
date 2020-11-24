#!/usr/bin/env python3
import requests

from trailer.db.send import collect_update, log_update
from trailer import get_config


conf = get_config()
print('export to ', conf.mirror_db.url)
data, last_export_id, line_count = collect_update(verbose=True)
r = requests.post(url=conf.mirror_db.url,
                  data=data)
if r.text.strip() == str(line_count):
    log_update(last_export_id)
else:
    print('Update was not succesful')
    print(r.text)
