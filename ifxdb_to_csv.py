#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Created on Fri Oct 16 13:28:25 2020

@author: mep53
"""


from influxdb import InfluxDBClient
import pandas as pd
import datetime as dt
import numpy as np

cadvisor_metrics = ['container_memory_usage_bytes'
                ,'container_network_transmit_bytes_total'
                ,'container_network_receive_bytes_total'
                ,'container_cpu_usage_seconds_total'
                ,'container_network_receive_packets_total'
                ,'container_network_transmit_packets_total'
                ,'container_fs_usage_bytes'
                ,'container_spec_memory_limit_bytes'
                ,'container_spec_memory_reservation_limit_bytes'
                ,'container_spec_cpu_shares'
                ,'container_spec_cpu_period'
               ]

sckl_metrics = {'ngcdi_received_msgs_count_total':['time','instance','job','metric','value']
                ,'ngcdi_da_sensed':['time','instance','job','key','metric','value']
                ,'ngcdi_service_mean':['time','instance','job','key','metric','value']
                }


ag_types = ("Digital Asset (DA)","Service Manager (SM)", "Function Provisioner (FP)")

tptMetric = 'CCOutbound Throughput'
dateFormat = '%Y-%m-%dT%H:%M:%S.%fZ' # RFC3339 format used by influxdb
dateFormatNTZ = '%Y-%m-%dT%H:%M:%S'
root_dir = ""
data_dir = root_dir+"data/"
sckl_core_img = 'ngcdi/sckl-demo:0.6'



def build_cadvisor_df(host,suffix):
    user = ''
    password = ''
    dbname = 'ngcdi_metrics'

    #cols = ['mean','max', 'min']

    df_ca = pd.DataFrame()
   # print("starting",)
    i=0
    #for k in runs:
    i+=1
    c = InfluxDBClient(host, 18086, user, password, dbname)
    idx = 0

    dRun = pd.DataFrame()

    for metric in cadvisor_metrics:
        sqlAgs = getAgentQuery(cadvisor_metrics[idx])
        print(sqlAgs)
        dAgs = runQuery(sqlAgs,c,['time','name','job','value'])
        dAgs.columns = ['time','name','job',metric]

        if(idx >0):
              dRun = pd.merge(dRun,dAgs,on=['time','name','job'])
        else:
             dRun = dAgs.copy()
        idx = idx + 1

    df_ca = df_ca.append(dRun, ignore_index=True)

    df_ca.to_csv(data_dir+"ca-data-"+suffix+".csv", index= False, header = True, line_terminator = "\n")


def build_sckl_df(host,suffix):
    user = ''
    password = ''
    dbname = 'ngcdi_metrics'

    #cols = ['mean','max', 'min']

    df_sckl = pd.DataFrame()
   # print("starting",)
    i=0
    i+=1
    c = InfluxDBClient(host, 18086, user, password, dbname)
    idx = 0

    dRun = pd.DataFrame()

    for metric,columns in sckl_metrics.items():
        sqlAgs = getScklMetrics(metric,columns)
        dAgs = runQuery(sqlAgs,c,columns)
        newcols = columns[0:len(columns)-2]
        newcols.append('label') #  replace metric sckl by label
        newcols.append(metric)
        dAgs.columns = newcols
        #dAgs = dAgs.replace(np.nan, 'none', regex=True)




        if(idx >0):
             dRun = pd.merge(dRun,dAgs,on=['time','job','instance','label'],how='outer')
        else:
              dRun = dAgs.copy()
        idx = idx + 1
        #print(dRun.head())


    df_sckl = df_sckl.append(dRun, ignore_index=True)


    ## timer measurements

    sqlTimerMs = getScklTimeMeasurements()
    #print(sqlTimerMs)
    rs = c.query(sqlTimerMs)
    listResults = list(rs.get_points())
    columns = ["time","instance","job","operation","value"]

    idx = 0
    dfRunTM = pd.DataFrame(columns=columns)
    for o in listResults:
        sqlTimers = getScklIndividualQuery(o["name"],columns)
        dIndTM = runQuery(sqlTimers,c,columns)
        dfRunTM = dfRunTM.append(dIndTM, ignore_index=True)

    ### convert to csv

    df_sckl.to_csv(data_dir+"sckl-data-"+suffix+".csv", index= False, header = True, line_terminator = "\n")
    dfRunTM.to_csv(data_dir+"sckl-timers-"+suffix+".csv", index= False, header = True, line_terminator = "\n")


def getAgentQuery(series):
    image = sckl_core_img
    #series = 'container_memory_usage_bytes'

    sql = 'SELECT '

    sql += '"value", '
    sql += '"name", '
    sql += '"job" '
    #sql += 'count("value"::field) '

    sql += 'FROM "' + series + '" '

    #condition
    sql += 'WHERE "image" = \''+ image +'\' '
    sql += 'GROUP BY "name"'
    return sql

def getMsgsIndividualQuery(node,start,end):
    #series = 'akka_system_processed_messages_total'
    series = 'container_network_transmit_bytes_total'
    #select mean(value) from container_network_receive_packets_total where image =~ /sckl/ group by name
    sql = 'SELECT '

    sql += 'max("value"::field) '

    sql += 'FROM "' + series + '" '

    #condition
    sql += 'WHERE '
    #sql += '"instance" =~ /'+node+'/ '
    #sql += 'AND "tracked" = \'true\' '
    sql += 'image =~ /sckl/ '
    sql += 'AND "name" =~ /'+ node +'/'
    #sql += 'AND time >= \''+ start + '\' '
    #if(end != ''):
    #    sql += 'AND time < \''+ end + '\' '
    #sql += 'GROUP BY "instance"'
    sql += 'GROUP BY "name"::tag'

    #FROM + series + WHERE time >= '2019-11-13T17:03:04.462036Z' AND time < '2019-11-13T17:07:14.462036Z' AND "instance" =~ /c/ GROUP BY "instance"
    #print(sql)
    return sql

def getScklIndividualQuery(series,columns):
    #select mean(value),max(value) from ngcdi_c10_timer_seconds_count, ngcdi_c1_timer_seconds_count, ngcdi_c20_timer_seconds_count group by instance

    sql = 'SELECT '

    for co in columns:
        sql += '"'+co+'",'
    sql = sql[0:len(sql)-1]+ ' '

    sql += 'FROM ' + series + ' '

    return sql


def getScklMetrics(series,columns):

    sql = 'SELECT '

    for co in columns:
        sql += '"'+co+'",'
    sql = sql[0:len(sql)-1]+ ' '
    sql += 'FROM ' + series + ' '
    sql += 'WHERE '
    sql += '"metric" = \'bandwidth\' '
    sql += 'OR "metric" = \'free_bandwidth\' '
    sql += 'OR "metric" = \'throughput\' '
    sql += 'OR "metric" = \'board_temperature\' '
    sql += 'OR "metric" = \'\' '
    #print(sql)
    return sql

def getScklTimeMeasurements():

    sql = 'SHOW '
    sql += 'measurements '
    sql += 'WITH '
    sql += ' measurement =~ /n*timer_seconds_count/ '
    #print(sql)
    return sql

def runQuery(sql,client, cols):
    rs = client.query(sql)

    listResults = list(rs.get_points())
    # print('Results')
    # print(listResults)
    df = pd.DataFrame.from_records(listResults, columns = cols)
    #print(df.dtypes)
    return df

def build_monitoring_csvs(run_name,host:str='localhost'):
    # Build CSV files
    build_cadvisor_df(host,run_name)
    build_sckl_df(host,run_name)
