from aiogram.fsm.state import State, StatesGroup

class StatsState(StatesGroup):
    waiting_for_dates = State()