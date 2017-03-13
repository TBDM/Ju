# !/usr/bin/env python
# -*- Python Ver: 3.5.2 -*-
# -*- coding: utf-8 -*-


#----------model import----------

# Import built-in models
import re
import os
import sys
import time
import pickle
import subprocess

# Import third-part models

# Import custom models
import tbdmSPIndicator
from tbdmSetting import tbdmDatabase
from tbdmLogging import tbdmLogger
from tbdmSlack import tbdmSlack

#----------model import----------


#----------global variables----------

tbdmDb = tbdmDatabase()
worklog = tbdmLogger("worker", loglevel = 30).log # logging.DEBUG - 10, increase 10 for every level
redisCli = tbdmDb.tbdmRedis(addrOwner = 'xhuang', auth = True)
mongoCli = tbdmDb.tbdmMongo(addrOwner = 'xhuang', authDb = 'tbdm')
mongod = mongoCli.tbdm
slacker = tbdmSlack()

PENALIZE_TIME = 21601 # 6h penalty time and 1s for fail mark
task_keylist = ["juID", "itemID", "score", "status", "urlType", "fail"]
url_arch = ["",
            "https://item.taobao.com/item.htm?id=",
            "https://detail.tmall.hk/hk/item.htm?id=",
            "https://chaoshi.detail.tmall.com/item.htm?id=",
            "https://detail.yao.95095.com/item.htm?id="]

#----------global variables----------


#----------class definition----------

#----------class definition----------


#----------function definition----------

def task_locker(tasks = None, filename = "tbdmPipelock.lock"):
    if (tasks == None):
        try:
            os.remove(filename)
        except Exception as _Eall:
            worklog.error("Locker Error:" + str(_Eall))
    else:
        with open(filename, "ab+") as f:
            pickle.dump(tasks, f, 0)

def task_back2redis(taskdicts):
    tasks = task_dicts2strs(taskdicts)
    with redisCli.pipeline() as redisp:
        for task in tasks:
            redisp.zadd('juList', int(task.split('/')[2]), task)
        try:
            redisp.execute()
        except Exception as _Eall:
            worklog.error("Feedback to Redis failed." + str(_Eall))
            slacker.post_message("Feedback to Redis failed, task info dumped to fbRedis.lock .")
            task_locker(taskdicts, "fbRedis.lock")
            return None
        else:
            task_locker(None)
            with open('toRedis.log','a+', encoding = "utf-8") as f:
                f.write(str(taskdicts) + "\n")
            return 0

def task_min_score(taskdicts):
    """
    @author: X.Huang
    """
    min_score = 3737373737 # Just one big number
    for task in taskdicts:
        if(task['score'] < min_score):
            min_score = task['score']
    return min_score

def task_dicts2strs(taskdicts):
    """
    @author: X.Huang
    """
    taskstrs = []
    for task in taskdicts:
        try:
            taskstr = ''
            for i in range(0, len(task_keylist)):
                taskstr += str(task[task_keylist[i]]) + '/'
        except Exception as _Eall:
            worklog.error('Invalid task dict: ' + str(task))
        else:
            taskstrs.append(taskstr)
    return taskstrs

def task_strs2dicts(tasks):
    """
    @author: X.Huang
    """
    taskdicts = []
    for task in tasks:
        try:
            task = task.decode().split('/')
        except AttributeError as _Eattr:
            worklog.error("Task from Redis not properly encoded, trying without decode: " + str(task))
            task = task.split('/')
        except Exception as _Eall:
            worklog.error('Invalid task string: ' + str(task))
        try:
            taskdicts.append({'juID' : str(task[0]),
                              'itemID' : str(task[1]),
                              'score' : int(task[2]),
                              'status' : int(task[3]),
                              'urlType' : int(task[4]),
                              'fail' : int(task[5])
                              # 'fail' : int(float(task[2]))%10
                            })
        except Exception as _Eall:
            worklog.error('Invalid task: ' + str(task))
    return taskdicts

def str_to_time(is_taobao, timestr):
    """
    @author: P.Liu
    """
    if(is_taobao):
        timestr = timestr.replace('月', '-')
        timestr = timestr.replace('日', '')
        timestr = time.strftime("%Y", time.localtime()) + '-' + timestr + ':00'
        return int(time.mktime(time.strptime(timestr, '%Y-%m-%d %H:%M:%S')))
    else:
        now_time = int(time.time())
        if(timestr.find('天') != -1):
            if(timestr.find('小时') != -1):
                now_time = int((now_time + 24 * 60 * 60 * int(timestr[:timestr.find('天')])
                 + 60 * 60 * int(timestr[timestr.find('天')+1:timestr.find('小时')])) / 100) * 100
        else:
            if(timestr.find('小时') != -1):
                if(timestr.find('分') != -1):
                    now_time = int((now_time + 60 * 60 * int(timestr[:timestr.find('小时')])
                     + 60 * (int(timestr[timestr.find('小时') + 2:timestr.find('分')]) + 1)) / 100) * 100
            else:
                if(timestr.find('分') != -1):
                    if(timestr.find('秒') != -1):
                        now_time = int((now_time + 60 * (int(timestr[:timestr.find('分')]) + 1)) / 100) * 100
        return now_time
       
def get_indicator(task, url, datestr):
    """
    @author: P.Liu X.Huang
    """
    try:
        content = open(task['itemID'] + '.html', encoding = "utf-8").read()
        is_taobao = 0
        title = ''
        if(url == 2):
            try:
                if(not re.search('<title>([\S ]*)淘宝网</title>', content)):
                    is_taobao = 0
                    title = re.search('<input type="hidden" name="title" value="([\S ]*)"', content).group(1)
                else:
                    is_taobao = 1
                    title = re.search('<h3 class="tb-main-title" data-title="([\S ]*)"', content).group(1) 
            except Exception as _Eall:
                worklog.error("Title-parsing error: " + str(_Eall))           
        if(not tbdmSPIndicator.nvwang_festa_indicate(content, task)):
            if(re.search('参加聚划算', content)):
                if(not re.search('</strong>后结束', content)):
                    if(is_taobao):
                        begin_time = str_to_time(1, re.search('<strong class="tb-ju-more">([\S ]*)</strong>参加聚划算', content).group(1))                
                    else:
                        begin_time = str_to_time(0, re.search('<strong>([\S ]*)</strong>后开始', content).group(1))
                    if(task['status'] == 0):
                        task['status'] += 1
                    task['score'] = begin_time
                else:
                    end_time = str_to_time(0, re.search('<strong>([\S ]*)</strong>后结束', content).group(1))   
                    if(task['status'] < 2):
                        task['status'] = 2
                    task['score'] = end_time
            else:
                if(task['status'] > 1):
                        task['status'] += 1
                        task['score'] += 86400 # Scrape on next day
                else:
                    # Failure situation
                    task['score'] = int(time.time() / 10) * 10 + PENALIZE_TIME
                    task['fail'] += 1
                    worklog.error('Unexcepted indicating: ' + task['itemID'] + ',' + title + ',' + str(url) + ',' + 
                                    str(task['score']) + "\n")
                    subprocess.call(['mv', task['itemID'] + '.html', datestr + '/error/' + task['itemID']
                                + '-' + str(int(time.time()))  + '.html'])
                    return 0
        else:
            with open(datestr + '/NvwangFestItem_20170308.log','a', encoding = "utf-8") as f:
                f.write(task['itemID'] + ',' + title + ',' + str(url) + "\n")
        subprocess.call(['mv', task['itemID'] + '.html', datestr + '/success/' + task['itemID']
                                + '-' + str(int(time.time())) + '.html'])
        with open(datestr + '/success.log','a', encoding = "utf-8") as f:
            f.write(task['itemID'] + ',' + title + ',' + str(url) + ',' + str(task['score']) + "\n")
        worklog.info('sleep 10s')
        time.sleep(10)
        return 1
    except Exception:
        task['score'] = int(time.time() / 10) * 10 + PENALIZE_TIME
        task['fail'] += 1
        subprocess.call(['mv', task['itemID'] + '.html', datestr + '/error/' + task['itemID']
                                + '-' + str(int(time.time()))  + '.html'])
        worklog.error('Fetch-parsing Error:' + task['itemID'] + ',' + title + ',' + str(url) + ',' + str(task['score']) + "\n")
        return 0

def request_page(taskdicts):
    success_cnt = 0
    total_cnt = len(taskdicts)
    datestr = time.strftime("%Y%m%d", time.localtime())
    if not os.path.isdir(datestr):
        os.mkdir(datestr)
    if not os.path.isdir(datestr + '/error'):
        os.mkdir(datestr + '/error')
    if not os.path.isdir(datestr + '/success'):
        os.mkdir(datestr + '/success')
    try:
        for task in taskdicts:
            if(task['score'] > time.time()):
                total_cnt -= 1
                continue;
            if(task['fail'] > 8):
                worklog.error("Too many failures, abandon task: " + str(task))
                slacker.post_message("Task " + str(task) + " was abandoned for failures.", channel = "worker")
                with open(datestr + "/abandoned_task.log", "a+", encoding = "utf-8") as f:
                    f.write(str(task))
                taskdicts.remove(task)
                break
            if(task['status'] > 14):
                worklog.info("Track of " + str(task) + " finished. Hooray!")
                slacker.post_message("Track of " + str(task) + " finished. Hooray!", channel = "worker")
                with open(datestr +"/finished_task.log", "a+", encoding = "utf-8") as f:
                    f.write(str(task))
                taskdicts.remove(task)
                break
            if(task['urlType'] > 0 and task['urlType'] < 5):
                reqseq = task['urlType']
            else:
                reqseq = 1
            while True:
                retcode =  subprocess.call(['phantomjs', 'spider.js', url_arch[reqseq] + task['itemID']])
                if(retcode == 0):
                    task['urlType'] = reqseq
                    success_cnt += get_indicator(task, reqseq + 1, datestr)
                    break
                else:
                    reqseq += 1
                    if reqseq > 4:
                        worklog.critical('oops! Pan said taobao has upgraded their anti-spider policy\n')
                        task['score'] = int(time.time() / 10) * 10 + PENALIZE_TIME
                        task['fail'] += 1
                        break
    except KeyboardInterrupt:
        pass
    except Exception as _Eall:
        print(_Eall)
    finally:
        task_back2redis(taskdicts)
        return (success_cnt, total_cnt)

#----------function definition----------


#----------main function----------

if __name__ == '__main__':
    print('Import me pls, meow.')

#----------main function----------