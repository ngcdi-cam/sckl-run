#!/usr/bin/python3

import subprocess
import requests
import time
import logging
import json
import os
#import ifxdb_to_csv as ifx_csv

logging.basicConfig(
    level='INFO', format='%(asctime)s %(name)-12s %(levelname)-8s %(message)s')

RUN_CONTAINERS = 'run_containers.py'

BASE_CONFIG = 'configs/base.yaml'
NETWORK_CONFIG = 'configs/network.overlay.yaml'
AGENTS_CONFIG = 'configs/agents.overlay.yaml'
NO_SCKL_DATA_CONFIG = 'configs/no_sckl_data.overlay.yaml'

# NO_SCKL_SM_CONFIG = 'configs/agents_nosm.overlay.yaml' # deprecated
NO_NETWORK_CONFIG = 'configs/no_network.overlay.yaml'

MININET_TOPO_BASE_DIR = 'configs/mininet_topos'
AGENT_TOPO_BASE_DIR = 'configs/agent_topos'


def get_ip_address_of_container(name):
    return subprocess.run(
        ['docker', 'inspect', '-f',
            '{{range .NetworkSettings.Networks}}{{.IPAddress}}{{end}}', name],
        capture_output=True).stdout.decode('ascii').rstrip('\n')


def clean_containers():
    logging.info('Cleaning containers...')
    subprocess.run('docker stop -t 0 $(docker ps -q) > /dev/null 2> /dev/null', shell=True)
    subprocess.run('docker rm $(docker ps -a -q) > /dev/null 2> /dev/null', shell=True)


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
    # print("====start throughput_raw=======")
    # [ print(str(el)) for el in throughput_raw ]
    # print("====end throughput_raw=======")
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

def awareness_set_access_table_pinning(url, dpid, ip, port):
    res = requests.patch(
        url + '/awareness/access_table_entry_pinnings',
        data=json.dumps({'pinnings': [{'dpid': dpid, 'ip': ip, 'port': port}]})
    )

def awareness_get_services():
    return requests.get(AWARENESS_URL + '/awareness/services').json()['services']

def awareness_get_switch_weights():
    return requests.get(AWARENESS_URL + '/awareness/weights/switches').json()['switches']

def mininet_start_iperf_servers():
    requests.post(
        MININET_URL + '/nodes/h1/cmd',
        data='iperf -s -u &')
    requests.post(
        MININET_URL + '/nodes/h2/cmd',
        data='iperf -s -u &')

def mininet_ping():
    requests.post(
        MININET_URL + '/nodes/h1/cmd',
        data='ping -c 10 h2 &'
    )
    requests.post(
        MININET_URL + '/nodes/h2/cmd',
        data='ping -c 10 h1 &'
    )

def log_event(file, name, data=''):
    j = json.dumps({'type': name, 'timestamp': time.time(), 'data': data})
    logging.info('{}: {}'.format(name, data))
    file.write(j + '\n')
    file.flush()

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

def log_awareness_services(file):
    log_event(file, 'awareness_services', awareness_get_services())

def log_awareness_switch_weights(file):
    log_event(file, 'awareness_switch_weights', awareness_get_switch_weights())

def mininet_trigger_traffic(file, duration=3):
    logging.info('Triggering traffic for {}s'.format(duration))
    src_host = 'h1'
    dst_host = 'h2'
    cmd = 'iperf -u -b 8m -t ' + str(duration) + ' -c ' + dst_host
    log_event(file, 'iperf', cmd)
    return requests.post(
        MININET_URL + '/nodes/' + src_host + '/cmd',
        data=cmd)


def run_experiment(name, ext_agent_configs: list = [], ext_network_configs: list = [], run_agents=False, iterations: int =1):
    global MININET_URL, AWARENESS_URL

    os.makedirs('runs', exist_ok=True)

    with open('runs/{}.log'.format(name), 'w') as log:
        logging.info('Starting experiment ' + name)

        # replace in the config file as for some reason it is not updating the prometheus config with the run name in advance
        subprocess.run(['sed','-i', 's/default_run/'+name+'/g', BASE_CONFIG])
        
        logging.info('Starting mininet and awareness...')
        subprocess.run([RUN_CONTAINERS, BASE_CONFIG, NETWORK_CONFIG, *ext_network_configs])

        MININET_URL = 'http://{}:8081'.format(
            get_ip_address_of_container('mininet'))
        AWARENESS_URL = 'http://{}:8080'.format(
            get_ip_address_of_container('awareness1'))
        logging.info('Mininet URL is ' + MININET_URL)
        logging.info('Awareness URL is ' + AWARENESS_URL)
        logging.info('Starting iperf servers...')
        mininet_start_iperf_servers()
        logging.info('Testing ping')
        mininet_ping()

        # workaround the default route
        if name.startswith('mesh_multisdn_'):
            AWARENESS2_URL = 'http://{}:8080'.format(
                get_ip_address_of_container('awareness2'))
            awareness_set_access_table_pinning(AWARENESS_URL, 1, '10.0.0.2', 1)
            awareness_set_access_table_pinning(AWARENESS2_URL, 2, '10.0.0.1', 1)
            # wait for the old flow entries to expire
            time.sleep(30)

        if run_agents:
            logging.info('Starting agents...')
            subprocess.run([RUN_CONTAINERS, '-w', 'run_name', name,
                            BASE_CONFIG, AGENTS_CONFIG, *ext_network_configs, *ext_agent_configs, NO_NETWORK_CONFIG])

        for i in range(iterations):
            logging.info('Iteration ' + str(i))
            mininet_trigger_traffic(log, 10)
            throughput = log_awareness_throughput(log)
            log_awareness_computed_path(log, throughput, 80)
            log_awareness_switch_weights(log)
            log_awareness_services(log)
        
        
        
        #rollback base config for next run
        subprocess.run(['sed','-i', 's/'+name+'/default_run/g', BASE_CONFIG])

def run_experiment_group(rtype, network_topo, agent_topo: str ='off'):
    
    network_topo_file = os.path.join(MININET_TOPO_BASE_DIR, network_topo + '.yaml')
    mininet = [network_topo_file]
        
    #agent config
    if(rtype == 'netm_on_conm_on'):
        agent_topo_file = os.path.join(AGENT_TOPO_BASE_DIR, agent_topo + '.yaml')
        agents=[agent_topo_file]
        flag=True
        prefix = network_topo + '_ag_' + agent_topo
        
    elif (rtype == 'netm_on_conm_off'):
        agent_topo_file = os.path.join(AGENT_TOPO_BASE_DIR, agent_topo + '.yaml')
        agents=[NO_SCKL_DATA_CONFIG, agent_topo_file]
        flag=True
        prefix = network_topo + '_ag_' + agent_topo
        
    else: #agents off
        agents=[]
        flag=False
        prefix = network_topo
        
    
    iterations = 20
    runs = 1
    
    for i in range(1,runs+1,1):
        clean_containers()
        time.sleep(15) # allow some time to remove containers 
        name = rtype +'_'+ prefix +'_'+ str(i)        
        run_experiment(name, agents, mininet, flag, iterations)
        #ifx_csv.build_monitoring_csvs(name)
        logging.info("FINISHES HERE")

if __name__ == '__main__':
    rtypes = ['ag_off','netm_on_conm_on','netm_on_conm_off']
    #ag_topos = ['topo1','topo3','topo4']#,'topo4_indirect']
    ag_topos = ['topo3']
    netw_topos = ['mesh']#,'ring','small_world','scale_free']#,'custom','mesh_indirect','ring_indirect','mesh_multisdn','complete_bipartite']
    
    for agt in ag_topos:
        for nwt in netw_topos:
            run_experiment_group(rtypes[0],nwt,agt)
