#!/usr/bin/env python

'''
Based on:
=======
https://github.com/vmayoral/basic_reinforcement_learning
https://gist.github.com/wingedsheep/4199594b02138dd427c22a540d6d6b8d
'''
import gym
from gym import wrappers
import gym_gazebo
import time
from distutils.dir_util import copy_tree
import os
import json
import random
import numpy as np
from keras.models import Sequential, load_model
from keras.initializers import normal
from keras import optimizers
from keras.optimizers import RMSprop
from keras.layers import Convolution2D, Flatten, ZeroPadding2D
from keras.layers.core import Dense, Dropout, Activation
from keras.layers.normalization import BatchNormalization
from keras.layers.advanced_activations import LeakyReLU
from keras.layers.pooling import MaxPooling2D
from keras.regularizers import l2
from keras.optimizers import SGD , Adam
import memory

import keras
from keras import backend, layers, models, utils
from keras.models import Model
backend.set_image_data_format('channels_last')

from keras_applications.vgg16 import VGG16
import re

class DeepQ:
    """
    DQN abstraction.

    As a quick reminder:
        traditional Q-learning:
            Q(s, a) += alpha * (reward(s,a) + gamma * max(Q(s') - Q(s,a))
        DQN:
            target = reward(s,a) + gamma * max(Q(s')

    """
    def __init__(self, outputs, memorySize, discountFactor, learningRate, learnStart, img_rows, img_cols, img_channels):
        """
        Parameters:
            - outputs: output size
            - memorySize: size of the memory that will store each state
            - discountFactor: the discount factor (gamma)
            - learningRate: learning rate
            - learnStart: steps to happen before for learning. Set to 128
        """
        self.output_size = outputs
        self.memory = memory.Memory(memorySize)
        self.discountFactor = discountFactor
        self.learnStart = learnStart
        self.learningRate = learningRate
        self.img_rows = img_rows
        self.img_cols = img_cols
        self.img_channels = img_channels

    def initNetworks(self):
        model = self.createModel()
        self.model = model

    def createModel(self):
        # Network structure must be directly changed here.
        base_model = VGG16(backend=backend, layers=layers, models=models, utils=utils, weights='imagenet', include_top=False, input_shape=(self.img_rows, self.img_cols, self.img_channels))

        for layer in base_model.layers:
            layer.trainable = False

        x = base_model.output

        # flat: passing it to a dense layer
        x = Flatten()(x)
        # 1st Dense Layer
        x = Dense(4096, activation='relu', name='fc1')(x)
        # 2st Dense Layer
        x = Dense(4096, activation='relu', name='fc2')(x)

        # Output Layer
        x = Dense(network_outputs)(x)

        model = Model(base_model.input, x)

        #adam = Adam(lr=self.learningRate)
        #model.compile(loss='mse',optimizer=adam)
        model.compile(RMSprop(lr=self.learningRate), 'MSE')
        model.summary()

        return model

    def printNetwork(self):
        i = 0
        for layer in self.model.layers:
            weights = layer.get_weights()
            print("layer ",i,": ",weights)
            i += 1

    def backupNetwork(self, model, backup):
        weightMatrix = []
        for layer in model.layers:
            weights = layer.get_weights()
            weightMatrix.append(weights)
        i = 0
        for layer in backup.layers:
            weights = weightMatrix[i]
            layer.set_weights(weights)
            i += 1

    def updateTargetNetwork(self):
        self.backupNetwork(self.model, self.targetModel)

    # predict Q values for all the actions
    def getQValues(self, state):
        predicted = self.model.predict(state)
        return predicted[0]

    def getTargetQValues(self, state):
        predicted = self.targetModel.predict(state)
        return predicted[0]

    def getMaxQ(self, qValues):
        return np.max(qValues)

    def getMaxIndex(self, qValues):
        return np.argmax(qValues)

    # calculate the target function
    def calculateTarget(self, qValuesNewState, reward, isFinal):
        """
        target = reward(s,a) + gamma * max(Q(s')
        """
        if isFinal:
            return reward
        else :
            return reward + self.discountFactor * self.getMaxQ(qValuesNewState)

    # select the action with the highest Q value
    def selectAction(self, qValues, explorationRate):
        rand = random.random()
        if rand < explorationRate :
            action = np.random.randint(0, self.output_size)
        else :
            action = self.getMaxIndex(qValues)
        return action

    def selectActionByProbability(self, qValues, bias):
        qValueSum = 0
        shiftBy = 0
        for value in qValues:
            if value + shiftBy < 0:
                shiftBy = - (value + shiftBy)
        shiftBy += 1e-06

        for value in qValues:
            qValueSum += (value + shiftBy) ** bias

        probabilitySum = 0
        qValueProbabilities = []
        for value in qValues:
            probability = ((value + shiftBy) ** bias) / float(qValueSum)
            qValueProbabilities.append(probability + probabilitySum)
            probabilitySum += probability
        qValueProbabilities[len(qValueProbabilities) - 1] = 1

        rand = random.random()
        i = 0
        for value in qValueProbabilities:
            if (rand <= value):
                return i
            i += 1

    def addMemory(self, state, action, reward, newState, isFinal):
        self.memory.addMemory(state, action, reward, newState, isFinal)

    def learnOnLastState(self):
        if self.memory.getCurrentSize() >= 1:
            return self.memory.getMemory(self.memory.getCurrentSize() - 1)

    def learnOnMiniBatch(self, miniBatchSize, useTargetNetwork=True):
        # Do not learn until we've got self.learnStart samples
        if self.memory.getCurrentSize() > self.learnStart:
            # learn in batches of 128
            miniBatch = self.memory.getMiniBatch(miniBatchSize)
            X_batch = np.empty((1,img_channels,img_rows,img_cols), dtype = np.float64)
            Y_batch = np.empty((1,self.output_size), dtype = np.float64)
            for sample in miniBatch:
                isFinal = sample['isFinal']
                state = sample['state']
                action = sample['action']
                reward = sample['reward']
                newState = sample['newState']

                qValues = self.getQValues(state)
                if useTargetNetwork:
                    qValuesNewState = self.getTargetQValues(newState)
                else :
                    qValuesNewState = self.getQValues(newState)
                targetValue = self.calculateTarget(qValuesNewState, reward, isFinal)
                X_batch = np.append(X_batch, state.copy(), axis=0)
                Y_sample = qValues.copy()
                Y_sample[action] = targetValue
                Y_batch = np.append(Y_batch, np.array([Y_sample]), axis=0)
                if isFinal:
                    X_batch = np.append(X_batch, newState.copy(), axis=0)
                    Y_batch = np.append(Y_batch, np.array([[reward]*self.output_size]), axis=0)
            self.model.fit(X_batch, Y_batch, validation_split=0.2, batch_size = len(miniBatch), nb_epoch=1, verbose = 0)

    def saveModel(self, path):
        self.model.save(path)

    def loadWeights(self, path):
        self.model.set_weights(load_model(path).get_weights())

def detect_monitor_files(training_dir):
    return [os.path.join(training_dir, f) for f in os.listdir(training_dir) if f.startswith('openaigym')]

def clear_monitor_files(training_dir):
    files = detect_monitor_files(training_dir)
    if len(files) == 0:
        return
    for file in files:
        os.unlink(file)

if __name__ == '__main__':

    #REMEMBER!: turtlebot_cnn_setup.bash must be executed.
    env = gym.make('GazeboCircuit2cTurtlebotCameraCnnEnv-v0')

    # Parameters:
    outdir = '/tmp/gazebo_gym_experiments/'
    SAVE_PREFIX_PATH = '/home/tal/deep/data/gym-gazebo'
    SAVE_PREFIX_NAME = 'turtle_dqn_vgg16_100_100_3ch'
    epochs = 100000
    steps = 1000

    if not os.path.isdir(SAVE_PREFIX_PATH):
        os.makedirs()
    if not os.path.isdir(outdir):
        os.makedirs()

    epochs_list = []
    _, _, files = next(os.walk(SAVE_PREFIX_PATH))
    for file in files:
        if file.startswith(SAVE_PREFIX_NAME + '_ep'):
            str_file = file.split(SAVE_PREFIX_NAME + '_ep')[1]
            epochs_list.append(int(re.search(r'\d+', str_file).group()))

    epochs_list.sort(reverse=True)
    continue_execution = False
    current_epoch = 0
    file_prefix = SAVE_PREFIX_PATH + '/' + SAVE_PREFIX_NAME + '_ep'

    for current_epoch in epochs_list:
        file_prefix = SAVE_PREFIX_PATH + '/' + SAVE_PREFIX_NAME + '_ep'
        file_prefix_ep = file_prefix + str(current_epoch)
        if (os.path.isfile(file_prefix_ep + '.json')
            and
            os.path.isfile(file_prefix_ep + '.h5')):
            continue_execution = True
            weights_path = file_prefix_ep + '.h5'
            params_json  = file_prefix_ep + '.json'
            monitor_path = file_prefix_ep
            break

    img_rows, img_cols, img_channels = env.img_rows, env.img_cols, env.img_channels

    if not continue_execution:
        minibatch_size = 32
        learningRate = 1e-3   # 1e6
        discountFactor = 0.95
        network_outputs = 3
        memorySize = 100000
        learnStart = 10000    # time steps to observe before training
        EXPLORE = memorySize  # frames over which to anneal epsilon
        INITIAL_EPSILON = 1   # starting value of epsilon
        FINAL_EPSILON = 0.01  # final value of epsilon
        explorationRate = INITIAL_EPSILON
        current_epoch = 0
        stepCounter = 0
        loadsim_seconds = 0

        deepQ = DeepQ(network_outputs, memorySize, discountFactor, learningRate, learnStart, img_rows, img_cols, img_channels)
        deepQ.initNetworks()
        env = gym.wrappers.Monitor(env, outdir, force=True)
    else:
        # Load weights, monitor info and parameter info.
        with open(params_json) as outfile:
            d = json.load(outfile)
            explorationRate = d.get('explorationRate')
            minibatch_size = d.get('minibatch_size')
            learnStart = d.get('learnStart')
            learningRate = d.get('learningRate')
            discountFactor = d.get('discountFactor')
            memorySize = d.get('memorySize')
            network_outputs = d.get('network_outputs')
            current_epoch = d.get('current_epoch')
            stepCounter = d.get('stepCounter')
            EXPLORE = d.get('EXPLORE')
            INITIAL_EPSILON = d.get('INITIAL_EPSILON')
            FINAL_EPSILON = d.get('FINAL_EPSILON')
            loadsim_seconds = d.get('loadsim_seconds')

        deepQ = DeepQ(network_outputs, memorySize, discountFactor, learningRate, learnStart, img_rows, img_cols, img_channels)
        deepQ.initNetworks()
        deepQ.loadWeights(weights_path)

        clear_monitor_files(outdir)
        copy_tree(monitor_path,outdir)
        env = gym.wrappers.Monitor(env, outdir, resume=True)

    last100Rewards = [0] * 100
    last100RewardsIndex = 0
    last100Filled = False

    start_time = time.time()
    print("start epoch: " + str(current_epoch))
    # start iterating from 'current epoch'.
    for epoch in range(current_epoch+1, epochs+1, 1):
        observation = env.reset()
        cumulated_reward = 0

        # number of timesteps
        for t in range(steps):
            qValues = deepQ.getQValues(observation)

            action = deepQ.selectAction(qValues, explorationRate)
            newObservation, reward, done, info = env.step(action)

            deepQ.addMemory(observation, action, reward, newObservation, done)
            observation = newObservation

            # We reduced the epsilon gradually
            if explorationRate > FINAL_EPSILON and stepCounter > learnStart:
                explorationRate -= (INITIAL_EPSILON - FINAL_EPSILON) / EXPLORE

            if stepCounter == learnStart:
                print("Starting learning")

            if stepCounter >= learnStart:
                deepQ.learnOnMiniBatch(minibatch_size, False)

            if (t == steps-1):
                print ("reached the end")
                done = True

            env._flush(force=True)
            cumulated_reward += reward

            if done:
                last100Rewards[last100RewardsIndex] = cumulated_reward
                last100RewardsIndex += 1
                if last100RewardsIndex >= 100:
                    last100Filled = True
                    last100RewardsIndex = 0
                m, s = divmod(int(time.time() - start_time + loadsim_seconds), 60)
                h, m = divmod(m, 60)
                if not last100Filled:
                    print ("EP "+str(epoch)+" - {} steps".format(t+1)+" - CReward: "+str(round(cumulated_reward, 2))+"  Eps="+str(round(explorationRate, 2))+"  Time: %d:%02d:%02d" % (h, m, s))
                else :
                    print ("EP "+str(epoch)+" - {} steps".format(t+1)+" - last100 C_Rewards : "+str(int((sum(last100Rewards)/len(last100Rewards))))+" - CReward: "+str(round(cumulated_reward, 2))+"  Eps="+str(round(explorationRate, 2))+"  Time: %d:%02d:%02d" % (h, m, s))
                break
        # SAVE SIMULATION DATA
        if (epoch) % 100 == 0 or epoch == 1:
            print('save epoch: %d' % epoch)
            # save model weights and monitoring data every 100 epochs.
            deepQ.saveModel(file_prefix + str(epoch) + '.h5')
            env._flush()
            copy_tree(outdir, file_prefix + str(epoch))
            # save simulation parameters.
            parameter_keys = ['explorationRate', 'minibatch_size', 'learnStart', 'learningRate', 'discountFactor',
                              'memorySize', 'network_outputs', 'current_epoch', 'stepCounter', 'EXPLORE',
                              'INITIAL_EPSILON', 'FINAL_EPSILON', 'loadsim_seconds']
            parameter_values = [explorationRate, minibatch_size, learnStart, learningRate, discountFactor,
                                memorySize, network_outputs, epoch, stepCounter, EXPLORE, INITIAL_EPSILON,
                                FINAL_EPSILON, s]
            parameter_dictionary = dict(zip(parameter_keys, parameter_values))
            with open(file_prefix + str(epoch) + '.json', 'w') as outfile:
                json.dump(parameter_dictionary, outfile)

            stepCounter += 1
            if stepCounter % 2500 == 0:
                print("Frames = "+str(stepCounter))

    env.close()
