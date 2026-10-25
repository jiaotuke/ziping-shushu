"""Host-side bounded resource monitoring. No accounts, requests, or model credentials read."""
from datetime import datetime, timezone
import json
import logging
from logging.handlers import RotatingFileHandler
import os
from pathlib import Path
import shutil
import subprocess
from zoneinfo import ZoneInfo

ROOT = Path('/root/ziping-maintenance/security')


def main():
    ROOT.mkdir(parents=True, mode=0o700, exist_ok=True)
    state_file=ROOT/'state.json'
    try:
        previous=json.loads(state_file.read_text())
    except (OSError,ValueError):
        previous={}
    memory={line.split(':',1)[0]:int(line.split()[1])*1024 for line in Path('/proc/meminfo').read_text().splitlines()}
    memory_used=round(100*(1-memory['MemAvailable']/memory['MemTotal']),1)
    disk=shutil.disk_usage('/')
    disk_used=round(100*disk.used/disk.total,1)
    load5=os.getloadavg()[1]
    interface=next(line.split()[0] for line in Path('/proc/net/route').read_text().splitlines()[1:] if line.split()[1]=='00000000')
    tx=int((Path('/sys/class/net')/interface/'statistics/tx_bytes').read_text())
    today=datetime.now(ZoneInfo('Asia/Shanghai')).date().isoformat()
    daily=previous.get('daily_tx_bytes',0) if previous.get('day')==today else 0
    if 'tx_bytes' in previous:
        daily+=max(0,tx-previous['tx_bytes'])
    alerts=[]
    if memory_used>=85: alerts.append('服务器内存使用率达到85%以上')
    if disk_used>=85: alerts.append('系统盘使用率达到85%以上')
    if load5>=3: alerts.append('服务器五分钟平均负载较高')
    if daily>=1024**3: alerts.append('今日网卡出流量粗估超过1GiB，请核对访问与费用')
    containers={}
    for role,name in (('web','ziping-public-web-1'),('gateway','ziping-public-gateway-1')):
        result=subprocess.run(['docker','inspect',name],capture_output=True,text=True)
        if result.returncode:
            alerts.append(role+'服务容器不存在或无法检查')
            continue
        item=json.loads(result.stdout)[0]
        containers[role]={'id':item['Id'],'status':item['State']['Status'],'restarts':item['RestartCount'],
                          'health':item['State'].get('Health',{}).get('Status')}
        if item['State']['Status']!='running' or containers[role]['health']=='unhealthy':
            alerts.append(role+'服务未运行或健康检查异常')
        old=previous.get('containers',{}).get(role,{})
        if old.get('id')==item['Id'] and item['RestartCount']>old.get('restarts',0):
            alerts.append(role+'服务发生自动重启')
    status={'checked_at':datetime.now(timezone.utc).isoformat(timespec='seconds'),'day':today,
            'memory_used_percent':memory_used,'disk_used_percent':disk_used,'load_5m':round(load5,2),
            'network_outbound_mib_today':round(daily/1024**2,1),
            'network_note':'服务器网卡粗估，从监控启用时开始累计，不等于阿里云计费流量；告警不会停止计费。',
            'alerts':alerts,'containers':{role:{k:v for k,v in value.items() if k!='id'} for role,value in containers.items()}}
    state={'day':today,'tx_bytes':tx,'daily_tx_bytes':daily,'containers':containers,'alerts':alerts}
    state_file.write_text(json.dumps(state,ensure_ascii=False))
    # Only resource summaries go into the site's writable data volume.
    volume=json.loads(subprocess.check_output(['docker','volume','inspect','ziping-public-data'],text=True))[0]
    target=Path(volume['Mountpoint'])/'runtime/security/host-status.json'
    target.parent.mkdir(parents=True,exist_ok=True)
    os.chown(target.parent,10001,10001)
    os.chmod(target.parent,0o700)
    temporary=target.with_suffix('.tmp')
    temporary.write_text(json.dumps(status,ensure_ascii=False),encoding='utf-8')
    os.chown(temporary,10001,10001)
    os.chmod(temporary,0o600)
    temporary.replace(target)
    logger=logging.getLogger('ziping-security-monitor')
    logger.setLevel(logging.INFO)
    handler=RotatingFileHandler(ROOT/'monitor.log',maxBytes=1024*1024,backupCount=3,encoding='utf-8')
    logger.addHandler(handler)
    if alerts!=previous.get('alerts'):
        logger.warning(json.dumps({'checked_at':status['checked_at'],'alerts':alerts},ensure_ascii=False))
    print(json.dumps(status,ensure_ascii=False))


if __name__=='__main__':
    main()
