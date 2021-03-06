# encoding: UTF-8

'''
CTA模块相关的GUI控制组件
'''


from vnpy.event import Event
from vnpy.trader.vtEvent import *
from vnpy.trader.uiBasicWidget import QtGui, QtCore, QtWidgets, BasicCell

from .Account import EVENT_LOG, EVENT_STRATEGY
from .language import text


########################################################################
class ValueMonitor(QtWidgets.QTableWidget):
    """参数监控"""

    #----------------------------------------------------------------------
    def __init__(self, parent=None):
        """Constructor"""
        super(AShValueMonitor, self).__init__(parent)
        
        self.keyCellDict = {}
        self.data = None
        self.inited = False
        
        self.initUi()
        
    #----------------------------------------------------------------------
    def initUi(self):
        """初始化界面"""
        self.setRowCount(1)
        self.verticalHeader().setVisible(False)
        self.setEditTriggers(self.NoEditTriggers)
        
        self.setMaximumHeight(self.sizeHint().height())
        
    #----------------------------------------------------------------------
    def updateData(self, data):
        """更新数据"""
        if not self.inited:
            self.setColumnCount(len(data))
            self.setHorizontalHeaderLabels(data.keys())
            
            col = 0
            for k, v in data.items():
                cell = QtWidgets.QTableWidgetItem(unicode(v))
                self.keyCellDict[k] = cell
                self.setItem(0, col, cell)
                col += 1
            
            self.inited = True
        else:
            for k, v in data.items():
                cell = self.keyCellDict[k]
                cell.setText(unicode(v))


########################################################################
class StrategyManager(QtWidgets.QGroupBox):
    """策略管理组件"""
    signal = QtCore.Signal(type(Event()))

    #----------------------------------------------------------------------
    def __init__(self, account, eventChannel, name, parent=None):
        """Constructor"""
        super(AShStrategyManager, self).__init__(parent)
        
        self.account = account
        self._eventChannel = eventChannel
        self.name = name
        
        self.initUi()
        self.updateMonitor()
        self.registerEvent()
        
    #----------------------------------------------------------------------
    def initUi(self):
        """初始化界面"""
        self.setTitle(self.name)
        
        self.paramMonitor = AShValueMonitor(self)
        self.varMonitor = AShValueMonitor(self)
        
        height = 65
        self.paramMonitor.setFixedHeight(height)
        self.varMonitor.setFixedHeight(height)
        
        buttonInit = QtWidgets.QPushButton(text.INIT)
        buttonStart = QtWidgets.QPushButton(text.START)
        buttonStop = QtWidgets.QPushButton(text.STOP)
        buttonInit.clicked.connect(self.init)
        buttonStart.clicked.connect(self.start)
        buttonStop.clicked.connect(self.stop)
        
        hbox1 = QtWidgets.QHBoxLayout()     
        hbox1.addWidget(buttonInit)
        hbox1.addWidget(buttonStart)
        hbox1.addWidget(buttonStop)
        hbox1.addStretch()
        
        hbox2 = QtWidgets.QHBoxLayout()
        hbox2.addWidget(self.paramMonitor)
        
        hbox3 = QtWidgets.QHBoxLayout()
        hbox3.addWidget(self.varMonitor)
        
        vbox = QtWidgets.QVBoxLayout()
        vbox.addLayout(hbox1)
        vbox.addLayout(hbox2)
        vbox.addLayout(hbox3)

        self.setLayout(vbox)
        
    #----------------------------------------------------------------------
    def updateMonitor(self):
        """显示策略最新状态"""
        paramDict = self.account.getStrategyParam(self.name)
        if paramDict:
            self.paramMonitor.updateData(paramDict)
            
        varDict = self.account.getStrategyVar(self.name)
        if varDict:
            self.varMonitor.updateData(varDict)        
    
    #----------------------------------------------------------------------
    def updateVar(self, event):
        """更新策略变量"""
        data = event.dict_['data']
        self.varMonitor.updateData(data)
    
    #----------------------------------------------------------------------
    def registerEvent(self):
        """注册事件监听"""
        self.signal.connect(self.updateVar)
        self._eventChannel.register(EVENT_STRATEGY+self.name, self.signal.emit)
    
    #----------------------------------------------------------------------
    def init(self):
        """初始化策略"""
        self.account.initStrategy(self.name)
    
    #----------------------------------------------------------------------
    def start(self):
        """启动策略"""
        self.account.startStrategy(self.name)
        
    #----------------------------------------------------------------------
    def stop(self):
        """停止策略"""
        self.account.stopStrategy(self.name)


########################################################################
class EngineManager(QtWidgets.QWidget):
    """CTA引擎管理组件"""
    signal = QtCore.Signal(type(Event()))

    #----------------------------------------------------------------------
    def __init__(self, account, eventChannel, parent=None):
        """Constructor"""
        super(AShEngineManager, self).__init__(parent)
        
        self.account = account
        self._eventChannel = eventChannel
        
        self.strategyLoaded = False
        
        self.initUi()
        self.registerEvent()
        
        # 记录日志
        self.account.log(text.CTA_ENGINE_STARTED)        
        
    #----------------------------------------------------------------------
    def initUi(self):
        """初始化界面"""
        self.setWindowTitle(text.CTA_STRATEGY)
        
        # 按钮
        loadButton = QtWidgets.QPushButton(text.LOAD_STRATEGY)
        initAllButton = QtWidgets.QPushButton(text.INIT_ALL)
        startAllButton = QtWidgets.QPushButton(text.START_ALL)
        stopAllButton = QtWidgets.QPushButton(text.STOP_ALL)
        
        loadButton.clicked.connect(self.load)
        initAllButton.clicked.connect(self.initAll)
        startAllButton.clicked.connect(self.startAll)
        stopAllButton.clicked.connect(self.stopAll)
        
        # 滚动区域，放置所有的AShStrategyManager
        self.scrollArea = QtWidgets.QScrollArea()
        self.scrollArea.setWidgetResizable(True)
        
        # CTA组件的日志监控
        self.ashLogMonitor = QtWidgets.QTextEdit()
        self.ashLogMonitor.setReadOnly(True)
        self.ashLogMonitor.setMaximumHeight(200)
        
        # 设置布局
        hbox2 = QtWidgets.QHBoxLayout()
        hbox2.addWidget(loadButton)
        hbox2.addWidget(initAllButton)
        hbox2.addWidget(startAllButton)
        hbox2.addWidget(stopAllButton)
        hbox2.addStretch()
        
        vbox = QtWidgets.QVBoxLayout()
        vbox.addLayout(hbox2)
        vbox.addWidget(self.scrollArea)
        vbox.addWidget(self.ashLogMonitor)
        self.setLayout(vbox)
        
    #----------------------------------------------------------------------
    def initStrategyManager(self):
        """初始化策略管理组件界面"""        
        w = QtWidgets.QWidget()
        vbox = QtWidgets.QVBoxLayout()
        
        l = self.account.getStrategyNames()
        for name in l:
            strategyManager = AShStrategyManager(self.account, self._eventChannel, name)
            vbox.addWidget(strategyManager)
        
        vbox.addStretch()
        
        w.setLayout(vbox)
        self.scrollArea.setWidget(w)   
        
    #----------------------------------------------------------------------
    def initAll(self):
        """全部初始化"""
        self.account.initAll()    
            
    #----------------------------------------------------------------------
    def startAll(self):
        """全部启动"""
        self.account.startAll()
            
    #----------------------------------------------------------------------
    def stopAll(self):
        """全部停止"""
        self.account.stopAll()
            
    #----------------------------------------------------------------------
    def load(self):
        """加载策略"""
        if not self.strategyLoaded:
            self.account.loadSetting()
            self.initStrategyManager()
            self.strategyLoaded = True
            self.account.log(text.STRATEGY_LOADED)
        
    #----------------------------------------------------------------------
    def updateAShLog(self, event):
        """更新CTA相关日志"""
        log = event.dict_['data']
        content = '\t'.join([log.logTime, log.logContent])
        self.ashLogMonitor.append(content)
    
    #----------------------------------------------------------------------
    def registerEvent(self):
        """注册事件监听"""
        self.signal.connect(self.updateAShLog)
        self._eventChannel.register(EVENT_LOG, self.signal.emit)

    
    
    
    



    
    