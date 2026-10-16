"""Loot tracking: reads the ETC inventory grid, follows each item's count and
values the change at the NPC price you enter."""
from __future__ import annotations

import time

import cv2

from statisticbuddy.core import fmt
from statisticbuddy.core.module import AppContext, RegionRead, RegionSpec, TrackerModule
from statisticbuddy.modules.loot import store
from statisticbuddy.modules.loot.digits import DigitReader
from statisticbuddy.modules.loot.grid import Catalog, Slot, read_grid
from statisticbuddy.modules.loot.tracker import LootTracker


class LootModule(TrackerModule):
    key = "loot"
    title = "Loot"
    regions = (RegionSpec(
        "etc_grid", "ETC inventory grid",
        "Open your inventory on the ETC tab, then drag a box exactly around all the item slots "
        "(every row and column, no borders or tabs).",
        ocr="none",  # stack counts are read with the game's pixel font (digits.py), not OCR
    ),)
    history_headers = ("Loot value",)

    def __init__(self):
        self.ctx: AppContext | None = None
        self._digits: DigitReader | None = None
        self.catalog = Catalog()
        self.items: dict[int, dict] = {}   # id -> {"name", "price", "png"}
        self.tracker = LootTracker()
        self.session_id: int | None = None
        self.last_read = "Not read yet: start a session with the ETC tab open."
        self.panel = None

    # ----- setup ---------------------------------------------------------------------------
    def init_schema(self, db) -> None:
        store.init_schema(db)

    def create_panel(self, ctx: AppContext):
        from statisticbuddy.modules.loot.widget import LootPanel
        self.ctx = ctx
        for row, icon in store.load_items(ctx.db):
            self.catalog.add(row["id"], icon)
            self.items[row["id"]] = {"name": row["name"], "price": row["npc_price"], "png": row["icon_png"],
                                     "have": row["last_count"]}
        self.panel = LootPanel(self)
        return self.panel

    @property
    def cfg(self) -> dict:
        return self.ctx.settings.section("loot")

    @property
    def grid_size(self) -> tuple[int, int]:
        return int(self.cfg.get("cols", 5)), int(self.cfg.get("rows", 6))

    def set_grid_size(self, cols: int, rows: int) -> None:
        self.cfg["cols"], self.cfg["rows"] = cols, rows
        self.ctx.settings.save()

    @property
    def empty_threshold(self) -> float:
        return float(self.cfg.get("empty_threshold", 12.0))

    @property
    def digits(self) -> DigitReader:
        if self._digits is None:
            self._digits = DigitReader(self.cfg.get("glyphs"))
        return self._digits

    def prices(self) -> dict[int, float]:
        return {i: d["price"] for i, d in self.items.items()}

    # ----- items ---------------------------------------------------------------------------
    def _new_item(self, slot: Slot) -> int:
        ok, png = cv2.imencode(".png", slot.image)
        item_id = store.add_item(self.ctx.db, slot.icon, png.tobytes() if ok else None)
        self.catalog.add(item_id, slot.icon)
        self.items[item_id] = {"name": f"Item #{item_id}", "price": 0.0, "png": png.tobytes() if ok else None,
                               "have": None}
        return item_id

    def rename(self, item_id: int, name: str) -> None:
        self.items[item_id]["name"] = name
        store.update_item(self.ctx.db, item_id, name=name)

    def set_price(self, item_id: int, price: float) -> None:
        self.items[item_id]["price"] = price
        store.update_item(self.ctx.db, item_id, npc_price=price)
        self._save()

    def forget(self, item_id: int) -> None:
        self.catalog.remove(item_id)
        self.items.pop(item_id, None)
        store.delete_item(self.ctx.db, item_id)

    # ----- lifecycle -------------------------------------------------------------------------
    def on_start(self, session_id: int, ts: float) -> None:
        self.session_id = session_id
        self.tracker.reset()
        self.tracker.start(ts)

    def on_pause(self, ts: float) -> None:
        self.tracker.pause(ts)
        self._save()

    def on_resume(self, ts: float) -> None:
        self.tracker.start(ts)

    def on_stop(self, ts: float) -> None:
        self.tracker.pause(ts)
        self._save()
        self.session_id = None
        self.tracker.reset()
        self._changed()

    def _save(self) -> None:
        if self.session_id is None or (self.tracker.reference is None and not self.tracker.accumulated):
            return
        store.save_session(self.ctx.db, self.session_id, self.tracker.changes(), self.prices(),
                           starts=self.tracker.start_counts, ends=self.tracker.current)

    def on_continue(self, session_id: int, active_seconds: float) -> None:
        rows = store.session_items(self.ctx.db, session_id)
        self.session_id = session_id
        self.tracker.restore({r["item_id"]: r["change"] for r in rows},
                             {r["item_id"]: r["start_count"] for r in rows if r["start_count"] is not None},
                             active_seconds)
        self._changed()

    def _changed(self) -> None:
        if self.panel is not None:
            self.panel.update_items()

    # ----- reading ---------------------------------------------------------------------------
    def _slots(self, read: RegionRead) -> list[Slot]:
        cols, rows = self.grid_size
        return [s for s in read_grid(read.image, cols, rows, self.digits, self.empty_threshold) if not s.empty]

    def _quantity(self, slot: Slot) -> int | None:
        """Stack size; if the font has a digit we haven't seen, read it once with OCR and learn it."""
        q = slot.quantity
        if q is not None or self.ctx is None or self.ctx.ocr is None:
            return q
        read = slot.count
        if read.strip is None or not read.glyphs or read.damaged:
            return None   # partly hidden by the pickup highlight: never learn from it
        big = cv2.resize(read.strip, None, fx=4, fy=4, interpolation=cv2.INTER_NEAREST)
        big = cv2.copyMakeBorder(big, 12, 12, 12, 12, cv2.BORDER_CONSTANT, value=255)
        text = "".join(ch for ch in self.ctx.ocr.read_line(big) if ch.isdigit())
        learned = self.digits.learn(read, text)
        if not learned:
            return None
        glyphs = self.cfg.setdefault("glyphs", {})
        for d, bitmap in learned.items():
            glyphs.setdefault(d, []).append(bitmap)
        self.ctx.settings.save()
        return int(text)

    def on_region_changed(self, region_key: str) -> None:
        self.tracker.rebase(set(self.tracker.current))

    def on_read(self, reads: dict[str, RegionRead], ts: float) -> str | None:
        slots = self._slots(reads["etc_grid"])
        matched = [(s, self.catalog.match(s.icon)) for s in slots]
        unknown = [s for s, item in matched if item is None]
        had_items = any(self.tracker.current.values())
        # Inventory closed or another tab open: the box shows mostly unfamiliar "items" (game
        # world, other icons). An all-empty grid is fine: you may have sold everything.
        if had_items and len(unknown) > len(slots) / 2:
            self.last_read = "Last read: ETC tab not visible, skipped"
            self._changed()
            return "ETC tab not visible, skipped"

        counts: dict[int, int] = {}
        unreadable: set[int] = set()
        for s, item in matched:
            if item is None:
                item = self.catalog.match(s.icon) or self._new_item(s)  # a 2nd stack of a new item
            q = self._quantity(s)
            if q is None:
                unreadable.add(item)
            else:
                counts[item] = counts.get(item, 0) + q
        for item in unreadable:
            counts.pop(item, None)
        msg = self.tracker.feed(counts, unreadable)
        self._remember_counts()
        self.last_read = (f"Last read: {len(slots)} stacks, {len(set(counts) | unreadable)} items"
                          + (f", {len(unreadable)} count(s) unreadable" if unreadable else ""))
        self._save()
        self._changed()
        if unknown:
            msg += f", {len(unknown)} new item(s): set their name and NPC price on the Live tab"
        if unreadable:
            msg += f", couldn't read {len(unreadable)} stack count(s)"
        return msg

    def describe(self, region_key: str, read: RegionRead) -> str:
        slots = self._slots(read)
        if not slots:
            return "no items found. Is the ETC tab open and the box exactly around the slots?"
        parts = []
        for s in slots:
            item = self.catalog.match(s.icon)
            q = s.quantity
            parts.append(f"{self.items[item]['name'] if item else 'new item'} ×{q if q is not None else '?'}")
        cols, rows = self.grid_size
        return f"{len(slots)} of {cols * rows} slots used: " + ", ".join(parts)

    def on_snapshot(self, reads: dict[str, RegionRead]) -> None:
        """Outside a session: update how many of each known item you hold."""
        counts: dict[int, int] = {}
        unreadable: set[int] = set()
        for s in self._slots(reads["etc_grid"]):
            item = self.catalog.match(s.icon)
            if item is None:
                continue
            q = s.quantity
            if q is None:
                unreadable.add(item)
            else:
                counts[item] = counts.get(item, 0) + q
        changed = {i: c for i, c in counts.items() if i not in unreadable and self.items[i].get("have") != c}
        for i, c in changed.items():
            self.items[i]["have"] = c
        if changed:
            store.save_counts(self.ctx.db, changed)
        self._changed()

    def _remember_counts(self) -> None:
        """Keep the confirmed count of every item, so totals survive between sessions."""
        changed = {}
        for item, count in self.tracker.current.items():
            if item in self.items and self.items[item].get("have") != count:
                self.items[item]["have"] = count
                changed[item] = count
        if changed:
            store.save_counts(self.ctx.db, changed)

    # ----- display / accounting -------------------------------------------------------------
    def rows(self) -> list[tuple[int, dict, int | None, int | None, float, int, float]]:
        """(item_id, info, count at session start, have, held value, change this session,
        session value), most valuable holdings first."""
        changes = self.tracker.changes()
        starts = self.tracker.start_counts
        out = []
        for i, d in self.items.items():
            have, price, change = d.get("have"), d["price"], changes.get(i, 0)
            out.append((i, d, starts.get(i), have, (have or 0) * price, change, change * price))
        return sorted(out, key=lambda r: (-r[4], -(r[5] != 0), r[0]))

    def total_value(self) -> float:
        """Value of this session's change in loot."""
        return self.tracker.value(self.prices())

    def held_value(self) -> float:
        """Value of all ETC items you hold (last known counts)."""
        return sum((d.get("have") or 0) * d["price"] for d in self.items.values())

    def holdings(self) -> list[tuple[str, float]]:
        return [("ETC items", self.held_value())] if any(d.get("have") for d in self.items.values()) else []

    def unpriced_changes(self) -> list[int]:
        """Items whose count changed this session but have no NPC price (so they count as 0)."""
        return [i for i, c in self.tracker.changes().items()
                if c and i in self.items and not self.items[i]["price"]]

    def profit_parts(self, ts: float) -> list[tuple[str, float]]:
        if self.tracker.reference is None and not self.tracker.accumulated:
            return []
        unpriced = len(self.unpriced_changes())
        label = "Loot value" + (f" ({unpriced} item(s) with no price count as 0)" if unpriced else "")
        return [(label, self.total_value())]

    def profit_history(self, db, session_id: int) -> float | None:
        return store.session_value(db, session_id)

    def history_values(self, db, session_id: int) -> list[str]:
        v = store.session_value(db, session_id)
        return [fmt.signed(v) if v is not None else "-"]
