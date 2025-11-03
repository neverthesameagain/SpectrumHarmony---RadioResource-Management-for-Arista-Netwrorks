import numpy as np
import math


class MAB:
    def __init__(self, num):
        self.num = num
        self.totalCount = 0
        self.rewards = [0 for _ in range(num)]
        self.count = [0 for _ in range(num)]
        print("Initiating MAB...")

    def initializeArms(self, reward: list):
        self.totalCount += self.num
        for arm in range(self.num):
            self.updateArm(arm, reward[arm])

    def updateArm(self, arm, reward):
        self.count[arm] += 1
        self.rewards[arm] += (self.rewards[arm] - reward)/self.count[arm]

    def selectArm(self):
        self.totalCount += 1
        ucb_values = np.zeros(self.num)
        for i in range(self.num):
            bonus = math.sqrt((2 * math.log(self.totalCount)) / self.count[i])
            ucb_values[i] = self.rewards[i] + bonus

        best_index = int(np.argmax(ucb_values))
        return best_index
