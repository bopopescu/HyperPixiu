# encoding: UTF-8

# 系统模块
from Queue import Queue, Empty
from threading import Thread
from time import sleep
from collections import defaultdict

# 第三方模块
from qtpy.QtCore import QTimer

########################################################################
class EventChannel(object):
    """
    计时器使用python线程的事件驱动引擎        
    """

    # 系统相关
    EVENT_TIMER = 'eTimer'                  # 计时器事件，每隔1秒发送一次
    EVENT_LOG   = 'eLog'                    # 日志事件，全局通用
    EVENT_ERROR = 'eError.'                 # 错误回报事件

    #----------------------------------------------------------------------
    def __init__(self):
        """初始化事件引擎"""
        # 事件队列
        self.__queue = Queue()
        
        # 事件引擎开关
        self.__active = False
        
        # 事件处理线程
        self.__thread = Thread(target = self.__run)
        
        # 计时器，用于触发计时器事件
        self.__timer = Thread(target = self.__runTimer)
        self.__timerActive = False                      # 计时器工作状态
        self.__timerSleep = 1                           # 计时器触发间隔（默认1秒）        
        
        # 这里的__handlers是一个字典，用来保存对应的事件调用关系
        # 其中每个键对应的值是一个列表，列表中保存了对该事件进行监听的函数功能
        self.__handlers = defaultdict(list)
        
        # __generalHandlers是一个列表，用来保存通用回调函数（所有事件均调用）
        self.__generalHandlers = []        
        
    #----------------------------------------------------------------------
    def __run(self):
        """引擎运行"""
        while self.__active == True:
            try:
                event = self.__queue.get(block = True, timeout = 1)  # 获取事件的阻塞时间设为1秒
                if event :
                    self.__process(event)
            except Exception:
                pass
            
    #----------------------------------------------------------------------
    def __process(self, event):
        """处理事件"""
        # 检查是否存在对该事件进行监听的处理函数
        if event.type_ in self.__handlers:
            # 若存在，则按顺序将事件传递给处理函数执行
            for handler in self.__handlers[event.type_] :
                try:
                    handler(event)
                except Exception as ex:
                    print(ex)
            
        # 调用通用处理函数进行处理
        if self.__generalHandlers:
            for handler in self.__generalHandlers :
                try:
                    handler(event)
                except Exception as ex:
                    print(ex)
               
    #----------------------------------------------------------------------
    def __runTimer(self):
        """运行在计时器线程中的循环函数"""
        while self.__timerActive:
            # 创建计时器事件
            event = Event(type_= EventChannel.EVENT_TIMER)
        
            # 向队列中存入计时器事件
            self.put(event)    
            
            # 等待
            sleep(self.__timerSleep)

    #----------------------------------------------------------------------
    def start(self, timer=True):
        """
        引擎启动
        timer：是否要启动计时器
        """
        # 将引擎设为启动
        self.__active = True
        
        # 启动事件处理线程
        self.__thread.start()
        
        # 启动计时器，计时器事件间隔默认设定为1秒
        if timer:
            self.__timerActive = True
            self.__timer.start()
    
    #----------------------------------------------------------------------
    def stop(self):
        """停止引擎"""
        # 将引擎设为停止
        self.__active = False
        
        # 停止计时器
        self.__timerActive = False
        self.__timer.join()
        
        # 等待事件处理线程退出
        self.__thread.join()
            
    #----------------------------------------------------------------------
    def register(self, type_, handler):
        """注册事件处理函数监听"""
        # 尝试获取该事件类型对应的处理函数列表，若无defaultDict会自动创建新的list
        handlerList = self.__handlers[type_]
        
        # 若要注册的处理器不在该事件的处理器列表中，则注册该事件
        if handler not in handlerList:
            handlerList.append(handler)
            
    #----------------------------------------------------------------------
    def unregister(self, type_, handler):
        """注销事件处理函数监听"""
        # 尝试获取该事件类型对应的处理函数列表，若无则忽略该次注销请求   
        handlerList = self.__handlers[type_]
            
        # 如果该函数存在于列表中，则移除
        if handler in handlerList:
            handlerList.remove(handler)

        # 如果函数列表为空，则从引擎中移除该事件类型
        if not handlerList:
            del self.__handlers[type_]  
        
    #----------------------------------------------------------------------
    def put(self, event):
        """向事件队列中存入事件"""
        self.__queue.put(event)

    #----------------------------------------------------------------------
    @property
    def pendingSize(self):
        return len(self.__queue)

    #----------------------------------------------------------------------
    def registerGeneralHandler(self, handler):
        """注册通用事件处理函数监听"""
        if handler not in self.__generalHandlers:
            self.__generalHandlers.append(handler)
            
    #----------------------------------------------------------------------
    def unregisterGeneralHandler(self, handler):
        """注销通用事件处理函数监听"""
        if handler in self.__generalHandlers:
            self.__generalHandlers.remove(handler)


########################################################################
class Event:
    """事件对象"""

    #----------------------------------------------------------------------
    def __init__(self, type_=None):
        """Constructor"""
        self.type_ = type_      # 事件类型
        self.dict_ = {}         # 字典用于保存具体的事件数据


#----------------------------------------------------------------------
def test():
    """测试函数"""
    import sys
    from datetime import datetime
    from qtpy.QtCore import QCoreApplication
    
    def simpletest(event):
        print(u'处理每秒触发的计时器事件：{}'.format(str(datetime.now())))
    
    app = QCoreApplication(sys.argv)
    
    ee = EventChannel()
    #ee.register(EventChannel.EVENT_TIMER, simpletest)
    ee.registerGeneralHandler(simpletest)
    ee.start()
    
    app.exec_()
