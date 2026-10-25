"""SSH-only public code deployment. Never expose this as a website endpoint."""
from __future__ import annotations
import argparse
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import re
import shutil
import subprocess
import time
from urllib.request import urlopen
from zipfile import ZipFile

WEB = 'ziping-public-web-1'
GATEWAY = 'ziping-public-gateway-1'
RELEASES = Path('/root/ziping-releases')
MAINTENANCE = Path('/root/ziping-maintenance')
RUNTIME = Path('/root/ziping-runtime')
PRIVATE_NAMES = {'admin_app.py', 'referral_admin_panel.py', 'referral_store.py', 'referral_panel.py', 'referral_cloud_sync.py'}
PRIVATE_NAMES.add('referral_local_backup.py')


def run(args, *, capture=False, cwd=None):
    result = subprocess.run(args, check=True, cwd=cwd, text=True,
                            stdout=subprocess.PIPE if capture else None)
    return result.stdout if capture else None


def inspect(name):
    return json.loads(run(['docker', 'inspect', name], capture=True))[0]


def compose_for(container):
    labels = container['Config']['Labels']
    command = ['docker', 'compose', '-p', 'ziping-public']
    for name in labels['com.docker.compose.project.config_files'].split(','):
        path = Path(name)
        if not path.is_absolute() or not path.is_file():
            raise ValueError('Previous compose configuration is unavailable')
        command += ['-f', str(path)]
    return command + ['--profile', 'https']


def wait_healthy():
    for _ in range(35):
        current = inspect(WEB)
        if current['State'].get('Health', {}).get('Status') == 'healthy':
            return current
        if current['State']['Status'] in ('dead', 'exited'):
            break
        time.sleep(2)
    raise RuntimeError('New public website did not become healthy')


def wait_for_model_requests():
    # Inspect connection counts only, never request contents, provider keys, or
    # another session's report. Require a quiet interval between staged calls.
    program='''from pathlib import Path
n=0
for name in ("/proc/net/tcp","/proc/net/tcp6"):
    for line in Path(name).read_text().splitlines()[1:]:
        row=line.split()
        if row[3]=="01" and int(row[2].split(":")[1],16)==443: n+=1
print(n)
'''
    quiet=None
    for _ in range(64):
        busy=int(run(['docker','exec',WEB,'python','-c',program],capture=True).strip())
        if busy:
            quiet=None
        else:
            quiet=quiet or time.monotonic()
            if time.monotonic()-quiet>=20:
                return
        time.sleep(5)
    raise RuntimeError('Model connections are still active; existing service was left running. Retry after reports finish.')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--archive', type=Path, required=True)
    parser.add_argument('--sha256', required=True)
    parser.add_argument('--domain', required=True)
    parser.add_argument('--security-caddy', type=Path)
    args = parser.parse_args()
    if not re.fullmatch(r'[a-f0-9]{64}', args.sha256) or not re.fullmatch(r'[a-z0-9.-]+', args.domain):
        raise ValueError('Invalid release hash or domain')
    if hashlib.sha256(args.archive.read_bytes()).hexdigest() != args.sha256:
        raise ValueError('Archive hash mismatch')
    old_web, old_gateway = inspect(WEB), inspect(GATEWAY)
    previous_web_command, previous_gateway_command = compose_for(old_web), compose_for(old_gateway)
    with ZipFile(args.archive) as bundle:
        names = bundle.namelist()
        roots = {PurePosixPath(name).parts[0] for name in names}
        if len(roots) != 1 or len(names) != len(set(names)):
            raise ValueError('Invalid archive structure')
        root_name = roots.pop()
        if not re.fullmatch(r'ziping-public-[A-Za-z0-9-]+', root_name):
            raise ValueError('Unexpected release directory')
        manifest = json.loads(bundle.read(root_name + '/manifest.json'))
        if manifest.get('release') != root_name or any(manifest.get(key) is not False for key in (
                'contains_private_ledger', 'contains_demo_data', 'contains_model_keys')):
            raise ValueError('Archive is not marked as a public-only release')
        expected = {root_name + '/' + name for name in manifest['sha256']} | {root_name + '/manifest.json'}
        if set(names) != expected or sum(item.file_size for item in bundle.infolist()) > 32 * 1024 * 1024:
            raise ValueError('Archive contains unlisted files or is too large')
        for item in bundle.infolist():
            path = PurePosixPath(item.filename)
            if path.is_absolute() or '..' in path.parts or '\\' in item.filename or ((item.external_attr >> 16) & 0o170000) == 0o120000:
                raise ValueError('Unsafe archive path')
            if any(part in PRIVATE_NAMES or part in {'.local', '.cache', '.git', '__pycache__'} for part in path.parts):
                raise ValueError('Private management or runtime file in archive')
            if path.name.endswith(('.sqlite', '.sqlite3', '.private.json', '.pem', '.key')):
                raise ValueError('Private data in archive')
            relative = '/'.join(path.parts[1:])
            if relative != 'manifest.json' and hashlib.sha256(bundle.read(item)).hexdigest() != manifest['sha256'][relative]:
                raise ValueError('Source manifest mismatch: ' + relative)
        release = RELEASES / root_name
        release.mkdir(parents=True, exist_ok=False)
        for item in bundle.infolist():
            target = RELEASES / item.filename
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(bundle.read(item))

    stamp = datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S%fZ')
    operation = MAINTENANCE / ('deploy-' + stamp)
    operation.mkdir(parents=True, mode=0o700, exist_ok=False)
    source_caddy = next(Path(m['Source']) for m in old_gateway['Mounts'] if m['Destination'] == '/etc/caddy/Caddyfile')
    RUNTIME.mkdir(mode=0o700, exist_ok=True)
    active_caddy = RUNTIME / 'Caddyfile'
    shutil.copy2(source_caddy, operation / 'Caddyfile.previous')
    if source_caddy.resolve() != active_caddy.resolve():
        shutil.copy2(source_caddy, active_caddy)
    (release / '.env').write_text('SITE_HOST=' + args.domain + '\nZIPING_RELEASE=' + root_name + '\n')
    os.chmod(release / '.env', 0o600)
    # Volume merges are keyed by container target, so this replaces only the Caddyfile bind.
    (release / 'compose.runtime.json').write_text(json.dumps({'services': {'gateway': {
        'volumes': [str(active_caddy) + ':/etc/caddy/Caddyfile:ro']}}}, indent=2))
    command = ['docker', 'compose', '-p', 'ziping-public', '-f', str(release / 'compose.yaml'),
               '-f', str(release / 'compose.runtime.json'), '--profile', 'https']
    run(command + ['config', '--quiet'], cwd=release)
    run(command + ['build', 'web'], cwd=release)
    wait_for_model_requests()
    database_backup = run(['docker', 'exec', WEB, 'python', '/app/maintenance/backup_public.py'], capture=True).strip()
    state = {'status': 'ready-to-switch', 'release': str(release), 'previous_release': old_web['Config']['Labels']['com.docker.compose.project.working_dir'],
             'previous_web_id': old_web['Id'], 'previous_web_image': old_web['Image'], 'archive_sha256': args.sha256,
             'database_backup': database_backup, 'operation_directory': str(operation), 'domain': args.domain}
    state_path = operation / 'operation.json'
    state_path.write_text(json.dumps(state, indent=2) + '\n')
    try:
        if args.security_caddy:
            run(['docker','run','--rm','--network','none','--entrypoint','caddy','-v',
                 str(args.security_caddy.resolve())+':/etc/caddy/Caddyfile:ro','caddy:2-alpine',
                 'validate','--config','/etc/caddy/Caddyfile','--adapter','caddyfile'])
            active_caddy.write_bytes(args.security_caddy.read_bytes())
        run(command + ['up', '-d', '--no-deps', '--no-build', '--pull', 'never', 'web'], cwd=release)
        new_web = wait_healthy()
        run(command + ['up', '-d', '--no-deps', '--no-build', '--pull', 'never', 'gateway'], cwd=release)
        last_error = None
        for _ in range(12):
            try:
                with urlopen('https://' + args.domain + '/_stcore/health', timeout=6) as response:
                    if response.status != 200 or response.read() != b'ok':
                        raise RuntimeError('Unexpected public health response')
                last_error = None
                break
            except Exception as error:
                last_error = error
                time.sleep(2)
        if last_error:
            raise last_error
        state.update(status='public-https-healthy', image_id=new_web['Image'], container_id=new_web['Id'],
                     gateway_id=inspect(GATEWAY)['Id'], application_source_changed=True)
    except Exception as error:
        active_caddy.write_bytes((operation/'Caddyfile.previous').read_bytes())
        state.update(status='failed-rollback-started', error=str(error))
        state_path.write_text(json.dumps(state, indent=2) + '\n')
        run(previous_web_command + ['up', '-d', '--no-deps', '--no-build', '--pull', 'never', 'web'],
            cwd=old_web['Config']['Labels']['com.docker.compose.project.working_dir'])
        wait_healthy()
        run(previous_gateway_command + ['up', '-d', '--no-deps', '--no-build', '--pull', 'never', 'gateway'],
            cwd=old_gateway['Config']['Labels']['com.docker.compose.project.working_dir'])
        state['status'] = 'failed-previous-release-restored'
        state_path.write_text(json.dumps(state, indent=2) + '\n')
        raise
    state_path.write_text(json.dumps(state, indent=2) + '\n')
    print('ZIPING_DEPLOY_RESULT=' + json.dumps(state, ensure_ascii=False), flush=True)


if __name__ == '__main__':
    main()
