#!/usr/bin/python3

import subprocess
import requests
import time
import logging
import json
import os

logging.basicConfig(
    level='INFO', format='%(asctime)s %(name)-12s %(levelname)-8s %(message)s')

RUN_CONTAINERS = 'run_containers.py'

BASE_CONFIG = 'configs/base.yaml'
NETWORK_CONFIG = 'configs/network.overlay.yaml'
AGENTS_CONFIG = 'configs/agents.overlay.yaml'
NO_SCKL_DATA_CONFIG = 'configs/no_sckl_data.overlay.yaml'


def get_ip_address_of_container(name):
    return subprocess.run(
        ['docker', 'inspect', '-f',
            '{{range .NetworkSettings.Networks}}{{.IPAddress}}{{end}}', name],
        capture_output=True).stdout.decode('ascii').rstrip('\n')


def clean_containers():
    logging.info('Cleaning containers...')
    subprocess.run('docker stop $(docker ps -q)', shell=True)
    subprocess.run('docker rm $(docker ps -a -q)', shell=True)


MININET_URL = ''
AWARENESS_URL = ''


def awareness_get_paths():
    return requests.get(AWARENESS_URL + '/awareness/active_paths').json()['paths']


def awareness_get_throughput():
    stats = requests.get(AWARENESS_URL + '/awareness/stats').json()['graph']
    ret = []
    for link in stats:
        src = link['src']
        dst = link['dst']
        throughput = link['metrics']['throughput']
        ret.append({'src': src, 'dst': dst, 'throughput': throughput})
    return ret


def awareness_compute_potential_paths(throughput, threshold):
    throughput_raw = map(lambda x: (x['src'], x['dst']), filter(
        lambda x: x['throughput'] > threshold, throughput))
    topo = {}
    for (src, dst) in throughput_raw:
        topo.setdefault(src, [])
        topo[src].append(dst)
        topo.setdefault(dst, [])
        topo[dst].append(src)

    cur_switch = None
    for switch, peers in topo.items():
        if len(peers) == 1:
            cur_switch = switch
            break
    if cur_switch is None:
        return []
    path = [cur_switch]
    while True:
        peers = topo[cur_switch]
        updated = False
        for peer in peers:
            if peer not in path:
                path.append(peer)
                cur_switch = peer
                updated = True
                break
        
        if not updated:
            break
    
    if path[0] > path[-1]:
        path = path[::-1]
    
    return path


def mininet_start_iperf_servers():
    requests.post(
        MININET_URL + '/nodes/h1/cmd',
        data='iperf -s -u &')
    requests.post(
        MININET_URL + '/nodes/h2/cmd',
        data='iperf -s -u &')


def log_event(file, name, data=''):
    j = json.dumps({'type': name, 'timestamp': time.time(), 'data': data})
    logging.info('log_event(): ' + j)
    file.write(j + '\n')

# deprecated
def log_awareness_paths(file):
    log_event(file, 'awareness_path', awareness_get_paths())


def log_awareness_throughput(file):
    throughput = awareness_get_throughput()
    log_event(file, 'awareness_throughput', throughput)
    return throughput


def log_awareness_computed_path(file, throughput, threshold):
    log_event(file, 'awareness_computed_path',
              awareness_compute_potential_paths(throughput, threshold))


def mininet_trigger_traffic(file, duration=3):
    logging.info('Triggering traffic for {}s'.format(duration))
    src_host = 'h1'
    dst_host = 'h2'
    cmd = 'iperf -u -b 8m -t ' + str(duration) + ' -c ' + dst_host
    log_event(file, 'iperf', cmd)
    return requests.post(
        MININET_URL + '/nodes/' + src_host + '/cmd',
        data=cmd)


def run_experiment(name, ext_agent_configs: list = [], run_agents=False):
    global MININET_URL, AWARENESS_URL

    os.makedirs('runs', exist_ok=True)
    
    with open('runs/{}.log'.format(name), 'w') as log:
        logging.info('Starting experiment ' + name)

        clean_containers()

        logging.info('Starting mininet and awareness...')
        subprocess.run([RUN_CONTAINERS, BASE_CONFIG, NETWORK_CONFIG])

        time.sleep(3)
        MININET_URL = 'http://{}:8081'.format(
            get_ip_address_of_container('mininet'))
        AWARENESS_URL = 'http://{}:8080'.format(
            get_ip_address_of_container('awareness'))
        logging.info('Mininet URL is ' + MININET_URL)
        logging.info('Awareness URL is ' + AWARENESS_URL)
        mininet_start_iperf_servers()
        time.sleep(3)

        if run_agents:
            logging.info('Starting agents...')
            subprocess.run([RUN_CONTAINERS, '-w', 'dataset_name', name,
                            BASE_CONFIG, AGENTS_CONFIG, *ext_agent_configs])
        
        logging.info('Waiting for awareness to collect network information')
        time.sleep(10)
        for i in range(15):
            logging.info('Run ' + str(i))
            mininet_trigger_traffic(log, 10)
            throughput = log_awareness_throughput(log)
            log_awareness_computed_path(log, throughput, 10)


if __name__ == '__main__':
    run_experiment('plain_awareness')
    run_experiment('agents_without_overheating', [NO_SCKL_DATA_CONFIG], True)
    run_experiment('agents_with_overheating', [], True)
