# encoding: UTF-8
'''
GymTrader impls BaseTrader and represent itself as a Gym Environment
'''
from __future__ import division

# from gym import GymEnv
from Account import Account, OrderData, Account_AShare
from Trader import MetaTrader, BaseTrader
import hpGym

from abc import ABC, abstractmethod
import matplotlib as mpl # pip install matplotlib
import matplotlib.pyplot as plt
import numpy as np

plt.style.use('dark_background')
mpl.rcParams.update(
    {
        "font.size": 15,
        "axes.labelsize": 15,
        "lines.linewidth": 1,
        "lines.markersize": 8
    }
)

########################################################################
class GymTrader(BaseTrader):
    '''
    GymTrader impls BaseTrader and represent itself as a Gym Environment
    '''
    ACTION_BUY  = OrderData.ORDER_BUY
    ACTION_SELL = OrderData.ORDER_SELL
    ACTION_HOLD = 'HOLD'

    ACTIONS = {
        ACTION_HOLD: np.array([1, 0, 0]),
        ACTION_BUY:  np.array([0, 1, 0]),
        ACTION_SELL: np.array([0, 0, 1])
    }

    POS_DIRECTIONS = {
        OrderData.DIRECTION_NONE:  np.array([1, 0, 0]),
        OrderData.DIRECTION_LONG:  np.array([0, 1, 0]),
        OrderData.DIRECTION_SHORT: np.array([0, 0, 1])
    }

    def __init__(self, program, agentClass=None, **kwargs):
        '''Constructor
        '''
        super(GymTrader, self).__init__(program, **kwargs) # redirect to BaseTrader, who will adopt account and so on

        self.__agent = None
        self._timeCostYrRate = self.getConfig('timeCostYrRate', 0)
        #TODO: the separate the Trader for real account and training account
        
        self.__1stRender = True

        agentType = self.getConfig('agent/type', 'DQN')
        if agentType and agentType in hpGym.GYMAGENT_CLASS.keys():
            AGENTCLASS = hpGym.GYMAGENT_CLASS[agentType]
            agentKwArgs = self.getConfig('agent', {})
            self.__agent = AGENTCLASS(self, jsettings=self.subConfig('agent'), **agentKwArgs)

        # self.n_actions = 3
        # self._prices_history = []

    #----------------------------------------------------------------------
    # impl/overwrite of BaseApplication
    def doAppInit(self): # return True if succ
        if not super(GymTrader, self).doAppInit() :
            return False
        # the self._account should be good here

        # step 1. GymTrader always take PerspectiveDict as the market state
        self._marketState = self._account._marketState
        if not self._marketState or not isinstance(self._marketState, PerspectiveDict):
            self._marketState = PerspectiveDict(self._account.exchange)
            self._account._marketState = self._marketState

        self._gymState = self.gymReset() # will perform self._action = ACTIONS[ACTION_HOLD]
        return True

    def doAppStep(self):
        super(GymTrader, self).doAppStep()
        # seems nothing else to do

    def OnEvent(self, ev): 
        # step 2. 收到行情后，在启动策略前的处理
        self._marketState.updateByEvent(ev)
        self._action = self._agent.gymAct(self._gymState)
        next_state, reward, done, _ = self.gymStep(self._action)
        loss = self._agent.gymObserve(self._gymState, self._action, reward, next_state, done)
        self._gymState = next_state

    #------------------------------------------------
    # GymEnv related methods
    def gymReset(self) :
        '''
        reset the gym environment, will be called when each episode starts
        reset the trading environment / rewards / data generator...
        @return:
            observation (numpy.array): observation of the state
        '''
        self.__closed_plot = False
        self.__stepNo = 0

        observation = self.__build_gym_observation()
        self._shapeOfState = observation.shape
        self._action = self.ACTIONS[ACTION_HOLD]
        return observation

    def gymStep(self, action) :
        '''Take an action (buy/sell/hold) and computes the immediate reward.

        @param action (numpy.array): Action to be taken, one-hot encoded.

        Returns:
            tuple:
                - observation (numpy.array): Agent's observation of the current environment.
                - reward (float) : Amount of reward returned after previous action.
                - done (bool): Whether the episode has ended, in which case further step() calls will return undefined results.
                - info (dict): Contains auxiliary diagnostic information (helpful for debugging, and sometimes learning).
        '''
        assert any([(action == x).all() for x in self.ACTIONS.values()])
        self._action = action
        self.__stepNo += 1
        done = False
        instant_pnl = 0
        info = {}

        # step 1. collected information from the account
        cashAvail, cashTotal, positions = self.getAccountState()
        capitalBeforeStep = summrizeAccount(positions, cashTotal)

        # TODO: the first version only support one symbol to play, so simply take the first symbol in the positions        
        symbol = None # TODO: should take the __dictOberserves
        latestPrice = 0
        posAvail =0
        for s, pos in positions.values() :
            symbol =  s
            latestPrice = pos.price
            posAvailVol = pos.posAvail
            capitalBeforeStep += pos.price * pos.position * self._account.contractSize
            break

        reward = - self._timeCostYrRate # initialize with a time cost
        # reward = - capitalBeforeStep *self._timeCostYrRate/100/365

        if not symbol or latestPrice <=0:
            action = self.ACTIONS[ACTION_HOLD]
            return

        if capitalBeforeStep <=0:
            done = True

        # step 2. perform the action buy/sell/hold by driving self._account
        if all(action == self.ACTIONS[ACTION_BUY]):
            # TODO: the first version only support FULL-BUY and FULL-SELL
            price  = latestPrice + self._account.priceTick
            volume = round(cashAvail / latestPrice / self._account.contractSize, 0)
            vtOrderIDList = self._account.sendOrder(symbol, OrderData.ORDER_BUY, price, volume, strategy=None)
            # cash will be updated in callback onOrderPlaced()
            # turnover, commission, slippage = self._account.calcAmountOfTrade(symbol, price, volume)
            # reward -= commission + slippage # TODO maybe after the order is comfirmed
        elif all(action == self.ACTIONS[ACTION_SELL]) and posAvail >0:
            price  = latestPrice - self._account.priceTick
            if price <= self._account.priceTick :
                price = self._account.priceTick 

            volume = - posAvail
            vtOrderIDList = self._account.sendOrder(symbol, OrderData.ORDER_SELL, price, volume, strategy=None)
            # cash will be updated in callback onOrderPlaced()
            # turnover, commission, slippage = self._account.calcAmountOfTrade(symbol, price, volume)
            # reward -= commission + slippage # TODO maybe after the order is comfirmed
            # if positions[self._symbol] ==0:
            #     self._exit_price = calculate based on price and commision # TODO maybe after the order is comfirmed
            #     instant_pnl = self._entry_price - self._exit_price
            #     self._entry_price = 0

        # step 3. calculate the rewards
        capitalAfterStep = self.summrizeAccount() # most likely the cashAmount changed due to comission
        instant_pnl = capitalAfterStep - capitalBeforeStep
        reward += instant_pnl
        self._total_pnl += instant_pnl
        self._total_reward += reward

        ''' step 4. composing info for tracing

        try :
            self._market_state = self._envMarket.next()
        except StopIteration:
            done = True
            info['status'] = 'No more data.'
        if self.__stepNo >= self._iterationsPerEpisode:
            done = True
            info['status'] = 'Time out.'
        if self.__closed_plot:
            info['status'] = 'Closed plot'

        '''
        try:
            self._prices_history.append(self._data_generator.next())
        except StopIteration:
            done = True
            info['status'] = 'No more data.'
        if self.__stepNo >= self._iterationsPerEpisode:
            done = True
            info['status'] = 'Time out.'
        if self.__closed_plot:
            info['status'] = 'Closed plot'

        ''' step 5. combine account and market observations as final observations,
            then return
        observation = np.concatenate((self._account_state, self._market_state))
        '''
        observation = self.__build_gym_observation()
        return observation, reward, done, info
    
    def _handle_close(self, evt):
        self.__closed_plot = True

    def render(self, savefig=False, filename='myfig'):
        """Matlplotlib rendering of each step.

        @param savefig (bool): Whether to save the figure as an image or not.
        @param filename (str): Name of the image file.
        """
        if self.__1stRender:
            self._f, self._ax = plt.subplots(
                len(self._spread_coefficients) + int(len(self._spread_coefficients) > 1),
                sharex=True
            )

            if len(self._spread_coefficients) == 1:
                self._ax = [self._ax]

            self._f.set_size_inches(12, 6)
            self.__1stRender = False
            self._f.canvas.mpl_connect('close_event', self._handle_close)

        if len(self._spread_coefficients) > 1:
            # TODO: To be checked
            for prod_i in range(len(self._spread_coefficients)):
                bid = self._prices_history[-1][2 * prod_i]
                ask = self._prices_history[-1][2 * prod_i + 1]
                self._ax[prod_i].plot([self.__stepNo, self.__stepNo + 1],
                                      [bid, bid], color='white')
                self._ax[prod_i].plot([self.__stepNo, self.__stepNo + 1],
                                      [ask, ask], color='white')
                self._ax[prod_i].set_title('Product {} (spread coef {})'.format(
                    prod_i, str(self._spread_coefficients[prod_i])))

        # Spread price
        prices = self._prices_history[-1]
        bid, ask = calc_spread(prices, self._spread_coefficients)
        self._ax[-1].plot([self.__stepNo, self.__stepNo + 1],
                          [bid, bid], color='white')
        self._ax[-1].plot([self.__stepNo, self.__stepNo + 1],
                          [ask, ask], color='white')
        ymin, ymax = self._ax[-1].get_ylim()
        yrange = ymax - ymin
        if (self._action == self.ACTIONS[ACTION_SELL]).all():
            self._ax[-1].scatter(self.__stepNo + 0.5, bid + 0.03 *
                                 yrange, color='orangered', marker='v')
        elif (self._action == self.ACTIONS[ACTION_BUY]).all():
            self._ax[-1].scatter(self.__stepNo + 0.5, ask - 0.03 *
                                 yrange, color='lawngreen', marker='^')
        plt.suptitle('Cumulated Reward: ' + "%.2f" % self._total_reward + ' ~ ' +
                     'Cumulated PnL: ' + "%.2f" % self._total_pnl + ' ~ ' +
                     'Position: ' + [OrderData.DIRECTION_NONE, OrderData.DIRECTION_LONG, OrderData.DIRECTION_SHORT][list(self._position).index(1)] + ' ~ ' +
                     'Entry Price: ' + "%.2f" % self._entry_price)
        self._f.tight_layout()
        plt.xticks(range(self.__stepNo)[::5])
        plt.xlim([max(0, self.__stepNo - 80.5), self.__stepNo + 0.5])
        plt.subplots_adjust(top=0.85)
        plt.pause(0.01)
        if savefig:
            plt.savefig(filename)

    def __build_gym_observation(self):
        """Concatenate all necessary elements to create the observation.

        Returns:
            numpy.array: observation array.
        """
        account_state = self._account.__build_gym_observation()
        market_state = self._envMarket.__build_gym_observation()
        return np.concatenate((account_state, market_state))
        # return np.concatenate(
        #     [prices for prices in self._prices_history[-self._history_length:]] +
        #     [
        #         np.array([self._entry_price]),
        #         np.array(self._position)
        #     ]
        # )

    @staticmethod
    def random_action_fun():
        """The default random action for exploration.
        We hold 80% of the time and buy or sell 10% of the time each.

        Returns:
            numpy.array: array with a 1 on the action index, 0 elsewhere.
        """
        return np.random.multinomial(1, [0.8, 0.1, 0.1])

    #----------------------------------------------------------------------
    # access to the account observed
    def getAccountState(self) :
        ''' get the account capitial including cash and positions
        '''
        positions = self._account.getAllPositions()
        cashAvail, cashTotal = self._account.cashAmount()
        return cashAvail, cashTotal, positions

    def summrizeAccount(self, positions=None, cashTotal=0) :
        ''' sum up the account capitial including cash and positions
        '''
        if positions is None:
            _, cashTotal, positions = self.getAccountState()

        posValueSubtotal =0
        for pos in positions:
            posValueSubtotal += pos.position * pos.price * self._account.contractSize

        return positions + posValueSubtotal

########################################################################
class MetaAgent(ABC): # TODO:
    def __init__(self, gymTrader, **kwargs):

        super(MetaAgent, self).__init__()

        self.__kwargs = kwargs
        self.__jsettings = None
        if 'jsettings' in self.__kwargs.keys():
            self.__jsettings = self.__kwargs.pop('jsettings', None)

        self._gymTrader = gymTrader
        self._stateSize = self._gymTrader.stateSize
        self._actionSize = len(type(gymTrader).ACTIONS)

        self._memorySize = getConfig('memorySize', 2000)
        self._memory = [None] * memory_size
        self._idxMem = 0

        self._trainInterval = getConfig('trainInterval', 10)
        self._learningRate = getConfig('learningRate', 0.001)
        self._batchSize = getConfig('batchSize', 64)

        self._gamma = getConfig('gamma', 0.95)
        self._epsilon = getConfig('epsilon', 1.0)
        self._epsilonMin = getConfig('epsilonMin', 0.01)
        self._epsilonDecrement = (self._epsilon - self._epsilonMin) * self._trainInterval / (episodes * episode_length)  # linear decrease rate

        self._brain = None # self._brain = self.buildBrain()

    def getConfig(self, configName, defaultVal) :
        try :
            if configName in self._kwargs.keys() :
                return self._kwargs[configName]

            if self.__jsettings:
                jn = self.__jsettings
                for i in configName.split('/') :
                    jn = jn[i]

                if defaultVal :
                    if isinstance(defaultVal, list):
                        return jsoncfg.expect_array(jn(defaultVal))
                    if isinstance(defaultVal, dict):
                        return jsoncfg.expect_object(jn(defaultVal))

                return jn(defaultVal)
        except:
            pass

        return defaultVal

    @abstractmethod
    def buildBrain(self):
        '''
        @return the brain built to set to self._brain
        '''
        raise NotImplementedError

    @abstractmethod
    def gymAct(self, state):
        '''
        @return one of self.__gymTrader.ACTIONS
        '''
        raise NotImplementedError

    @abstractmethod
    def gymObserve(self, state, action, reward, next_state, done, warming_up=False):
        '''Memory Management and training of the agent
        @return tuple:
            state_batch, action_batch, reward_batch, next_state_batch, done_batch
        '''
        raise NotImplementedError

########################################################################
class GymTrainer(MetaTrader):
    '''
    GymTrader extends GymTrader by reading history and perform training
    '''
    def __init__(self, program, trader, histdata, **kwargs):
        '''Constructor
        '''
        super(GymTrainer, self).__init__(program, **kwargs)

        self._initTrader = trader
        self._initMarketState = None # to populate from _initTrader
        self._originAcc = None # to populate from _initTrader then wrapper

        self._account = None # the working account inherit from MetaTrader
        self._marketState = None
        self.__wkTrader = None
        self.__wkHistData = histdata

        self._iterationsPerEpisode = self.getConfig('iterationsPerEpisode', 1)

    #----------------------------------------------------------------------
    # impl/overwrite of BaseApplication
    def doAppInit(self): # return True if succ
        if not super(GymTrainer, self).doAppInit() :
            return False

        # step 1. wrapper the Trader
        if not self._initTrader or not isinstance(self._initTrader, GymTrader) :
            return False
        
        self.info('doAppInit() taking trader-template[%s]' % (self._initTrader.ident))
        self._program.removeApp(self._initTrader.ident)
        self._program.addApp(self)
        if not self._initTrader.doAppInit() :
            self.info('doAppInit() failed to initialize trader-template[%s]' % (self._initTrader.ident))
            return False

        self._initMarketState = self._initTrader._marketstate
        
        # step 1. wrapper the broker drivers of the accounts
        self._originAcc = self._initTrader.account
        originAcc = self._initTrader.account
        if self._originAcc and not isinstance(self._originAcc, AccountWrapper):
            self._program.removeApp(self._originAcc.ident)

        self.gymReset()
        return True

    def doAppStep(self):
        super(BackTestApp, self).doAppStep()

        if self.__wkHistData :
            try :
                ev = next(self.__wkHistData)
                if not ev : return
                self._marketState.updateByEvent(ev)
                s = ev.data.symbol
                self.debug('hist-read: symbol[%s]%s asof[%s] lastPrice[%s] OHLC%s' % (s, ev.type[len(MARKETDATE_EVENT_PREFIX):], self._marketState.getAsOf(s).strftime('%Y%m%dT%H%M'), self._marketState.latestPrice(s), self._marketState.dailyOHLC_sofar(s)))
                self.OnEvent(ev) # call Trader
                self.__testRoundcEvs += 1
                return # successfully pushed an Event
            except StopIteration:
                pass

        # this test should be done if reached here
        self.debug('hist-read: end of playback')
        self._account.OnPlaybackEnd()
        self.info('test-round[%d/%d] done, processed %d events took %s, generating report' % (self.__testRoundId, self._testRounds, self.__testRoundcEvs, str(datetime.now() - self.__execStamp_roundStart)))
        try :
            self.generateReport()
        except Exception as ex:
            self.error("generateReport() caught exception %s %s" % (ex, traceback.format_exc()))

        self.__testRoundcEvs =0
        self.__testRoundId +=1
        if (self.__testRoundId > self._testRounds) :
            # all tests have been done
            self.stop()
            self.info('all %d test-round have been done, took %s, app stopped. obj-in-program: %s' % (self._testRounds, str(datetime.now() - self.__execStamp_appStart), self._program.listByType(MetaObj)))
            return

        self.resetTest()

    def OnEvent(self, ev): 
        symbol  = None
        try :
            symbol = ev.data.symbol
        except:
            pass

        if EVENT_TICK == ev.type or EVENT_KLINE_PREFIX == ev.type[:len(EVENT_KLINE_PREFIX)] :
            self._account.matchTrades(ev)

        self.__wkTrader.OnEvent(ev) # to perform the gym step

        if not self._dataBegin_date:
            self._dataBegin_date = self.__wkTrader.marketState.stateAsOf(symbol)
        
    # end of BaseApplication routine
    #----------------------------------------------------------------------
    
    #----------------------------------------------------------------------
    # Overrides of Events handling
    def eventHdl_Order(self, ev):
        return self.__wkTrader.eventHdl_Order(ev)
            
    def eventHdl_Trade(self, ev):
        return self.__wkTrader.eventHdl_Trade(ev)

    def onDayOpen(self, symbol, date):
        return self.__wkTrader.onDayOpen(symbol, date)

    def proc_MarketEvent(self, ev):
        self.error('proc_MarketEvent() should not be here')

    #------------------------------------------------
    # GymEnv related methods
    def gymReset(self) :
        '''
        reset the gym environment, will be called when each episode starts
        reset the trading environment / rewards / data generator...
        @return:
            observation (numpy.array): observation of the state
        '''
        self.__execStamp_episodeStart = datetime.now()
        
        self.info('gymReset() episode[%d/%d], elapsed %s' % (self.__testRoundId, self._testRounds, str(self.__execStamp_episodeStart - self.__execStamp_appStart)))

        # step 1. start over the market state
        if not self._marketState:
            self._marketState
            self._program.removeObj(self._marketState)
        
        if self._initMarketState:
            self._marketState = copy.deepcopy(self._initMarketState)
            self._program.addObj(self._marketState)

        # step 2. create clean trader and account from self._initAcc and  
        if self.__wkTrader:
            self._program.removeObj(self.__wkTrader)
        self.__wkTrader = copy.deepcopy(self._initTrader)
        self._program.addApp(self.__wkTrader)
        self.__wkTrader._marketstate = self._marketState

        if self._account :
            self._program.removeApp(self._account)
            self._account =None
        
        # step 3. wrapper the broker drivers of the accounts
        if self._originAcc and not isinstance(self._originAcc, AccountWrapper):
            self._program.removeApp(self._originAcc.ident)
            self._account = AccountWrapper(self, account=copy.copy(self._originAcc)) # duplicate the original account for test espoches
            self._account._trader = self # adopt the account by pointing its._trader to self
            self._account.setCapital(self._startBalance, True)
            self._program.addApp(self._account)
            self._account._marketstate = self._marketState
            self.__wkTrader._account = self._account
            self.info('doAppInit() wrappered account[%s] to [%s] with startBalance[%d]' % (self._originAcc.ident, self._account.ident, self._startBalance))

        self.__wkHistData.resetRead()
           
        self._dataBegin_date = None
        self._dataBegin_closeprice = 0.0
        
        self._dataEnd_date = None
        self._dataEnd_closeprice = 0.0

        if self._marketState :
            for i in range(30) : # initially feed 20 data from histread to the marketstate
                ev = next(self.__wkHistData)
                if not ev : continue
                self._marketState.updateByEvent(ev)

            if len(self.__wkTrader._dictObjectives) <=0:
                sl = self._marketState.listOberserves()
                for symbol in sl:
                    self.__wkTrader.openObjective(symbol)

        # step 4. subscribe account events
        self.subscribeEvent(Account.EVENT_ORDER)
        self.subscribeEvent(Account.EVENT_TRADE)

        return __wkTrader.gymReset()


if __name__ == '__main__':
    from Application import Program
    from Account import Account_AShare
    import HistoryData as hist
    import sys, os

    sys.argv += ['-f', os.path.dirname(os.path.dirname(os.path.abspath(__file__))) + '/../conf/Gym_AShare.json']
    p = Program()
    p._heartbeatInterval =-1
    SYMBOL = '000001' # '000540' '000001'

    acc = p.createApp(Account_AShare, configNode ='account', ratePer10K =30)
    csvdir = '/mnt/e/AShareSample' # '/mnt/m/AShareSample'
    csvreader = hist.CsvPlayback(program=p, symbol=SYMBOL, folder='%s/%s' % (csvdir, SYMBOL), fields='date,time,open,high,low,close,volume,ammount')
    # marketstate = PerspectiveDict('AShare')
    # p.addObj(marketstate)

    gymtdr = p.createApp(GymTrader, configNode ='trainer', account=acc)
    
    p.info('all objects registered piror to GymTrainer: %s' % p.listByType())
    
    p.createApp(GymTrainer, configNode ='trainer', trader=gymtdr, histdata=csvreader)

    p.start()
    p.loop()
    p.stop()
