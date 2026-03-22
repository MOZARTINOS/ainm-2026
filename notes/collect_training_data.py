#!/usr/bin/env python3
"""Collect n8n execution logs and save as training data."""
import urllib.request
import json
import sys
import os
import time

sys.stdout.reconfigure(encoding='utf-8')

SELF_HOSTED_KEY = 'YOUR_JWT_TOKEN_HERE'
CLOUD_KEY = 'YOUR_JWT_TOKEN_HERE'

SERVERS = [
    ('self-hosted', 'https://n8n.visam.no/api/v1', SELF_HOSTED_KEY, 'WK54ADS72hF36hg2'),
    ('cloud', 'https://mozartino.app.n8n.cloud/api/v1', CLOUD_KEY, 'AEH07Hs5Vl37N2PZ'),
]

OUTPUT_PATH = r'F:\Workfolder\NM i AI main\repo\notes\training_data.jsonl'
SUMMARY_PATH = r'F:\Workfolder\NM i AI main\repo\notes\training_data_summary.md'


def api_get(base, path, key):
    url = f'{base}{path}'
    req = urllib.request.Request(url, headers={'X-N8N-API-KEY': key})
    resp = urllib.request.urlopen(req, timeout=60)
    return json.loads(resp.read())


def get_all_execution_ids(base, key, workflow_id):
    ids = []
    cursor = None
    while True:
        path = f'/executions?workflowId={workflow_id}&limit=100'
        if cursor:
            path += f'&cursor={cursor}'
        data = api_get(base, path, key)
        batch = data.get('data', [])
        for ex in batch:
            ids.append((ex['id'], ex['status']))
        print(f'  Fetched {len(batch)} executions (total: {len(ids)})', flush=True)
        cursor = data.get('nextCursor')
        if not cursor or not batch:
            break
    return ids


def extract_training_record(base, key, exec_id, exec_status, source):
    try:
        data = api_get(base, f'/executions/{exec_id}?includeData=true', key)
    except Exception as e:
        return None

    exec_data = data.get('data', {})
    result_data = exec_data.get('resultData', {})
    runs = result_data.get('runData', {})

    if not runs:
        return None

    # Extract prompt and files from webhook node
    prompt = ''
    n_files = 0
    file_names = []

    webhook_node = runs.get('Receive Task') or runs.get('Webhook') or runs.get('webhook')
    if webhook_node:
        try:
            items = webhook_node[0]['data']['main'][0]
            if items:
                body = items[0].get('json', {}).get('body', {})
                prompt = body.get('prompt', '') or body.get('task', '') or ''
                files = body.get('files', [])
                if isinstance(files, list):
                    n_files = len(files)
                    file_names = [f.get('name', f.get('filename', '')) for f in files if isinstance(f, dict)]
        except (IndexError, KeyError, TypeError):
            pass

    if not prompt:
        return None

    # Extract debug info from agent node
    task_type = ''
    extracted_params = {}
    success = False
    results = []

    agent_node = runs.get('Tripletex Agent') or runs.get('Code') or runs.get('Agent')
    if agent_node:
        try:
            items = agent_node[0]['data']['main'][0]
            if items:
                json_data = items[0].get('json', {})
                debug = json_data.get('_debug', {})
                task_type = debug.get('task_type', '')
                extracted_params = debug.get('extracted_params', {}) or {}
                success = debug.get('success', False)
                results = debug.get('results', [])
        except (IndexError, KeyError, TypeError):
            pass

    # Count API call results
    n_api_calls = 0
    n_ok = 0
    n_errors = 0

    if isinstance(results, list):
        for r in results:
            if isinstance(r, dict):
                n_api_calls += 1
                if r.get('ok', False):
                    n_ok += 1
                else:
                    n_errors += 1

    if n_api_calls == 0 and exec_status == 'error':
        success = False

    record = {
        'exec_id': exec_id,
        'source': source,
        'timestamp': data.get('startedAt', ''),
        'task': prompt,
        'task_type': task_type or '',
        'params': extracted_params if isinstance(extracted_params, dict) else {},
        'n_files': n_files,
        'file_names': file_names,
        'success': bool(success),
        'n_api_calls': n_api_calls,
        'n_ok': n_ok,
        'n_errors': n_errors,
        'exec_status': exec_status,
    }

    return record


# Main collection
all_records = []

for source, base, key, wf_id in SERVERS:
    print(f'\n=== Collecting from {source} ({base}) ===', flush=True)

    try:
        exec_list = get_all_execution_ids(base, key, wf_id)
    except Exception as e:
        print(f'  ERROR listing executions: {e}', flush=True)
        continue

    print(f'  Total executions: {len(exec_list)}', flush=True)

    for i, (eid, estatus) in enumerate(exec_list):
        try:
            record = extract_training_record(base, key, eid, estatus, source)
            if record:
                all_records.append(record)
        except Exception as e:
            print(f'  ERROR on {eid}: {e}', flush=True)

        if (i + 1) % 50 == 0:
            print(f'  Processed {i+1}/{len(exec_list)} ({len(all_records)} valid records)', flush=True)

        time.sleep(0.05)

    print(f'  Done: {len(all_records)} total valid records so far', flush=True)

# Save JSONL
os.makedirs(os.path.dirname(OUTPUT_PATH), exist_ok=True)
with open(OUTPUT_PATH, 'w', encoding='utf-8') as f:
    for r in all_records:
        f.write(json.dumps(r, ensure_ascii=False) + '\n')

print(f'\nSaved {len(all_records)} records to {OUTPUT_PATH}', flush=True)

# Generate summary
task_type_counts = {}
success_counts = {'true': 0, 'false': 0}
source_counts = {}
total_api_calls = 0
total_ok = 0
total_errors = 0
file_counts = {'with_files': 0, 'without_files': 0}

for r in all_records:
    tt = r['task_type'] or 'unknown'
    task_type_counts[tt] = task_type_counts.get(tt, 0) + 1

    if r['success']:
        success_counts['true'] += 1
    else:
        success_counts['false'] += 1

    src = r['source']
    source_counts[src] = source_counts.get(src, 0) + 1

    total_api_calls += r['n_api_calls']
    total_ok += r['n_ok']
    total_errors += r['n_errors']

    if r['n_files'] > 0:
        file_counts['with_files'] += 1
    else:
        file_counts['without_files'] += 1

# Per task_type success rate
task_type_success = {}
for r in all_records:
    tt = r['task_type'] or 'unknown'
    if tt not in task_type_success:
        task_type_success[tt] = {'ok': 0, 'fail': 0}
    if r['success']:
        task_type_success[tt]['ok'] += 1
    else:
        task_type_success[tt]['fail'] += 1

n_total = max(len(all_records), 1)
summary = f"""# Training Data Summary

Generated: {time.strftime('%Y-%m-%d %H:%M:%S')}

## Overview
- **Total records**: {len(all_records)}
- **Sources**: {', '.join(f'{k}: {v}' for k, v in sorted(source_counts.items()))}
- **Success rate**: {success_counts['true']}/{len(all_records)} ({100*success_counts['true']/n_total:.1f}%)
- **With files**: {file_counts['with_files']}, Without files: {file_counts['without_files']}

## API Call Stats
- **Total API calls**: {total_api_calls}
- **Successful**: {total_ok} ({100*total_ok/max(total_api_calls,1):.1f}%)
- **Errors**: {total_errors} ({100*total_errors/max(total_api_calls,1):.1f}%)
- **Avg calls/execution**: {total_api_calls/n_total:.1f}

## Task Type Distribution

| Task Type | Count | Success | Fail | Rate |
|-----------|-------|---------|------|------|
"""

for tt in sorted(task_type_success.keys(), key=lambda x: task_type_success[x]['ok']+task_type_success[x]['fail'], reverse=True):
    s = task_type_success[tt]
    total = s['ok'] + s['fail']
    rate = 100 * s['ok'] / max(total, 1)
    summary += f"| {tt} | {total} | {s['ok']} | {s['fail']} | {rate:.0f}% |\n"

if all_records:
    sample = json.dumps(all_records[0], indent=2, ensure_ascii=False)
    if len(sample) > 800:
        sample = sample[:800] + '\n  ...\n}'
else:
    sample = '{}'

summary += f"\n## File Format\n\nEach line in `training_data.jsonl` is a JSON object:\n```json\n{sample}\n```\n"

with open(SUMMARY_PATH, 'w', encoding='utf-8') as f:
    f.write(summary)

print(f'Saved summary to {SUMMARY_PATH}', flush=True)
print('DONE', flush=True)
