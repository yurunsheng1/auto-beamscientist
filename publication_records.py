"""Read-only verification of report versions against successful GitHub deployments."""
from __future__ import annotations
from pathlib import Path
from datetime import datetime, timezone
import hashlib
import json
import re
import subprocess

ROOT=Path(__file__).resolve().parent
REPOSITORY='yurunsheng1/auto-beamscientist'
RECORDS=ROOT/'data/publication-records.json'
SCHEMA='github-pages-publication-records-v1'

def read_records(path=None):
    source=Path(path) if path else RECORDS
    if not source.exists():return {'schema':SCHEMA,'repository':REPOSITORY,'papers':{}}
    result=json.loads(source.read_text())
    if result.get('schema')!=SCHEMA or result.get('repository')!=REPOSITORY:
        raise ValueError('Unexpected publication record source')
    for entry in result['papers'].values():
        for record in entry['versions']:
            if not re.fullmatch('[0-9a-f]{40}',record['commit_sha']) or not re.fullmatch('[0-9a-f]{64}',record['pdf_sha256']):
                raise ValueError('Invalid publication fingerprint')
            if record.get('state')!='success' or not datetime.fromisoformat(record['published_at_utc'].replace('Z','+00:00')).tzinfo:
                raise ValueError('Publication record needs a successful dated deployment')
            receipt=record.get('github_status_receipt')
            deploy=record.get('github_deployment_receipt')
            if receipt and (receipt['state']!='success' or receipt['created_at']!=record['published_at_utc']):
                raise ValueError('Timestamp does not match the successful GitHub receipt')
            if deploy and (deploy['sha']!=record['commit_sha'] or str(deploy['id'])!=record['deployment_id']):
                raise ValueError('Deployment does not match the recorded source commit')
    return result

def verified_versions(paper,records):
    versions=records.get('papers',{}).get(paper['id'],{}).get('versions',[])
    # A revised PDF cannot inherit verification from a previous file hash.
    current=[r for r in versions if r['pdf_sha256']==paper['sha256'] and r['pdf_path']==paper['pdf']]
    return (min(versions,key=lambda r:r['published_at_utc']) if versions else None,
            min(current,key=lambda r:r['published_at_utc']) if current else None)

def git_file(commit,path):
    result=subprocess.run(['git','show',commit+':'+path],cwd=ROOT,capture_output=True)
    return result.stdout if result.returncode==0 else None

def api(path,paginate=False):
    args=['gh','api']+(['--paginate'] if paginate else [])+[path]
    text=subprocess.check_output(args,cwd=ROOT,text=True)
    decoder=json.JSONDecoder();items=[]
    while text.strip():
        value,end=decoder.raw_decode(text.lstrip());items.extend(value if isinstance(value,list) else [value]);text=text.lstrip()[end:]
    return items

def refresh():
    records=read_records()
    papers=json.loads((ROOT/'data/papers.json').read_text())
    identities={p['id'] for p in papers}
    deployments=api(f'repos/{REPOSITORY}/deployments?environment=github-pages&per_page=100',True)
    for deploy in sorted(deployments,key=lambda d:d['created_at']):
        commit=deploy['sha']
        if not re.fullmatch('[0-9a-f]{40}',commit):continue
        raw=git_file(commit,'data/papers.json')
        if raw is None:continue
        catalog=json.loads(raw);candidates=[]
        for paper in catalog:
            if paper['id'] not in identities:continue
            versions=records['papers'].setdefault(paper['id'],{'versions':[]})['versions']
            if any(r['pdf_sha256']==paper['sha256'] and r['deployment_created_at']<=deploy['created_at'] for r in versions):continue
            pdf=git_file(commit,'dist/'+paper['pdf'])
            if pdf is not None and hashlib.sha256(pdf).hexdigest()==paper['sha256']:candidates.append(paper)
        if not candidates:continue
        statuses=api(f'repos/{REPOSITORY}/deployments/{deploy["id"]}/statuses?per_page=100',True)
        success=[s for s in statuses if s['state']=='success']
        if not success:continue
        status=min(success,key=lambda s:s['created_at'])
        for paper in candidates:
            record={'deployment_id':str(deploy['id']),'commit_sha':commit,
                    'deployment_created_at':deploy['created_at'],'pdf_path':paper['pdf'],
                    'pdf_sha256':paper['sha256'],'published_at_utc':status['created_at'],
                    'status_url':status['url'],'log_url':status.get('log_url'),
                    'environment_url':status.get('environment_url'),'state':'success',
                    'github_deployment_receipt':deploy,'github_status_receipt':status}
            versions=records['papers'][paper['id']]['versions']
            versions[:]=[r for r in versions if r['pdf_sha256']!=paper['sha256']]
            versions.append(record);versions.sort(key=lambda r:r['published_at_utc'])
    # Upgrade seeded records with full API receipts while those records remain available.
    for entry in records['papers'].values():
        for record in entry['versions']:
            if 'github_status_receipt' not in record:
                record['github_status_receipt']=api(record['status_url'])[0]
                record['github_deployment_receipt']=api(f'repos/{REPOSITORY}/deployments/{record["deployment_id"]}')[0]
    RECORDS.write_text(json.dumps(records,indent=2)+'\n')
    print('Verified publication records for',len(identities),'current reports')

if __name__=='__main__':refresh()
