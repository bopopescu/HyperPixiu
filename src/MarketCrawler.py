# encoding: UTF-8

from __future__ import division

from Application import BaseApplication
from EventData import datetime2float
from MarketData import *
from Perspective import PerspectiveState

import traceback
from datetime import datetime

from abc import ABCMeta, abstractmethod

########################################################################
class MarketCrawler(BaseApplication):
    ''' abstract application to observe market
    '''
    __lastId__ =100

    #----------------------------------------------------------------------
    def __init__(self, program, marketState, recorder=None, **kwargs):
        '''Constructor
        '''
        super(MarketCrawler, self).__init__(program, **kwargs)

        self._recorder = recorder
        self._symbolsToPoll = []

        # MarketCrawler is supposed to focus on the most recent event to process, but it MAY also grab
        # some historical data in order to complete the perspective
        # The following config help to ONLY deliver the recent events to the EventChannel
        self._timeoutToPostEvent = self.getConfig('timeoutToPostEvent', 120.0) # 2min to stop barking those old data crawled
        self._eventsToPost       = self.getConfig('eventsToPost', [])

        self.__marketStateToUpdate = marketState

        # the MarketData instance Id
        # self._id = settings.id("")
        # if len(self._id)<=0 :
        #     MarketData.__lastId__ +=1
        #     self._id = 'MD%d' % MarketData.__lastId__

        # self._mr = program
        # self._eventCh  = program._eventLoop
        # self._exchange = settings.exchange(self._id)

        self._steps = []
        self._stepAsOf =0
        self.__genSteps={}
    
    #----------------------------------------------------------------------
    @property
    def marketState(self) :
        return self.__marketStateToUpdate

    @property
    def subscriptions(self):
        return self.subDict

    # def attachMarketState(self, marketState) :
    #     if marketState:
    #         self.__marketStateToUpdate = marketState

    #----------------------------------------------------------------------
    # inqueries to some market data
    # https://www.cnblogs.com/bradleon/p/6106595.html
    def query(self, symbol, eventType, since, cortResp=None):
        ''' 查询请求
        will call cortResp.send(csvline) when the result comes
        '''
        scale =1200
        if (eventType == EVENT_TICK) :
            scale=0
        elif (eventType == EVENT_TICK) :
            scale = 1
        
        url = "http://money.finance.sina.com.cn/quotes_service/api/json_v2.php/CN_MarketData.getKLineData?scale=5&datalen=1000" % (scale1min, linesExpected)

        req = (uri, httpParams, reqData, funcMethod, callbackResp)

        self.enqueue(reqId, req)
        return reqId
   
    def subscribe(self, symbols):
        """订阅成交细节"""
        c =0
        for s in symbols:
            if s in self._symbolsToPoll:
                continue

            self._symbolsToPoll.append(s)
            c +=1
        
        if c <=0:
            return c
        
        self._symbolsToPoll.sort()
        return c

    def unsubscribe(self, symbols):
        """取消订阅主题"""
        c = len(self._symbolsToPoll)
        for s in symbols:
            self._symbolsToPoll.remove(s)
        
        if c ==len(self._symbolsToPoll):
            return c
        
        self._symbolsToPoll.sort()
        return len(self._symbolsToPoll)

    #--- new methods defined in MarketCrawler ---------
    # if the MarketData has background thread, connect() will not start the thread
    # but start() will
    def connect(self):
        '''
        return True if connected 
        '''
        return True

    def close(self):
        pass

    #--- impl/overwrite of BaseApplication -----------------------
    def doAppInit(self): # return True if succ
        if not super(MarketCrawler, self).doAppInit() :
            return False

        if not self.__marketStateToUpdate :
            self.__marketStateToUpdate = PerspectiveState(exchange="na") # dummy state if not specified

        self.info("doAppInit() %d symbols subcribed: %s" %(len(self._symbolsToPoll), ','.join(self._symbolsToPoll)))
        return self.connect()

    def OnEvent(self, event):
        '''
        process the event
        '''
        pass

    def doAppStep(self):
        '''
        @return True if busy at this step
        '''
        self._stepAsOf = datetime2float(datetime.now())
        cBusy = 0
        cStepped =0

        for s in self._steps:
            cStepped +=1
            cBusy += s()
            # if not s in self.__genSteps.keys() or not self.__genSteps[s] :
            #     self.__genSteps[s] = s()
            # try :
            #     if next(self.__genSteps[s]) :
            #         busy = True
            # except StopIteration:
            #     self.__genSteps[s] = None
        if self._threadWished and cBusy<=0:
            sleep(0.5)

        return (cBusy >0)

    def stop(self):
        super(MarketCrawler, self).stop()
        self.close()
        
    #----------------------------------------------------------------------
    def fmtSubscribeKey(self, symbol, eventType):
        key = '%s>%s' %(eventType, symbol)
        return key

    def chopSubscribeKey(self, key):
        ''' chop the pair (eventType, symbol) out of a given key
        '''
        pos = key.find('>')
        return key[:pos], key[pos+1:]

    def OnEventCaptured(self, ev):
        if self._recorder:
            self._recorder.pushRow(ev.type, ev.data)

        # eliminate some events with no interests
        if len(self._eventsToPost) >0 and not ev.type in self._eventsToPost:
            return

        # eliminate some old events crawled to messup eventchannel
        if self._timeoutToPostEvent and self._timeoutToPostEvent >0:
            ftimeExp = datetime2float(datetime.now()) - self._timeoutToPostEvent
            if datetime2float(ev.data.asof) < ftimeExp:
                return
        
        self.postEvent(ev)

    #----------------------------------------------------------------------
    def onError(self, msg):
        """错误推送"""
        self.error(msg)
        
