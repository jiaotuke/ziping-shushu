"""Publish a public-only release over the configured SSH connection; never push Git."""
from __future__ import annotations
import argparse
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import re
import shlex
import subprocess
from prepare_cloud_release import build, ROOT


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--apply', action='store_true', help='Upload and activate the public release')
    parser.add_argument('--harden', action='store_true', help='Apply the reviewed security gateway configuration')
    args = parser.parse_args()
    if not args.apply:
        parser.error('使用 --apply 明确执行云端代码发布；仅准备源码请运行 prepare_cloud_release.py。')
    record_path = ROOT / '.local/cloud-ssh/aliyun-deployment.json'
    record = json.loads(record_path.read_text(encoding='utf-8-sig'))
    alias, domain = record['ssh_alias'], record['domain']
    if not re.fullmatch(r'[a-zA-Z0-9_-]+', alias) or not re.fullmatch(r'[a-z0-9.-]+', domain):
        raise ValueError('Invalid private deployment configuration')
    release, archive = build()
    digest = hashlib.sha256(archive.read_bytes()).hexdigest()
    config = str(ROOT / '.local/cloud-ssh/ssh_config')
    subprocess.run(['ssh', '-F', config, alias, 'mkdir -p /root/ziping-incoming /root/ziping-maintenance'], check=True)
    remote_archive = '/root/ziping-incoming/' + archive.name
    subprocess.run(['scp', '-F', config, str(archive), alias + ':' + remote_archive], check=True)
    helper = ROOT / 'deploy/public-site/maintenance/deploy_release.py'
    subprocess.run(['scp', '-F', config, str(helper), alias + ':/root/ziping-maintenance/deploy_release.py'], check=True)
    remote_arguments=['python3', '/root/ziping-maintenance/deploy_release.py', '--archive', remote_archive,
                      '--sha256', digest, '--domain', domain]
    if args.harden:
        caddy=(ROOT/'deploy/public-site/Caddyfile').read_text(encoding='utf-8').replace('{$SITE_HOST}',domain)
        caddy+='\nwww.'+domain+' {\n    header -Server\n    redir https://'+domain+'{uri} permanent\n}\n'
        candidate=release/'Caddyfile.security.runtime'
        candidate.write_text(caddy,encoding='utf-8')
        remote_caddy='/root/ziping-incoming/'+release.name+'.Caddyfile'
        subprocess.run(['scp','-F',config,str(candidate),alias+':'+remote_caddy],check=True)
        remote_arguments+=['--security-caddy',remote_caddy]
    command = shlex.join(remote_arguments)
    result = None
    with subprocess.Popen(['ssh', '-F', config, alias, command], stdout=subprocess.PIPE, text=True, encoding='utf-8') as process:
        for line in process.stdout:
            print(line, end='', flush=True)
            if line.startswith('ZIPING_DEPLOY_RESULT='):
                result = json.loads(line.split('=', 1)[1])
        status = process.wait()
    if status or not result or result.get('status') != 'public-https-healthy':
        raise SystemExit('云端发布未通过，未更新本机部署记录；请查看以上错误及云端回滚结果。')
    record.update(status=result['status'], remote_release=result['release'], archive=archive.name,
                  archive_sha256=digest, image_id=result['image_id'], container=result.get('container', 'ziping-public-web-1'),
                  public_database_backup=result['database_backup'], code_deployment_backup=result['operation_directory'],
                  previous_remote_release=result['previous_release'], public_gateway_started=True,
                  application_source_changed=True, original_web_container_unchanged=False,
                  last_checked_utc=datetime.now(timezone.utc).isoformat(timespec='seconds'))
    record_path.write_text(json.dumps(record, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    print('公开网站代码已更新，后台与私有账本仍留在本机。', flush=True)


if __name__ == '__main__':
    main()
