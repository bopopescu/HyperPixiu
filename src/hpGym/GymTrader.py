# encoding: UTF-8
'''
GymTrader impls BaseTrader and represent itself as a Gym Environment
'''
from __future__ import division

# from gym import GymEnv
from Account import Account, OrderData, Account_AShare
from Application import MetaObj
from Trader import MetaTrader, BaseTrader
from BackTest import BackTestApp
from Perspective import PerspectiveState
from MarketData import EVENT_TICK, EVENT_KLINE_PREFIX

import hpGym

from abc import abstractmethod
import matplotlib as mpl # pip install matplotlib
import matplotlib.pyplot as plt
import numpy as np
import datetime

plt.style.use('dark_background')
mpl.rcParams.update(
    {
        "font.size": 15,
        "axes.labelsize": 15,
        "lines.linewidth": 1,
        "lines.markersize": 8
    }
)

DUMMY_BIG_VAL = 999999.9

########################################################################
class MetaAgent(MetaObj): # TODO:
    def __init__(self, gymTrader, **kwargs):

        super(MetaAgent, self).__init__()

        self.__kwargs = kwargs
        self.__jsettings = None
        if 'jsettings' in self.__kwargs.keys():
            self.__jsettings = self.__kwargs.pop('jsettings', None)

        self._gymTrader = gymTrader
        self._stateSize = len(self._gymTrader.gymReset())
        self._actionSize = len(type(gymTrader).ACTIONS)

        self._learningRate = self.getConfig('learningRate', 0.001)
        self._batchSize = self.getConfig('batchSize', 128)

        self._gamma = self.getConfig('gamma', 0.95)
        self._epsilon = self.getConfig('epsilon', 1) # rand()[0,1) <= self._epsilon will trigger a random explore
        self._epsilonMin = self.getConfig('epsilonMin', 0.01)

        self._wkBrainId = self.getConfig('brainId', None)

        self._trainInterval = self._batchSize /2
        if self._trainInterval < 10:
            self._trainInterval =10

        self._brain = self.buildBrain(self._wkBrainId)

    @abstractmethod
    def isReady(self) : return True

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
    def buildBrain(self, brainId =None):
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

    @abstractmethod
    def saveBrain(self, brainId =None) :
        ''' save the current brain into the dataRoot
        @param a unique brainId must be given
        '''
        raise NotImplementedError
        
    @abstractmethod
    def loadBrain(self, brainId) :
        ''' load the previous saved brain
        @param a unique brainId must be given
        '''
        raise NotImplementedError

########################################################################
class GymTrader(BaseTrader):
    '''
    GymTrader impls BaseTrader and represent itself as a Gym Environment
    '''
    ACTION_BUY  = OrderData.ORDER_BUY
    ACTION_SELL = OrderData.ORDER_SELL
    ACTION_HOLD = 'HOLD'

    ACTIONS = {
        ACTION_HOLD: np.array([1, 0, 0]).astype('float32'),
        ACTION_BUY:  np.array([0, 1, 0]).astype('float32'),
        ACTION_SELL: np.array([0, 0, 1]).astype('float32')
    }

    POS_DIRECTIONS = {
        OrderData.DIRECTION_NONE:  np.array([1, 0, 0]).astype('float32'),
        OrderData.DIRECTION_LONG:  np.array([0, 1, 0]).astype('float32'),
        OrderData.DIRECTION_SHORT: np.array([0, 0, 1]).astype('float32')
    }

    def __init__(self, program, agentClass=None, **kwargs):
        '''Constructor
        '''
        super(GymTrader, self).__init__(program, **kwargs) # redirect to BaseTrader, who will adopt account and so on

        self._agent = None
        self._timeCostYrRate = self.getConfig('timeCostYrRate', 0)
        self._tradeSymbol    = self.getConfig('tradeSymbol', '000001')
        #TODO: the separate the Trader for real account and training account
        
        self.__1stRender = True
        self._AGENTCLASS = None
        agentType = self.getConfig('agent/type', 'DQN')
        if agentType and agentType in hpGym.GYMAGENT_CLASS.keys():
            self._AGENTCLASS = hpGym.GYMAGENT_CLASS[agentType]

        # step 1. GymTrader always take PerspectiveState as the market state
        self._marketState = PerspectiveState(None)
        self._gymState = None
        self.__recentLoss = None
        self._total_pnl = 0.0
        self._total_reward = 0.0
        self._capOfLastStep = 0.0

        # self.n_actions = 3
        # self._prices_history = []
    @property
    def loss(self) :
        return round(self.__recentLoss.history["loss"][0], 6) if self.__recentLoss else DUMMY_BIG_VAL

    #----------------------------------------------------------------------
    # impl/overwrite of BaseApplication
    def doAppInit(self): # return True if succ
        if not super(GymTrader, self).doAppInit() :
            return False

        if not self._AGENTCLASS :
            return False

        # the self._account should be good here

        # step 1. GymTrader always take PerspectiveState as the market state
        self._marketState._exchange = self._account.exchange
        self._account._marketState = self._marketState

        agentKwArgs = self.getConfig('agent', {})
        self._agent = self._AGENTCLASS(self, jsettings=self.subConfig('agent'), **agentKwArgs)
        # gymReset() will be called by agent above, self._gymState = self.gymReset() # will perform self._action = ACTIONS[ACTION_HOLD]

        # self.__stampActStart = datetime.datetime.now()
        # self.__stampActEnd = self.__stampActStart

        while not self._agent.isReady() :
            action = self._agent.gymAct(self._gymState)
            next_state, reward, done, _ = self.gymStep(action)
            self._agent.gymObserve(self._gymState, action, reward, next_state, done, warming_up=True) # regardless state-stepping, rewards and loss here

        return True

    def doAppStep(self):
        super(GymTrader, self).doAppStep()
        # perform some dummy steps in order to fill agent._memory[]

    def proc_MarketEvent(self, ev):
        '''processing an incoming MarketEvent'''

        self._action = self._agent.gymAct(self._gymState)
        next_state, reward, self._episodeDone, _ = self.gymStep(self._action)
    
        # self.__stampActStart = datetime.datetime.now()
        # waited = self.__stampActStart - self.__stampActEnd
        loss = self._agent.gymObserve(self._gymState, self._action, reward, next_state, self._episodeDone)
        if loss: self.__recentLoss =loss
        # self.__stampActEnd = datetime.datetime.now()

        self._gymState = next_state
        self._total_reward += reward

        # self.info('proc_MarketEvent(%s) processed took %s, from last-round %s' % (ev.desc, (self.__stampActEnd - self.__stampActStart), waited))
        self.debug('proc_MarketEvent(%s) processed' % (ev.desc))

    # end of impl/overwrite of BaseApplication
    #----------------------------------------------------------------------

    #------------------------------------------------
    # GymEnv related entries
    def gymReset(self) :
        '''
        reset the gym environment, will be called when each episode starts
        reset the trading environment / rewards / data generator...
        @return:
            observation (numpy.array): observation of the state
        '''
        self.__closed_plot = False
        self.__stepNo = 0
        self._total_pnl = 0.0
        self._total_reward = 0.0
        cash, posvalue = self._account.summrizeBalance()
        self._capOfLastStep = cash + posvalue

        observation = self.makeupGymObservation()
        self._shapeOfState = observation.shape
        self._action = GymTrader.ACTIONS[GymTrader.ACTION_HOLD]
        self._gymState = observation
        return observation

    def gymStep(self, action) :
        '''Take an action (buy/sell/hold) and computes the immediate reward.

        @param action (numpy.array): Action to be taken, one-hot encoded.
        @returns:
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
        instant_pnl = 0.0
        reward =0.0
        info = {}

        # step 1. collected information from the account
        cashAvail, cashTotal, positions = self._account.positionState()
        _, posvalue = self._account.summrizeBalance(positions, cashTotal)
        capitalBeforeStep = cashTotal + posvalue

        # TODO: the first version only support one symbol to play, so simply take the first symbol in the positions        
        symbol = self._tradeSymbol # TODO: should take the __dictOberserves
        latestPrice = self._marketState.latestPrice(symbol)

        maxBuy, maxSell = self._account.maxOrderVolume(symbol, latestPrice)
        # TODO: the first version only support FULL-BUY and FULL-SELL
        if all(action == GymTrader.ACTIONS[GymTrader.ACTION_BUY]) :
            if maxBuy >0 :
                self._account.cancelAllOrders()
                vtOrderIDList = self._account.sendOrder(symbol, OrderData.ORDER_BUY, latestPrice, maxBuy, strategy=None)
            else: reward -=  100 # penalty: is the agent blind to buy with no cash? :)
        elif all(action == GymTrader.ACTIONS[GymTrader.ACTION_SELL]):
            if  maxSell >0:
                self._account.cancelAllOrders()
                vtOrderIDList = self._account.sendOrder(symbol, OrderData.ORDER_SELL, latestPrice, maxSell, strategy=None)
            else: reward -=  100 # penalty: is the agent blind to sell with no position? :)

        # step 3. calculate the rewards
        cash, posvalue = self._account.summrizeBalance() # most likely the cashAmount changed due to comission
        capitalAfterStep = cash + posvalue
        if capitalAfterStep < 50000 : 
            done =True

        instant_pnl = capitalAfterStep - capitalBeforeStep
        reward      = capitalAfterStep - self._capOfLastStep
        self._total_pnl += instant_pnl
        self._capOfLastStep = capitalAfterStep

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

        # try:
        #     self._prices_history.append(self._data_generator.next())
        # except StopIteration:
        #     done = True
        #     info['status'] = 'No more data.'
        # if self.__stepNo >= self._iterationsPerEpisode:
        #     done = True
        #     info['status'] = 'Time out.'
        # if self.__closed_plot:
        #     info['status'] = 'Closed plot'

        '''

        ''' step 5. combine account and market observations as final observations,
            then return
        observation = np.concatenate((self._account_state, self._market_state))
        '''
        observation = self.makeupGymObservation()
        return observation, reward, done, info
    
    def gymRender(self, savefig=False, filename='myfig'):
        """Matlplotlib gymRendering of each step.

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
            self._f.canvas.mpl_connect('close_event', self.__OnRenderClosed)

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

    # end of GymEnv entries
    #------------------------------------------------

    def makeupGymObservation(self):
        '''Concatenate all necessary elements to create the observation.

        Returns:
            numpy.array: observation array.
        '''
        # part 1. build up the account_state
        cashAvail, cashTotal, positions = self._account.positionState()
        _, posvalue = self._account.summrizeBalance(positions, cashTotal)
        capitalBeforeStep = cashTotal + posvalue
        stateCapital = [cashAvail, cashTotal, capitalBeforeStep]
        # POS_COLS = PositionData.COLUMNS.split(',')
        # del(POS_COLS['exchange', 'stampByTrader', 'stampByBroker'])
        # del(POS_COLS['symbol']) # TODO: this version only support single Symbol, so regardless field symbol
        POS_COLS = 'position,posAvail,price,avgPrice'
        statePOS = [0.0,0.0,0.0,0.0] # supposed to be [[0.0,0.0,0.0,0.0],...] when mutliple-symbols
        for s, pos in positions.items() :
            # row = []
            # for c in POS_COLS:
            #     row.append(pos.__dict__[c])
            # statePOS.append(row)
            statePOS = [pos.position, pos.posAvail, pos.price, pos.avgPrice]
            break

        account_state = np.concatenate([stateCapital + statePOS], axis=0)

        # part 2. build up the market_state
        market_state = self._marketState.snapshot('000001')

        # return the concatenation of account_state and market_state as gymEnv sate
        ret = np.concatenate((account_state, market_state))
        return ret.astype('float32')

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

    def __OnRenderClosed(self, evt):
        self.__closed_plot = True

########################################################################
class GymTrainer(BackTestApp):
    '''
    GymTrader extends GymTrader by reading history and perform training
    '''
    def __init__(self, program, trader, histdata, **kwargs):
        '''Constructor
        '''
        super(GymTrainer, self).__init__(program, trader, histdata, **kwargs)
        self._iterationsPerEpisode = self.getConfig('iterationsPerEpisode', 1)
        self.__lastEpisode_loss = DUMMY_BIG_VAL

        self.__bestEpisode_Id = -1
        self.__bestEpisode_loss = DUMMY_BIG_VAL
        self.__bestEpisode_reward = -DUMMY_BIG_VAL
        self.__stampLastSaveBrain = '0000'

    #----------------------------------------------------------------------
    # impl/overwrite of BaseApplication
    def doAppInit(self): # return True if succ

        # make sure GymTrainer is ONLY wrappering GymTrader
        if not self._initTrader or not isinstance(self._initTrader, GymTrader) :
            return False

        return super(GymTrainer, self).doAppInit()

    def OnEvent(self, ev): # this overwrite BackTest's because there are some different needs
        symbol  = None
        try :
            symbol = ev.data.symbol
        except:
            pass

        if EVENT_TICK == ev.type or EVENT_KLINE_PREFIX == ev.type[:len(EVENT_KLINE_PREFIX)] :
            self._account.matchTrades(ev)

        self.wkTrader.OnEvent(ev) # to perform the gym step

        self._dataEnd_date = self.wkTrader.marketState.getAsOf(symbol)
        self._dataEnd_closeprice = self.wkTrader.marketState.latestPrice(symbol)

        if not self._dataBegin_date:
            self._dataBegin_date = self._dataEnd_date
            self._dataBegin_openprice = self._dataEnd_closeprice

        
    # end of BaseApplication routine
    #----------------------------------------------------------------------

    #------------------------------------------------
    # BackTest related entries
    def OnEpisodeDone(self):
        super(GymTrainer, self).OnEpisodeDone()

        # save brain and decrease epsilon if improved
        if self.wkTrader.loss < self.__bestEpisode_loss :
            self.__bestEpisode_loss = self.wkTrader.loss
            self.__bestEpisode_Id = self.episodeId
            self.__bestEpisode_reward = self.wkTrader._total_reward
            self.wkTrader._agent.saveBrain()
            self.__stampLastSaveBrain = datetime.datetime.now()

            self.wkTrader._agent._epsilon -= self.wkTrader._agent._epsilon/4
            if self.wkTrader._agent._epsilon < self.wkTrader._agent._epsilonMin :
                self.wkTrader._agent._epsilon = self.wkTrader._agent._epsilonMin

        mySummary = {
            'totalReward' : round(self.wkTrader._total_reward, 2),
            'epsilon'     : round(self.wkTrader._agent._epsilon, 4),
            'loss'        : self.wkTrader.loss,
            'lastLoss'    : self.__lastEpisode_loss,
            'bestLoss'    : self.__bestEpisode_loss,
            'idOfBest'    : self.__bestEpisode_Id,
            'rewardOfBest': self.__bestEpisode_reward,
            'lastSaveBrain': self.__stampLastSaveBrain
        }
        self._episodeSummary = {**self._episodeSummary, **mySummary}

        self.__lastEpisode_loss = self.wkTrader.loss
        # maybe self.wkTrader.gymRender()

    def resetEpisode(self) :
        '''
        reset the gym environment, will be called when each episode starts
        reset the trading environment / rewards / data generator...
        @return:
            observation (numpy.array): observation of the state
        '''
        super(GymTrainer, self).resetEpisode()
        return self.wkTrader.gymReset()

    def formatSummary(self, summary=None):
        strReport = super(GymTrainer, self).formatSummary(summary)
        if not isinstance(summary, dict) :
            summary = self._episodeSummary

        strReport += '\n\n' + '-'*20
        strReport += '\n totalReward: %s'  % summary['totalReward']
        strReport += '\n     epsilon: %s'  % summary['epsilon']
        strReport += '\n        loss: %s <-last %s' % (summary['loss'], summary['lastLoss'])
        strReport += '\n    bestLoss: %s <-(%s: reward=%s)' % (summary['bestLoss'], summary['idOfBest'], summary['rewardOfBest'])
        strReport += '\n   saveBrain: %s %s'  % (summary['bestLoss'], summary['lastSaveBrain'])
        return strReport

if __name__ == '__main__':
    from Application import Program
    from Account import Account_AShare
    import HistoryData as hist
    import sys, os
    # from keras.backend.tensorflow_backend import set_session
    # import tensorflow as tf

    # config = tf.ConfigProto()
    # config.gpu_options.allow_growth=True
    # set_session(tf.Session(config=config))

    sys.argv += ['-f', os.path.dirname(os.path.dirname(os.path.abspath(__file__))) + '/../conf/Gym_AShare.json']
    p = Program()
    p._heartbeatInterval =-1
    SYMBOL = '000001' # '000540' '000001'

    acc = p.createApp(Account_AShare, configNode ='account', ratePer10K =30)
    csvdir = '/mnt/e/AShareSample' # '/mnt/m/AShareSample'
    # csvdir = 'e:/AShareSample'
    csvreader = hist.CsvPlayback(program=p, symbol=SYMBOL, folder='%s/%s' % (csvdir, SYMBOL), fields='date,time,open,high,low,close,volume,ammount')
    # marketstate = PerspectiveState('AShare')
    # p.addObj(marketstate)
    rec = p.createApp(hist.TaggedCsvRecorder, configNode ='recorder')

    gymtdr = p.createApp(GymTrader, configNode ='trainer', account=acc, recorder=rec)
    
    p.info('all objects registered piror to GymTrainer: %s' % p.listByType())
    
    p.createApp(GymTrainer, configNode ='trainer', trader=gymtdr, histdata=csvreader)

    p.start()
    p.loop()
    p.stop()

