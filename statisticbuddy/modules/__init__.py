"""Registered tracker modules, in display order. Add new trackers here."""
from statisticbuddy.modules.exp import ExpModule
from statisticbuddy.modules.loot import LootModule
from statisticbuddy.modules.meso import MesoModule
from statisticbuddy.modules.potions import PotionModule
from statisticbuddy.modules.profit import ProfitModule


def all_modules():
    return [ProfitModule(), PotionModule(), ExpModule(), MesoModule(), LootModule()]
