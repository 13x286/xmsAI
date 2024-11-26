from dataclasses import dataclass
from typing import List, Dict, Optional
from enum import Enum
import random
import math

class Phase(Enum):
    TURN_START = "回合开始阶段"
    PLAYER_ACTION = "玩家操作阶段"
    TURN_END = "回合结束阶段"

class EffectType(Enum):
    DAMAGE = "伤害"
    SPIRIT = "元气"
    FOCUS = "集中"
    DRAW = "抽牌"
    PLAY_COUNT = "出牌机会"
    MOOD = "好调"
    DIRECT_DAMAGE = "直接伤害"

class CardTrait(Enum):
    EXHAUST = "消耗"
    BYPASS_SPIRIT = "无视元气"

@dataclass
class Effect:
    type: EffectType
    value: int
    bypass_spirit: bool = False
 
class CardTemplate:
    name: str
    effects: List[Dict]
    cost: int
    count: int = 1  # 默认数量为1
    traits: List[str] = None
    shuffle_priority: float = 0

def create_card_from_template(template: CardTemplate) -> 'Card':
    """从模板创建卡牌实例"""
    traits = template.traits or []
    return Card(
        name=template.name,
        effects=template.effects,
        cost=template.cost,
        bypass_spirit=CardTrait.BYPASS_SPIRIT.value in traits,
        shuffle_priority=template.shuffle_priority,
        exhaust=CardTrait.EXHAUST.value in traits
    )

class Card:
    def __init__(self, name: str, effects: List[Dict], cost: int, bypass_spirit: bool = False, 
                 shuffle_priority: float = 0, exhaust: bool = False):  # 新增 exhaust 参数
        self.name = name
        self.effects = []
        for effect in effects:
            bypass = effect.get("bypass_spirit", False)
            self.effects.append(Effect(EffectType(effect["type"]), effect["value"], bypass))
        self.cost = cost
        self.bypass_spirit = bypass_spirit
        self.shuffle_priority = shuffle_priority
        self.exhaust = exhaust  # 消耗
        self.shuffle_random = 0  # 洗牌用
    
    def apply_cost(self, game_state: 'GameState') -> List[str]:
        """应用卡牌消耗，优先消耗元气，元气不足时消耗体力"""
        log_entries = []
        remaining_cost = self.cost
        
        # 如果卡牌设置了无视元气，直接消耗体力
        if self.bypass_spirit:
            game_state.vitality -= remaining_cost
            log_entries.append(f"消耗体力 {remaining_cost}")
            return log_entries
            
        # 优先消耗元气
        if game_state.spirit > 0:
            spirit_reduction = min(game_state.spirit, remaining_cost)
            game_state.spirit -= spirit_reduction
            remaining_cost -= spirit_reduction
            log_entries.append(f"消耗元气 {spirit_reduction}")
            
        # 如果还有剩余消耗，扣除体力
        if remaining_cost > 0:
            game_state.vitality -= remaining_cost
            log_entries.append(f"消耗体力 {remaining_cost}")
            
        return log_entries

    def apply_effects(self, game_state: 'GameState') -> List[str]:
        log_entries = []
        
        # 先处理消耗
        cost_logs = self.apply_cost(game_state)
        log_entries.extend(cost_logs)
        
        for effect in self.effects:
            if effect.type == EffectType.DAMAGE:
                focus_bonus = game_state.buffs.get("集中", 0)
                base_damage = effect.value + focus_bonus
                
                # 好调加成计算
                mood_bonus = game_state.buffs.get("好调", 0)
                if mood_bonus > 0:
                    actual_damage = math.floor(base_damage * 1.5)
                    log_entry = f"{effect.type.value}{effect.value}"
                    if focus_bonus:
                        log_entry += f"{focus_bonus:+}"
                    log_entry += f"×1.5(好调)={actual_damage}"
                else:
                    actual_damage = base_damage
                    log_entry = f"{effect.type.value}{effect.value}"
                    if focus_bonus:
                        log_entry += f"{focus_bonus:+}"
                    log_entry += f"={actual_damage}"
                
                game_state.score += actual_damage
                log_entries.append(log_entry)
                
            elif effect.type == EffectType.SPIRIT:
                actual_spirit = effect.value
                game_state.spirit += actual_spirit
                log_entries.append(f"{effect.type.value}{actual_spirit:+}={game_state.spirit}")
                
            elif effect.type == EffectType.FOCUS:
                current_focus = game_state.buffs.get("集中", 0)
                game_state.buffs["集中"] = current_focus + effect.value
                log_entries.append(f"{effect.type.value}{effect.value:+}={game_state.buffs['集中']}")
                
            elif effect.type == EffectType.MOOD:
                current_mood = game_state.buffs.get("好调", 0)
                was_zero = current_mood == 0
                game_state.buffs["好调"] = current_mood + effect.value
                if was_zero and game_state.buffs["好调"] > 0:
                    game_state.new_buffs["好调"] = True
                    log_entries.append(f"{effect.type.value}{effect.value:+}={game_state.buffs['好调']} (新获得)")
                else:
                    log_entries.append(f"{effect.type.value}{effect.value:+}={game_state.buffs['好调']}")
                
            elif effect.type == EffectType.PLAY_COUNT:
                game_state.buffs["出牌机会"] += effect.value
                log_entries.append(f"{effect.type.value}{effect.value:+}")

        return log_entries


class GameState:
    def __init__(self, deck: List[Card], num_rounds: int, target_score: int, 
                 max_hand_size: int = 5, starting_vitality: int = 30):
        self.deck = deck
        self.num_rounds = num_rounds
        self.target_score = target_score
        self.max_hand_size = max_hand_size
        
        # 游戏状态
        self.current_round = 1
        self.score = 0
        self.spirit = 0
        self.vitality = starting_vitality
        self.current_phase = Phase.TURN_START
        
        # 卡牌相关
        self.hand: List[Card] = []
        self.draw_pile: List[Card] = []
        self.discard_pile: List[Card] = []
        self.exhaust_pile: List[Card] = []  # 新增消耗堆
        
        # Buff系统
        self.buffs: Dict[str, int] = {
            "出牌机会": 1,
            "集中": 0,
            "好调": 0
        }
        
        self.new_buffs: Dict[str, bool] = {
            "好调": False
        }
        
        self.log: List[str] = []
        
        self.is_first_shuffle = True

        self._initialize_draw_pile()

    def _initialize_draw_pile(self):
        """初始化抽牌堆"""
        self.draw_pile = self.deck.copy()
        
        # 为每张卡赋予一个随机值
        for card in self.draw_pile:
            card.shuffle_random = random.random()
            
        # 如果是首次洗牌，与原始优先级相加后排序
        if self.is_first_shuffle:
            self.draw_pile.sort(key=lambda x: x.shuffle_random + x.shuffle_priority, reverse=True)
            # 首次洗牌后，重置所有优先级为0
            for card in self.draw_pile:
                card.shuffle_priority = 0
            self.is_first_shuffle = False
        else:
            # 后续洗牌只使用随机值排序
            self.draw_pile.sort(key=lambda x: x.shuffle_random, reverse=True)
            
    def draw_cards(self, count: int) -> None:
        """抽取指定数量的卡牌"""
        for _ in range(count):
            if len(self.draw_pile) == 0:
                if len(self.discard_pile) == 0:
                    break
                self.draw_pile = self.discard_pile.copy()
                self.discard_pile.clear()
                random.shuffle(self.draw_pile)
            
            if len(self.hand) < self.max_hand_size:
                card = self.draw_pile.pop()
                self.hand.append(card)

    def reset_for_new_round(self) -> None:
        """重置回合相关状态"""
        self.discard_pile.extend(self.hand)
        self.hand.clear()
        self.buffs["集中"] = 0
        self.defense = 0

    def handle_phase_start(self) -> List[str]:
        """处理回合开始阶段"""
        log_entries = []
        
        # 处理好调buff
        if self.buffs["好调"] > 0:
            # 检查是否是新获得的buff
            if self.new_buffs["好调"]:
                # 跳过本次衰减，重置新获得状态
                self.new_buffs["好调"] = False
                log_entries.append(f"好调效果为新获得，跳过衰减")
            else:
                # 正常衰减
                self.buffs["好调"] -= 1
                log_entries.append(f"好调效果衰减: {self.buffs['好调']+1} -> {self.buffs['好调']}")
        
        # 重置出牌机会
        self.buffs["出牌机会"] = 1
        
        # 抽牌
        self.draw_cards(3)
        log_entries.append("抽取3张卡牌")
        
        return log_entries

class Game:
    def __init__(self, deck: List[Card], num_rounds: int, target_score: int, 
                 max_hand_size: int = 5, starting_vitality: int = 30):
        self.state = GameState(deck, num_rounds, target_score, 
                             max_hand_size, starting_vitality)
        
    def display_hand(self) -> None:
        """显示当前手牌"""
        print("\n当前手牌:")
        for i, card in enumerate(self.state.hand, 1):
            effects_str = []
            for effect in card.effects:
                if effect.type == EffectType.DAMAGE:
                    # 计算伤害加成
                    focus_bonus = self.state.buffs.get("集中", 0)
                    base_damage = effect.value + focus_bonus
                    mood_bonus = self.state.buffs.get("好调", 0)
                    if mood_bonus > 0:
                        actual_damage = math.floor(base_damage * 1.5)
                        damage_str = f"{effect.type.value}{effect.value}"
                        if focus_bonus:
                            damage_str += f"{focus_bonus:+}"
                        damage_str += f"×1.5={actual_damage}"
                    else:
                        actual_damage = base_damage
                        damage_str = f"{effect.type.value}{effect.value}"
                        if focus_bonus:
                            damage_str += f"{focus_bonus:+}"
                        damage_str += f"={actual_damage}"
                    effects_str.append(damage_str)
                else:
                    effects_str.append(f"{effect.type.value}{effect.value:+}")
            
            # 添加无视元气标记
            cost_str = f"消耗:{card.cost}"
            if card.bypass_spirit:
                cost_str += "(无视元气)"
            
            print(f"{i}. {card.name}({cost_str}) - {', '.join(effects_str)}")

    def display_game_status(self) -> None:
        """显示当前游戏状态"""
        print(f"\n回合: {self.state.current_round}/{self.state.num_rounds}")
        print(f"目标分数: {self.state.target_score}")
        print(f"当前分数: {self.state.score}")
        print(f"体力值: {self.state.vitality}")
        print(f"元气值: {self.state.spirit}")
        print(f"剩余出牌次数: {self.state.buffs['出牌机会']}")
        print(f"消耗堆数量: {len(self.state.exhaust_pile)}")  # 新增显示消耗堆数量
        
        active_buffs = []
        for buff_name, value in self.state.buffs.items():
            if buff_name != "出牌机会" and value > 0:
                active_buffs.append(f"{buff_name}: {value}")
        if active_buffs:
            print("当前效果: " + ", ".join(active_buffs))

        # 显示buff状态
        active_buffs = []
        for buff_name, value in self.state.buffs.items():
            if buff_name != "出牌机会" and value > 0:
                active_buffs.append(f"{buff_name}: {value}")
        if active_buffs:
            print("当前效果: " + ", ".join(active_buffs))

    def get_valid_input(self, prompt: str, min_val: int, max_val: int) -> int:
        """获取有效的用户输入"""
        while True:
            try:
                choice = input(prompt)
                if choice.lower() == 'q':
                    print("\n游戏已退出!")
                    exit(0)
                if choice.lower() == 'p':
                    return 0  # 表示跳过出牌
                
                value = int(choice)
                if min_val <= value <= max_val:
                    return value
                else:
                    print(f"请输入{min_val}到{max_val}之间的数字!")
            except ValueError:
                print("请输入有效的数字!")

    def play_turn(self) -> None:
        """处理玩家回合逻辑"""
        while self.state.buffs["出牌机会"] > 0 and self.state.hand:
            self.display_game_status()
            self.display_hand()
            
            prompt = "\n请选择要使用的卡牌(输入编号)，输入'p'跳过出牌，输入'q'退出游戏: "
            choice = self.get_valid_input(prompt, 1, len(self.state.hand))
            
            if choice == 0:
                print("跳过出牌")
                break
                
            selected_card = self.state.hand[choice - 1]
            print(f"\n使用卡牌: {selected_card.name}")
            
            # 应用卡牌效果
            log_entries = selected_card.apply_effects(self.state)
            self.state.log.extend(log_entries)
            for entry in log_entries:
                print(entry)
            
            # 处理卡牌去向
            self.state.hand.remove(selected_card)
            if selected_card.exhaust:  # 根据消耗属性决定卡牌去向
                self.state.exhaust_pile.append(selected_card)
                print(f"{selected_card.name} 已消耗")
            else:
                self.state.discard_pile.append(selected_card)
            
            self.state.buffs["出牌机会"] -= 1
            
            if not self.state.hand:
                print("\n手牌已用完!")
            elif self.state.buffs["出牌机会"] <= 0:
                print("\n本回合出牌次数已用完!")

    def handle_turn_start(self) -> None:
        """处理回合开始阶段"""
        print(f"\n{Phase.TURN_START.value}")
        log_entries = self.state.handle_phase_start()
        self.state.log.extend(log_entries)
        for entry in log_entries:
            print(entry)

    def handle_turn_end(self) -> None:
        """处理回合结束阶段"""
        print(f"\n{Phase.TURN_END.value}")
        self.state.reset_for_new_round()
        self.state.log.append(f"回合 {self.state.current_round} 结束")

    def start(self) -> None:
        """开始游戏主循环"""
        print("\n游戏开始!")
        print("提示: 卡牌消耗会优先消耗元气值，元气值不足时才会消耗体力值")
        print("      标记为'无视元气'的卡牌将直接消耗体力值")
        
        while (self.state.current_round <= self.state.num_rounds and 
               self.state.score < self.state.target_score and
               self.state.vitality > 0):  # 添加体力值检查
            
            # 回合开始阶段
            self.state.current_phase = Phase.TURN_START
            self.handle_turn_start()
            
            # 玩家操作阶段
            self.state.current_phase = Phase.PLAYER_ACTION
            print(f"\n{Phase.PLAYER_ACTION.value}")
            self.play_turn()
            
            # 回合结束阶段
            self.state.current_phase = Phase.TURN_END
            self.handle_turn_end()
            
            self.state.current_round += 1

        print("\n游戏结束!")
        if self.state.vitality <= 0:
            print("体力耗尽，游戏失败！")
        elif self.state.score >= self.state.target_score:
            print("恭喜！您达到了目标分数。")
        else:
            print("很遗憾，您没有达到目标分数。")
        print(f"最终得分: {self.state.score}")

def create_base_deck() -> List[Card]:
    """创建基础卡组
    示例:
    {
        "name": "卡牌名",
        "effects": [
            {"type": "伤害", "value": 10}, 
            {"type": "元气", "value": 2}
        ],
        "cost": 3,
        "count": 2,  # 可选,默认1
        "traits": ["消耗", "无视元气"],  # 可选
        "shuffle_priority": 0  # 可选,默认0
    }
    """
    CARDS = [
        {
            "name": "进攻",
            "effects": [{"type": "伤害", "value": 9}],
            "cost": 4,
            "count": 2
        },
        {
            "name": "防御",
            "effects": [{"type": "元气", "value": 4}],
            "cost": 0,
            "count": 2
        },
        {
            "name": "集中",
            "effects": [
                {"type": "元气", "value": 2},
                {"type": "集中", "value": 2}
            ],
            "cost": 1,
            "count": 2
        },
        {
            "name": "双击",
            "effects": [
                {"type": "伤害", "value": 9},
                {"type": "伤害", "value": 9}
            ],
            "cost": 7,
            "traits": ["消耗"],
        },
        {
            "name": "沉静意志1",
            "effects": [
                {"type": "集中", "value": 4},
                {"type": "好调", "value": 3}
            ],
            "cost": 2,
            "traits": ["消耗"],
            "shuffle_priority": -1
        },
        {
            "name": "测试",
            "effects": [
                {"type": "伤害", "value": 9},
                {"type": "集中", "value": 2},
                {"type": "伤害", "value": 9}
            ],
            "cost": 4,
            "traits": ["消耗"],
        },
        {
            "name": "舍身一击",
            "effects": [{"type": "伤害", "value": 15}],
            "cost": 6,
            "traits": ["消耗", "无视元气"]
        },
        {
            "name": "爆发",
            "effects": [{"type": "伤害", "value": 20}],
            "cost": 8,
            "traits": ["消耗", "无视元气"]
        }
    ]

    deck = []
    for card_data in CARDS:
        # 获取卡牌属性
        name = card_data["name"]
        effects = card_data["effects"]
        cost = card_data["cost"]
        count = card_data.get("count", 1)  # 默认数量1
        traits = card_data.get("traits", [])  # 默认无特殊特质
        shuffle_priority = card_data.get("shuffle_priority", 0)  # 默认优先级0
        
        # 创建卡牌
        card = Card(
            name=name,
            effects=effects,
            cost=cost,
            bypass_spirit="无视元气" in traits,
            shuffle_priority=shuffle_priority,
            exhaust="消耗" in traits
        )
        
        # 根据count添加卡牌
        for _ in range(count):
            deck.append(card)
            
    return deck
# 示例运行
if __name__ == "__main__":
    base_deck = create_base_deck()
    game = Game(base_deck, num_rounds=9, target_score=90)
    game.start()

from card_recommendation import CardRecommendationAgent

base_deck = create_base_deck()
recommendation_agent = CardRecommendationAgent(base_deck)
recommendation_agent.train(num_episodes=1000)