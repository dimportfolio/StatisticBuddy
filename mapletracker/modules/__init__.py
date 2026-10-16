"""Registered tracker modules, in display order. Add new trackers here."""
from mapletracker.modules.exp import ExpModule
from mapletracker.modules.loot import LootModule
from mapletracker.modules.meso import MesoModule
from mapletracker.modules.potions import PotionModule
from mapletracker.modules.profit import ProfitModule


def all_modules():
    return [ProfitModule(), PotionModule(), ExpModule(), MesoModule(), LootModule()]
