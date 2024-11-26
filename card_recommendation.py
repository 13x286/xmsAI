import random
from typing import List, Dict, Any
from gamemain import create_base_deck, Game, GameState, Card, Phase

class CardRecommendationAgent:
    def __init__(self, deck: List[Card], learning_rate=0.1, discount_factor=0.9, exploration_rate=0.1):
        """
        初始化卡牌推荐强化学习智能体
        
        :param deck: 游戏卡组
        :param learning_rate: 学习率
        :param discount_factor: 折扣因子
        :param exploration_rate: 探索率
        """
        self.deck = deck
        self.q_table = {}  # Q-table存储状态-动作对的期望价值
        self.learning_rate = learning_rate
        self.discount_factor = discount_factor
        self.exploration_rate = exploration_rate

    def get_state_key(self, game_state: GameState) -> str:
        """
        将游戏状态转换为可哈希的状态键
        
        :param game_state: 游戏状态
        :return: 状态的字符串表示
        """
        return f"round:{game_state.current_round}_score:{game_state.score}_spirit:{game_state.spirit}_vitality:{game_state.vitality}_focus:{game_state.buffs.get('集中', 0)}_mood:{game_state.buffs.get('好调', 0)}"

    def choose_card(self, game_state: GameState) -> Card:
        """
        根据Q-learning选择最佳卡牌
        
        :param game_state: 当前游戏状态
        :return: 选择的卡牌
        """
        # 如果没有手牌，返回None
        if not game_state.hand:
            return None

        state_key = self.get_state_key(game_state)

        # 探索与利用平衡
        if random.random() < self.exploration_rate:
            return random.choice(game_state.hand)

        # 如果该状态没有记录，初始化
        if state_key not in self.q_table:
            self.q_table[state_key] = {card.name: 0 for card in game_state.hand}

        # 选择Q值最高的卡牌
        q_values = self.q_table[state_key]
        best_card = max(game_state.hand, key=lambda card: q_values.get(card.name, 0))
        return best_card

    def update_q_table(self, prev_state: str, card: Card, reward: float, curr_state: str):
        """
        更新Q-table
        
        :param prev_state: 前一个状态
        :param card: 选择的卡牌
        :param reward: 即时奖励
        :param curr_state: 当前状态
        """
        # 如果状态不存在，初始化
        if prev_state not in self.q_table:
            self.q_table[prev_state] = {card.name: 0 for card in self.deck}
        if curr_state not in self.q_table:
            self.q_table[curr_state] = {card.name: 0 for card in self.deck}

        # Q-learning更新公式
        current_q = self.q_table[prev_state].get(card.name, 0)
        max_next_q = max(self.q_table[curr_state].values())
        
        new_q = current_q + self.learning_rate * (
            reward + self.discount_factor * max_next_q - current_q
        )
        
        self.q_table[prev_state][card.name] = new_q

    def train(self, num_episodes=1000, num_rounds=9, target_score=90):
        """
        训练智能体，完全模拟游戏主流程
        
        :param num_episodes: 训练回合数
        :param num_rounds: 每局游戏的最大回合数
        :param target_score: 目标分数
        """
        training_results = {
            'total_episodes': num_episodes,
            'successful_episodes': 0,
            'average_final_score': 0,
            'total_final_score': 0
        }

        for episode in range(num_episodes):
            # 创建游戏实例，完全遵循游戏初始化逻辑
            game_state = GameState(
                deck=self.deck, 
                num_rounds=num_rounds, 
                target_score=target_score, 
                max_hand_size=5, 
                starting_vitality=30
            )

            # 记录每回合的状态和动作
            episode_states = []
            episode_actions = []
            episode_rewards = []

            # 完全模拟游戏流程
            while (game_state.current_round <= game_state.num_rounds and 
                   game_state.score < game_state.target_score and
                   game_state.vitality > 0):
                
                # 回合开始阶段 - 完全遵循游戏逻辑
                game_state.current_phase = Phase.TURN_START
                game_state.handle_phase_start()

                # 玩家操作阶段
                game_state.current_phase = Phase.PLAYER_ACTION
                
                # 记录回合初始状态
                prev_state_key = self.get_state_key(game_state)

                # 出牌阶段
                while game_state.buffs["出牌机会"] > 0 and game_state.hand:
                    # 使用智能体选择卡牌
                    selected_card = self.choose_card(game_state)
                    
                    if not selected_card:
                        break

                    # 记录选择的卡牌
                    episode_actions.append(selected_card.name)

                    # 应用卡牌效果
                    log_entries = selected_card.apply_effects(game_state)

                    # 记录当前状态
                    curr_state_key = self.get_state_key(game_state)

                    # 计算奖励 - 这里可以更复杂地设计奖励
                    reward = game_state.score  # 简单地使用分数作为奖励
                    episode_rewards.append(reward)

                    # 更新Q表
                    self.update_q_table(prev_state_key, selected_card, reward, curr_state_key)

                    # 移除已使用的卡牌
                    game_state.hand.remove(selected_card)
                    game_state.discard_pile.append(selected_card)
                    
                    # 减少出牌机会
                    game_state.buffs["出牌机会"] -= 1

                    # 更新前一个状态
                    prev_state_key = curr_state_key

                # 回合结束阶段
                game_state.current_phase = Phase.TURN_END
                game_state.reset_for_new_round()
                game_state.current_round += 1

            # 记录训练结果
            training_results['total_final_score'] += game_state.score
            if game_state.score >= target_score:
                training_results['successful_episodes'] += 1

            # 每100轮打印一次进度
            if (episode + 1) % 100 == 0:
                print(f"Episode {episode + 1}/{num_episodes} completed. Final score: {game_state.score}")

        # 计算平均分数
        training_results['average_final_score'] = training_results['total_final_score'] / num_episodes

        # 打印训练总结
        print("\n训练总结:")
        print(f"总训练局数: {training_results['total_episodes']}")
        print(f"成功局数: {training_results['successful_episodes']}")
        print(f"平均最终得分: {training_results['average_final_score']:.2f}")

        return training_results

def main():
    base_deck = create_base_deck()
    agent = CardRecommendationAgent(base_deck)
    agent.train(num_episodes=5000)

if __name__ == "__main__":
    main()