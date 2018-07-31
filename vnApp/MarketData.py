# encoding: UTF-8

from __future__ import division

from vnpy.trader.vtConstant import *
from vnpy.trader.vtObject import VtBarData, VtTickData

########################################################################
class MarketData(object):
    # Market相关events
    EVENT_TICK = 'eTick.'                   # TICK行情事件，可后接具体的vtSymbol
    EVENT_MARKET_DEPTH0 = 'eMD0.'           # Market depth0
    EVENT_MARKET_DEPTH2 = 'eMD2.'           # Market depth2
    EVENT_KLINE_1MIN    = 'eKL1m.'
    EVENT_KLINE_5MIN    = 'eKL5m.'
    EVENT_KLINE_15MIN   = 'eKL15m.'
    EVENT_KLINE_30MIN   = 'eKL30m.'
    EVENT_KLINE_1HOUR   = 'eKL1h.'
    EVENT_KLINE_4HOUR   = 'eKL4h.'
    EVENT_KLINE_1DAY    = 'eKL1d.'

    DATA_SRCTYPE_MARKET     = 'market'
    DATA_SRCTYPE_IMPORT     = 'import'
    DATA_SRCTYPE_BACKTEST   = 'backtest'

    from abc import ABCMeta, abstractmethod

    #----------------------------------------------------------------------
    def __init__(self, eventChannel, settings, srcType=DATA_SRCTYPE_MARKET):
        """Constructor"""

        self._eventCh = eventChannel
        self._sourceType = srcType

        self._active = False
        self.subDict = {}
        
        self.proxies = {}
    
    #----------------------------------------------------------------------
    @property
    def active(self):
        return self._active

    @property
    def subscriptions(self):
        return self.subDict
        
    #----------------------------------------------------------------------
    @abstractmethod
    def connect(self):
        """连接"""
        raise NotImplementedError
        return self.active
        
    #----------------------------------------------------------------------
    @abstractmethod
    def close(self):
        """停止"""
        if self._active:
            self._active = False

        raise NotImplementedError
        
    #----------------------------------------------------------------------
    def subscribeKey(self, symbol, eventType):
        key = '%s>%s' %(eventType, symbol)
        return key

    #----------------------------------------------------------------------
    # return eventType, symbol
    def chopSubscribeKey(self, key):
        pos = key.find('>')
        return key[:pos], key[pos+1:]

    #----------------------------------------------------------------------
    @abstractmethod
    def subscribe(self, symbol, eventType =EVENT_TICK):
        """订阅成交细节"""
        raise NotImplementedError

    #----------------------------------------------------------------------
    def unsubscribe(self, symbol, eventType):
        """取消订阅主题"""
        key = self.subscribeKey(symbol, eventType)
        if key not in self.subDict:
            return

        self.doUnsubscribe(key)
        del self.subDict[key]

    #----------------------------------------------------------------------
    @abstractmethod
    def doUnsubscribe(self, key):
        """取消订阅主题"""
        raise NotImplementedError

    #----------------------------------------------------------------------
    @abstractmethod
    def onError(self, msg):
        """错误推送"""
        print (msg)
        
    #----------------------------------------------------------------------
    @abstractmethod
    def postMarketEvent(self, event):
        if self._eventCh ==None:
            return

        self._eventCh.put(event)
    
 
########################################################################
class mdTickData(VtTickData):
    """Tick行情数据类"""

    #----------------------------------------------------------------------
    def __init__(self, md):
        """Constructor"""
        super(mdTickData, self).__init__()
        
        self.exchange   = md._exchange
        self.sourceType = md._sourceType          # 数据来源类型
    
########################################################################
class mdKLineData(VtBarData):
    """K线数据"""

    #----------------------------------------------------------------------
    def __init__(self, md):
        """Constructor"""
        super(mdKLineData, self).__init__()
        
        self.exchange   = md._exchange
        self.sourceType = md._sourceType          # 数据来源类型