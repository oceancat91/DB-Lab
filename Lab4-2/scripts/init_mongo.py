"""Initialize only the isolated project instance; never touch another MongoDB data path."""
from __future__ import annotations

import argparse
import importlib.metadata
import json
import platform
import time
from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4

from pymongo import MongoClient
from pymongo.errors import OperationFailure


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--port', type=int, default=27084)
    parser.add_argument('--replica-set', default='lab4rs')
    parser.add_argument('--output', default='results/stage2/environment.json')
    args = parser.parse_args()
    root = Path(__file__).resolve().parents[1]
    direct = MongoClient(f'mongodb://127.0.0.1:{args.port}/?directConnection=true', serverSelectionTimeoutMS=15000)
    options = direct.admin.command('getCmdLineOpts')['parsed']
    actual_path = Path(options['storage']['dbPath']).resolve()
    if actual_path != (root / '.runtime/mongo').resolve():
        raise RuntimeError('Port belongs to another MongoDB data directory; no initialization performed')
    try:
        status = direct.admin.command('replSetGetStatus')
        if status['set'] != args.replica_set:
            raise RuntimeError('Unexpected replica set')
    except OperationFailure as exc:
        if exc.code != 94:
            raise
        direct.admin.command('replSetInitiate', {'_id': args.replica_set, 'members': [{'_id': 0, 'host': f'127.0.0.1:{args.port}'}]})
    client = MongoClient(f'mongodb://127.0.0.1:{args.port}/?replicaSet={args.replica_set}', serverSelectionTimeoutMS=30000)
    client.admin.command('ping')
    hello = client.admin.command('hello')
    collection = client.lab4_environment.probe
    token = uuid4().hex
    collection.insert_one({'_id': token, 'stage': 'environment'})
    with client.start_session() as session:
        session.with_transaction(lambda s: collection.update_one({'_id': token}, {'$set': {'transaction': True}}, session=s))
    if collection.find_one({'_id': token}).get('transaction') is not True:
        raise RuntimeError('Transaction capability check failed')
    collection.delete_one({'_id': token})
    evidence = {
        'recorded_at': datetime.now(timezone.utc).isoformat(),
        'python': platform.python_version(), 'platform': platform.platform(),
        'mongodb': client.server_info()['version'], 'replica_set': hello['setName'],
        'is_primary': hello['isWritablePrimary'], 'port': args.port,
        'data_directory': '.runtime/mongo', 'probe_database': 'lab4_environment',
        'transaction_probe': 'PASS',
        'packages': {name: importlib.metadata.version(name) for name in ['fastapi', 'uvicorn', 'pymongo', 'pydantic', 'jinja2', 'httpx', 'pytest', 'python-dotenv']},
        'scope': 'Environment capability only; no application business tests run.'
    }
    output = root / args.output
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(evidence, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    print(json.dumps(evidence, ensure_ascii=False, indent=2))
    client.close()
    direct.close()


if __name__ == '__main__':
    main()
