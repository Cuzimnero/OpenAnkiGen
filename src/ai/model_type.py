from enum import Enum, auto


class ModelType(Enum):
    DEEPSEEK = auto()
    OPENAI = auto()
    ANTHROPIC = auto()
    LOCALE = auto()


class CallType(Enum):
    CARD_GENERATION = auto()
    FILTER_AND_SPLIT = auto()
    CARD_IMPROVEMENT = auto()
