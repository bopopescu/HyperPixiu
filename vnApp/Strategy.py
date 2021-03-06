# encoding: UTF-8

'''
本文件包含了CTA引擎中的策略开发用模板，开发策略时需要继承Strategy类。
'''

import numpy as np
import talib

from .Account import *
from .MainRoutine import *
from .MarketData import TickData, KLineData, TickToKLineMerger, KlineToXminMerger
from .EventChannel import EventChannel, EventData, datetime2float


########################################################################
class Strategy(object):
    # 策略类的名称和作者
    className = 'Strategy'
    author = EventData.EMPTY_UNICODE
    
    # MongoDB数据库的名称，K线数据库默认为1分钟
    tickDbName = TICK_DB_NAME
    barDbName = MINUTE_DB_NAME
    
    # 策略的基本参数
    name = EventData.EMPTY_UNICODE           # 策略实例名称
    productClass = EventData.EMPTY_STRING    # 产品类型（只有IB接口需要）
    currency = EventData.EMPTY_STRING        # 货币（只有IB接口需要）
    
    # 策略的基本变量，由引擎管理
    inited = False                 # 是否进行了初始化
    trading = False                # 是否启动交易，由引擎管理
    pos = 0                        # 持仓情况
    _posAvail = 0                  # 持仓情况
    
    # 参数列表，保存了参数的名称
    paramList = ['name',
                 'className',
                 'author']
    
    # 变量列表，保存了变量的名称
    varList = ['inited',
               'trading',
               'pos']
    
    # 同步列表，保存了需要保存到数据库的变量名称
    syncList = ['pos']

    #----------------------------------------------------------------------
    def __init__(self, trader, account, setting):
        """Constructor"""
        self.account = account
        self._trader = trader

        # 设置策略的参数
        if setting:
            d = self.__dict__
            for key in self.paramList:
                if key in setting:
                    d[key] = setting[key]

        # the instance Id
        self._id = setting.id('')
        if len(self._id)<=0 :
            Account.__lastId__ +=1
            self._id = '%s@%s' % (self.__class__.__name__, account.ident)

    @property
    def id(self):
        return self._id
    
    #----------------------------------------------------------------------
    def onInit(self):
        """初始化策略（必须由用户继承实现）"""
        raise NotImplementedError
    
    #----------------------------------------------------------------------
    def onStart(self):
        """启动策略（必须由用户继承实现）"""
        raise NotImplementedError
    
    #----------------------------------------------------------------------
    def onStop(self):
        """停止策略（必须由用户继承实现）"""
        raise NotImplementedError

    #----------------------------------------------------------------------
    def onTick(self, tick):
        """收到行情TICK推送（必须由用户继承实现）"""
        raise NotImplementedError

    #----------------------------------------------------------------------
    def onOrder(self, order):
        """收到委托变化推送（必须由用户继承实现）"""
        raise NotImplementedError
    
    #----------------------------------------------------------------------
    def onTrade(self, trade):
        """收到成交推送（必须由用户继承实现）"""
        raise NotImplementedError
    
    #----------------------------------------------------------------------
    def onBar(self, bar):
        """收到Bar推送（必须由用户继承实现）"""
        raise NotImplementedError
    
    #----------------------------------------------------------------------
    def onDayOpen(self, date):
        """收到交易日开始推送"""
        pass

    #----------------------------------------------------------------------
    def onStopOrder(self, so):
        """收到停止单推送（必须由用户继承实现）"""
        raise NotImplementedError
    
    #----------------------------------------------------------------------
    def _buy(self, symbol, price, volume, stop=False):
        """买开"""
        return self.sendOrder(OrderData.ORDER_BUY, symbol, price, volume, stop)
    
    #----------------------------------------------------------------------
    def _sell(self, symbol, price, volume, stop=False):
        """卖平"""
        return self.sendOrder(OrderData.ORDER_SELL, symbol, price, volume, stop)       

    #----------------------------------------------------------------------
    def _short(self, symbol, price, volume, stop=False):
        """卖开"""
        return self.sendOrder(OrderData.ORDER_SHORT, symbol, price, volume, stop)          
 
    #----------------------------------------------------------------------
    def _cover(self, symbol, price, volume, stop=False):
        """买平"""
        return self.sendOrder(OrderData.ORDER_COVER, symbol, price, volume, stop)
        
    #----------------------------------------------------------------------
    def sendOrder(self, orderType, symbol, price, volume, stop=False):
        """发送委托"""
        if not self.trading:
            # 交易停止时发单返回空字符串
            return []
        
        # 如果stop为True，则意味着发本地停止单
        # self.log(u'sendOrder:%s %.2fx%d>%s' %(orderType, price, volume, stop))
        if stop:
            vtOrderIDList = self.account.sendStopOrder(symbol, orderType, price, volume, self)
        else:
            vtOrderIDList = self.account.sendOrder(symbol, orderType, price, volume, self) 

        return vtOrderIDList
        
    #----------------------------------------------------------------------
    def cancelOrder(self, vtOrderID):
        """撤单"""
        # 如果发单号为空字符串，则不进行后续操作
        if not vtOrderID:
            return
        
        if OrderData.STOPORDERPREFIX in vtOrderID:
            self.account.cancelStopOrder(vtOrderID)
        else:
            self.account.cancelOrder(vtOrderID)
            
    #----------------------------------------------------------------------
    def cancelAll(self, symbol=None):
        """全部撤单"""
        l = self.account.findOrdersOfStrategy(self._id, symbol)

        orderIdList = []
        for o in l:
            orderIdList.append(o.brokerOrderId)
        if len(orderIdList) <=0:
            return
            
        self.account.batchCancel(orderIdList)
        self.log2(LOGLEVEL_INFO, 'cancelAll() symbol[%s] order-batch: %s' %(symbol, orderIdList))
    
    #----------------------------------------------------------------------
    def log2(self, loglevel, content):
        """记录CTA日志"""
        self._trader.log(loglevel, 'stg[%s] %s' %(self._id, content))

    def log(self, content):
        """记录CTA日志"""
        self.log2(LOGLEVEL_DEBUG, content)
        
    #----------------------------------------------------------------------
    def putEvent(self):
        """发出策略状态变化事件"""
        self._trader.postStrategyEvent(self.name)
        
    #----------------------------------------------------------------------
    def getEngineType(self):
        """查询当前运行的环境"""
        return self.account.engineType
    
    #----------------------------------------------------------------------
    def saveSyncData(self):
        """保存策略的持仓情况到数据库"""
        # if not self.trading : # or not self._trader:
        #     return

        # flt = {'name': self.name,
        #        'vtSymbol': self.vtSymbol,
        #        'account': self.account.ident
        #        }
        
        # d = copy(flt)
        # for key in strategy.syncList:
        #     d[key] = strategy.__getattribute__(key)
        
        # self._trader.dbUpdate(POSITION_DB_NAME, strategy.className, d, flt, True)
        # self._trader.log(u'策略%s同步数据保存成功，当前持仓%s' %(strategy.name, strategy.pos))

    # def loadSyncData(self, strategy):
    #     """从数据库载入策略的持仓情况"""
    #     flt = {'name': self.name,
    #            'vtSymbol': self.vtSymbol,
    #            'account': account.ident
    #            }

    #     syncData = self.dbQuery(POSITION_DB_NAME, strategy.className, flt)
        
    #     if not syncData:
    #         return
        
    #     d = syncData[0]
    #     for key in strategy.syncList:
    #         if key in d:
    #             strategy.__setattr__(key, d[key])
    
    #----------------------------------------------------------------------
    @property
    def priceTick(self):
        """查询最小价格变动"""
        return self.account.getPriceTick(self)
        
########################################################################
class StrategyOfSymbol(Strategy):
    ''' per symbol+account 策略类 '''

    #----------------------------------------------------------------------
    def __init__(self, trader, symbol, account, setting):
        """Constructor"""
        super(StrategyOfSymbol, self).__init__(trader, account, setting)
        self._symbol = symbol

        # the instance Id
        if self._id != setting.id("") :
            self._id += '.%s' % symbol

    @property
    def vtSymbol(self):
        return self._symbol

    #----------------------------------------------------------------------
    def buy(self, price, volume, stop=False):
        """买开"""
        return super(StrategyOfSymbol, self)._buy(self._symbol, price, volume, stop)

    def sell(self, price, volume, stop=False):
        """卖平"""
        return super(StrategyOfSymbol, self)._sell(self._symbol, price, volume, stop)

    def short(self, symbol, price, volume, stop=False):
        """卖开"""
        return super(StrategyOfSymbol, self)._short(self._symbol, price, volume, stop)

    def cover(self, symbol, price, volume, stop=False):
        """买平"""
        return super(StrategyOfSymbol, self)._cover(self._symbol, price, volume, stop)
        
    def cancelAll(self):
        return super(StrategyOfSymbol, self).cancelAll(self._symbol)

    #----------------------------------------------------------------------
    def insertTick(self, tick):
        """向数据库中插入tick数据"""
        self.account.insertData(self.tickDbName, self._symbol, tick)
    
    def insertBar(self, bar):
        """向数据库中插入bar数据"""
        self.account.insertData(self.barDbName, self._symbol, bar)
        
    def loadTick(self, days):
        """读取tick数据"""
        return self.account.loadTick(self.tickDbName, self._symbol, days)
    
    def loadBar(self, days):
        """读取bar数据"""
        return self.account.loadBar(self.barDbName, self._symbol, days)


########################################################################
class TargetPosTemplate(Strategy):
    """
    允许直接通过修改目标持仓来实现交易的策略模板
    
    开发策略时，无需再调用buy/sell/cover/short这些具体的委托指令，
    只需在策略逻辑运行完成后调用setTargetPos设置目标持仓，底层算法
    会自动完成相关交易，适合不擅长管理交易挂撤单细节的用户。    
    
    使用该模板开发策略时，请在以下回调方法中先调用母类的方法：
    onTick
    onBar
    onOrder
    
    假设策略名为TestStrategy，请在onTick回调中加上：
    super(TestStrategy, self).onTick(tick)
    
    其他方法类同。
    """
    
    className = 'TargetPosTemplate'
    author = u'量衍投资'
    
    # 目标持仓模板的基本变量
    tickAdd = 1             # 委托时相对基准价格的超价
    lastTick = None         # 最新tick数据
    lastBar = None          # 最新bar数据
    targetPos = EventData.EMPTY_INT   # 目标持仓
    orderList = []          # 委托号列表

    # 变量列表，保存了变量的名称
    varList = ['inited',
               'trading',
               'pos',
               'targetPos']

    #----------------------------------------------------------------------
    def __init__(self, account, setting):
        """Constructor"""
        super(TargetPosTemplate, self).__init__(account, setting)
        
    #----------------------------------------------------------------------
    def onTick(self, tick):
        """收到行情推送"""
        self.lastTick = tick
        
        # 实盘模式下，启动交易后，需要根据tick的实时推送执行自动开平仓操作
        if self.trading:
            self.trade()
        
    #----------------------------------------------------------------------
    def onBar(self, bar):
        """收到K线推送"""
        self.lastBar = bar
    
    #----------------------------------------------------------------------
    def onOrder(self, order):
        """收到委托推送"""
        if order.status == OrderData.STATUS_ALLTRADED or order.status == OrderData.STATUS_CANCELLED:
            if order.vtOrderID in self.orderList:
                self.orderList.remove(order.vtOrderID)
    
    #----------------------------------------------------------------------
    def setTargetPos(self, symbol, targetPos):
        """设置目标仓位"""
        self.targetPos = targetPos
        
        self.trade()
        
    #----------------------------------------------------------------------
    def trade(self, symbol):
        """执行交易"""
        # 先撤销之前的委托
        self.cancelAll(symbol)
        
        # 如果目标仓位和实际仓位一致，则不进行任何操作
        posChange = self.targetPos - self.pos
        if not posChange:
            return
        
        # 确定委托基准价格，有tick数据时优先使用，否则使用bar
        longPrice = 0
        shortPrice = 0
        
        if self.lastTick:
            if posChange > 0:
                longPrice = self.lastTick.a1P + self.tickAdd
                if self.lastTick.upperLimit:
                    longPrice = min(longPrice, self.lastTick.upperLimit)         # 涨停价检查
            else:
                shortPrice = self.lastTick.b1P - self.tickAdd
                if self.lastTick.lowerLimit:
                    shortPrice = max(shortPrice, self.lastTick.lowerLimit)       # 跌停价检查
        else:
            if posChange > 0:
                longPrice = self.lastBar.close + self.tickAdd
            else:
                shortPrice = self.lastBar.close - self.tickAdd
        
        # 回测模式下，采用合并平仓和反向开仓委托的方式
        if self.getEngineType() == ENGINETYPE_BACKTESTING:
            if posChange > 0:
                l = self.buy(symbol, longPrice, abs(posChange))
            else:
                l = self.short(shortPrice, abs(posChange))
            self.orderList.extend(l)
        
        # 实盘模式下，首先确保之前的委托都已经结束（全成、撤销）
        # 然后先发平仓委托，等待成交后，再发送新的开仓委托
        else:
            # 检查之前委托都已结束
            if self.orderList:
                return
            
            # 买入
            if posChange > 0:
                # 若当前有空头持仓
                if self.pos < 0:
                    # 若买入量小于空头持仓，则直接平空买入量
                    if posChange < abs(self.pos):
                        l = self.cover(longPrice, posChange)
                    # 否则先平所有的空头仓位
                    else:
                        l = self.cover(longPrice, abs(self.pos))
                # 若没有空头持仓，则执行开仓操作
                else:
                    l = self.buy(symbol, longPrice, abs(posChange))
            # 卖出和以上相反
            else:
                if self.pos > 0:
                    if abs(posChange) < self.pos:
                        l = self.sell(shortPrice, abs(posChange))
                    else:
                        l = self.sell(shortPrice, abs(self.pos))
                else:
                    l = self.short(shortPrice, abs(posChange))
            self.orderList.extend(l)
    

########################################################################
class ArrayManager(object):
    """
    K线序列管理工具，负责：
    1. K线时间序列的维护
    2. 常用技术指标的计算
    """

    #----------------------------------------------------------------------
    def __init__(self, size=100):
        """Constructor"""
        self.count = 0                      # 缓存计数
        self.size = size                    # 缓存大小
        self.inited = False                 # True if count>=size
        
        self.openArray = np.zeros(size)     # OHLC
        self.highArray = np.zeros(size)
        self.lowArray = np.zeros(size)
        self.closeArray = np.zeros(size)
        self.volumeArray = np.zeros(size)
        
    #----------------------------------------------------------------------
    def updateBar(self, bar):
        """更新K线"""
        self.count += 1
        if not self.inited and self.count >= self.size:
            self.inited = True
        
        self.openArray[0:self.size-1] = self.openArray[1:self.size]
        self.highArray[0:self.size-1] = self.highArray[1:self.size]
        self.lowArray[0:self.size-1] = self.lowArray[1:self.size]
        self.closeArray[0:self.size-1] = self.closeArray[1:self.size]
        self.volumeArray[0:self.size-1] = self.volumeArray[1:self.size]
    
        self.openArray[-1] = bar.open
        self.highArray[-1] = bar.high
        self.lowArray[-1] = bar.low        
        self.closeArray[-1] = bar.close
        self.volumeArray[-1] = bar.volume
        
    #----------------------------------------------------------------------
    @property
    def open(self):
        """获取开盘价序列"""
        return self.openArray
        
    #----------------------------------------------------------------------
    @property
    def high(self):
        """获取最高价序列"""
        return self.highArray
    
    #----------------------------------------------------------------------
    @property
    def low(self):
        """获取最低价序列"""
        return self.lowArray
    
    #----------------------------------------------------------------------
    @property
    def close(self):
        """获取收盘价序列"""
        return self.closeArray
    
    #----------------------------------------------------------------------
    @property    
    def volume(self):
        """获取成交量序列"""
        return self.volumeArray
    
    #----------------------------------------------------------------------
    def sma(self, n, array=False):
        """简单均线"""
        result = talib.SMA(self.close, n)
        if array:
            return result
        return result[-1]
        
    #----------------------------------------------------------------------
    def std(self, n, array=False):
        """标准差"""
        result = talib.STDDEV(self.close, n)
        if array:
            return result
        return result[-1]
    
    #----------------------------------------------------------------------
    def cci(self, n, array=False):
        """CCI指标"""
        result = talib.CCI(self.high, self.low, self.close, n)
        if array:
            return result
        return result[-1]
        
    #----------------------------------------------------------------------
    def atr(self, n, array=False):
        """ATR指标"""
        result = talib.ATR(self.high, self.low, self.close, n)
        if array:
            return result
        return result[-1]
        
    #----------------------------------------------------------------------
    def rsi(self, n, array=False):
        """RSI指标"""
        result = talib.RSI(self.close, n)
        if array:
            return result
        return result[-1]
    
    #----------------------------------------------------------------------
    def macd(self, fastPeriod, slowPeriod, signalPeriod, array=False):
        """MACD指标"""
        macd, signal, hist = talib.MACD(self.close, fastPeriod,
                                        slowPeriod, signalPeriod)
        if array:
            return macd, signal, hist
        return macd[-1], signal[-1], hist[-1]
    
    #----------------------------------------------------------------------
    def adx(self, n, array=False):
        """ADX指标"""
        result = talib.ADX(self.high, self.low, self.close, n)
        if array:
            return result
        return result[-1]
    
    #----------------------------------------------------------------------
    def boll(self, n, dev, array=False):
        """布林通道"""
        mid = self.sma(n, array)
        std = self.std(n, array)
        
        up = mid + std * dev
        down = mid - std * dev
        
        return up, down    
    
    #----------------------------------------------------------------------
    def keltner(self, n, dev, array=False):
        """肯特纳通道"""
        mid = self.sma(n, array)
        atr = self.atr(n, array)
        
        up = mid + atr * dev
        down = mid - atr * dev
        
        return up, down
    
    #----------------------------------------------------------------------
    def donchian(self, n, array=False):
        """唐奇安通道"""
        up = talib.MAX(self.high, n)
        down = talib.MIN(self.low, n)
        
        if array:
            return up, down
        return up[-1], down[-1]
    

########################################################################
class AShSignal(object):
    """
    CTA策略信号，负责纯粹的信号生成（目标仓位），不参与具体交易管理
    """

    #----------------------------------------------------------------------
    def __init__(self):
        """Constructor"""
        self.signalPos = 0      # 信号仓位
    
    #----------------------------------------------------------------------
    def onBar(self, bar):
        """K线推送"""
        pass
    
    #----------------------------------------------------------------------
    def onTick(self, tick):
        """Tick推送"""
        pass
        
    #----------------------------------------------------------------------
    def setSignalPos(self, pos):
        """设置信号仓位"""
        self.signalPos = pos
        
    #----------------------------------------------------------------------
    def getSignalPos(self):
        """获取信号仓位"""
        return self.signalPos
        
