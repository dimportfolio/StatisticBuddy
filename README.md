<img src="packaging/avatar.png" alt="StatisticBuddy logo" width="120" align="right">

# StatisticBuddy

A free Windows desktop app that tracks your MapleStory (including Classic World) grinding while you play: EXP per hour and time to level, mesos, ETC loot value, potion use and repot time, and whether a map is meso-positive, with session history.

[![Buy Me a Coffee](https://img.shields.io/badge/Buy%20me%20a%20coffee-support-FFDD00?logo=buymeacoffee&logoColor=black)](https://buymeacoffee.com/gamedo)

> **Disclaimer:** StatisticBuddy is an unofficial fan tool. It is not affiliated with, endorsed by or supported by Nexon. MapleStory is a trademark of Nexon. The app only reads pixels on your screen (see [How it stays within Nexon's Terms of Service](#how-it-stays-within-nexons-terms-of-service)), but screen reading isn't expressly authorized by Nexon. **Use it at your own risk.**

## Download

1. Go to the [**Releases**](https://github.com/dimportfolio/StatisticBuddy/releases/latest) page and download `StatisticBuddy-<version>-windows.zip`.
2. Unzip it anywhere (e.g. your Documents folder) and run **`StatisticBuddy.exe`** inside the folder. Nothing to install.
3. Windows may show "Windows protected your PC" because the app isn't code-signed. Click **More info → Run anyway**.

### Running from source (developers)

1. Install **Python 3.12** from python.org and tick "Add python.exe to PATH".
2. Double-click `run.bat`. The first run sets up the environment, which takes a few minutes.

To build the `.exe` yourself, run `build_exe.ps1` (see the comments at its top).

## Using it

1. Run the game in **windowed or borderless** mode. The app finds the MapleStory window automatically.
2. Open the **Regions** tab. For each tracker, click **Select…** and drag a tight box on the game screenshot:
   - **EXP bar**: the EXP numbers, e.g. `12345678 [45.678%]`.
   - **Meso count (inventory)**: open your inventory first, then box the meso number.
3. Click **Test read all** and check each "Read as" line.
4. Click **Start session**. The **Live** tab shows EXP and meso stats. Use **Pause** for breaks and **Stop & save** when done; past sessions are on the **History** tab.

Regions are stored relative to the game window, so moving the window is fine. If you change the game's resolution, or move your inventory, select the affected region again (the Regions tab warns you when the window size changes).

Mesos: increases count as gained; spending (shops, repairs) is tracked separately and never reduces "gained". If the inventory is closed, meso reads are simply skipped.

## Loot and profit

- **ETC inventory grid** (Regions tab): open the ETC tab and box exactly the item slots (all rows and columns). Set the grid size (default 5 columns × 6 rows) on the Loot panel.
- Each item is recognised by its icon, so it's followed even when it moves slots. New items appear in the Loot table as "Item #n"; click the name and NPC price to fill them in.
- A stack count only changes after two reads in a row agree. Reads where the inventory is closed or on another tab are skipped.
- **Profit** = net mesos (picked up − spent) + change in loot value (count change × NPC price). Selling loot to an NPC isn't double-counted: mesos go up and loot value goes down by the same amount.
- The Profit panel shows ✅ meso-positive / ❌ losing mesos with profit per hour; History has Profit and Profit / hour per session. Run a few 30+ minute sessions per map before trusting the result.

## Potions and repot time

- On the Regions tab, select up to 4 **Potion quickslot** keys: box one whole key (icon and number) each.
- On the Live tab's Potions panel, set each one's name, type (HP / MP / Other) and **price per potion** (what you pay at the shop).
- Shows potions used, their cost, use per hour, and **Repot: HP in ~X · MP in ~Y**, based on your use over the last 10 minutes (it turns orange under 15 minutes and red under 5).
- Profit counts potions **used**, not bought: restocking mid-session spends mesos but adds the same value in potions.

## Where data is stored

Everything stays on your PC, in `%LOCALAPPDATA%\StatisticBuddy` (before the rename it was `MapleTracker`; your data is copied over automatically and the old folder is kept as a backup):

- `tracker.db`: sessions, every reading taken (EXP, mesos, potion counts), your loot item list (name, NPC price and a small icon image per item) and per-session results.
- `settings.json`: the regions you selected, read interval, grid size, potion names and prices.
- `app.log`: errors, if any, to help diagnose problems.

Screenshots are **not** saved. Each read takes one screenshot of the game in memory, reads the selected regions from it and discards it. The only images kept are the small item icons shown in the Loot table.

One misread number can't skew your stats: unusual readings (level-ups, big jumps, spending) only count once the next reading confirms them. Each tracker also has a **Manual** entry box as a backup.

## How it stays within Nexon's Terms of Service

The app is a separate program that only looks at screen pixels. It never:

- reads or writes game memory, opens the game process, or injects anything
- sends keyboard/mouse input or window messages to the game, or automates gameplay
- intercepts network traffic or modifies game files

To find the game, it asks Windows (read-only) for the position of the window named MapleStory, the same query OBS "Window Capture" and Discord use. The pixels themselves are copied from the desktop, like a screenshot, not through the game window.

`tests/test_safety.py` enforces this: it fails if any code uses process or memory access, input simulation, window messages or hooks, the network, or subprocesses, and it limits the window finder to an allow-list of read-only Windows calls. OCR runs fully offline with telemetry disabled.

MapleStory Classic World uses the same Terms and account as MapleStory, so a ban in either applies to both. Screen reading isn't *expressly authorized* by Nexon, so use OCR at your own discretion. Manual entry alone carries no risk.

## Adding new trackers

Each feature is a module in `statisticbuddy/modules/` (see `exp/` and `meso/`). A module is a `TrackerModule` subclass (`core/module.py`) that:

- declares the screen `regions` it reads (they appear on the Regions tab automatically)
- turns OCR text into numbers in `on_read()`
- creates its own tables in `init_schema()` and returns a Live panel from `create_panel()`
- adds History columns via `history_headers` / `history_values()`

Register it in `all_modules()` in `statisticbuddy/modules/__init__.py`. Sessions, the game screenshot, OCR and storage are shared.

## Tests

```
%LOCALAPPDATA%\StatisticBuddy\venv\Scripts\python -m unittest discover -s tests -t .
```

Some tests check the readers against real game screenshots in `tests/fixtures/`. Those images contain Nexon's game art, so they aren't published; the tests that need them are skipped when they're missing.

## Support

StatisticBuddy is free and always will be. If it helps your grinding and you'd like to say thanks, you can [**buy me a coffee**](https://buymeacoffee.com/gamedo). It's completely optional and doesn't unlock anything; every feature is free for everyone.

## License

MIT. See [LICENSE](LICENSE).
