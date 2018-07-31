# encoding: UTF-8

from __future__ import print_function
import sys
try:
    reload(sys)  # Python 2
    sys.setdefaultencoding('utf8')
except NameError:
    pass         # Python 3

import multiprocessing
from time import sleep
from datetime import datetime, time

from vnpy.event import EventChannel
from vnpy.trader.vtEvent  import EVENT_LOG, EVENT_ERROR
from vnpy.trader.vtEngine import MainRoutine, Logger
from vnpy.trader.gateway  import huobiGateway
import vnApp.Strategy         as vnStategy
from vnApp.Strategy.Base  import EVENT_LOG

#----------------------------------------------------------------------
def processErrorEvent(event):
    """
    处理错误事件
    错误信息在每次登陆后，会将当日所有已产生的均推送一遍，所以不适合写入日志
    """
    error = event.dict_['data']
    print(u'错误代码：%s，错误信息：%s' %(error.errorID, error.errorMsg))
    
#----------------------------------------------------------------------
def runChildProcess():
    """子进程运行函数"""
    print('-'*20)
    
    # 创建日志引擎
    le = Logger()
    le.setLogLevel(le.LEVEL_INFO)
    le.addConsoleHandler()
    le.addFileHandler()
    
    le.info(u'启动vnApp策略运行子进程')
    
    ee = EventChannel()
    le.info(u'事件引擎创建成功')
    
    me = MainRoutine(ee)
    me.addMarketData(huobiGateway)
    me.addApp(vnStategy)
    le.info(u'主引擎创建成功')
    
    ee.register(EVENT_LOG, le.processLogEvent)
    ee.register(EVENT_LOG, le.processLogEvent)
    ee.register(EVENT_ERROR, processErrorEvent)
    le.info(u'注册日志事件监听')
    
    me.connect('HuoBI')
    le.info(u'连接HuoBi接口')
    
    sleep(10)                       # 等待CTP接口初始化
    me.dataEngine.saveContracts()   # 保存合约信息到文件
    
    app = me.getApp(vnStategy.appName)
    
    app.loadSetting()
    le.info(u'vnApp策略载入成功')
    
    app.initAll()
    le.info(u'vnApp策略初始化成功')
    
    app.startAll()
    le.info(u'vnApp策略启动成功')
    
    while True:
        sleep(1)

#----------------------------------------------------------------------
def runParentProcess():
    """父进程运行函数"""
    # 创建日志引擎
    le = Logger()
    le.setLogLevel(le.LEVEL_INFO)
    le.addConsoleHandler()
    
    le.info(u'启动vnApp策略守护父进程')
    
    DAY_START = time(8, 45)         # 日盘启动和停止时间
    DAY_END = time(15, 30)
    
    NIGHT_START = time(20, 45)      # 夜盘启动和停止时间
    NIGHT_END = time(2, 45)
    
    p = None        # 子进程句柄
    
    while True:
        currentTime = datetime.now().time()
        recording = False
        
        # 判断当前处于的时间段
        if ((currentTime >= DAY_START and currentTime <= DAY_END) or
            (currentTime >= NIGHT_START) or
            (currentTime <= NIGHT_END)):
            recording = True
        
        # 记录时间则需要启动子进程
        if recording and p is None:
            le.info(u'启动子进程')
            p = multiprocessing.Process(target=runChildProcess)
            p.start()
            le.info(u'子进程启动成功')
            
        # 非记录时间则退出子进程
        if not recording and p is not None:
            le.info(u'关闭子进程')
            p.terminate()
            p.join()
            p = None
            le.info(u'子进程关闭成功')
            
        sleep(5)


if __name__ == '__main__':
    runChildProcess()
    
    # 尽管同样实现了无人值守，但强烈建议每天启动时人工检查，为自己的PNL负责
    #runParentProcess()
