"""Application controller: window, event loop and state machine."""

from __future__ import annotations

import sys
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, List, Optional, Tuple

import pygame as pg

from ..ai.engine import Engine
from ..ai.levels import MAX_DIFFICULTY, get_level
from ..ai.search import SearchLimits, SearchResult
from ..ai.worker import SearchWorker
from ..branding import APP_NAME, VERSION
from ..core.constants import (
    MODE_AVA,
    MODE_HVAI,
    MODES,
    PLAYER_BLACK,
    SUPPORTED_BOARD_SIZES,
)
from ..core.notation import identify_opening
from ..util.errors import IagoError, SaveFileError
from ..util.log import get_logger
from ..ui.layout import compute_layout
from ..ui.overlays import GameOverData, OptionsData, ResumeData
from ..ui.renderer import RenderModel, Renderer
from ..ui.theme import get_theme, next_theme
from . import paths, persistence
from .achievements import GameSummary, evaluate as evaluate_achievements
from .analysis import GameReview, ReviewWorker
from .audio import SoundBank
from .keymap import AI_VS_AI, PLAYING, REPLAY, lookup
from .session import Session
from .settings import GameSettings

logger = get_logger("app.game")

AUTOSAVE_EVERY = 10
AVA_DELAYS = (0.05, 0.18, 0.45, 0.9)


@dataclass
class LaunchOptions:
    """Command-line overrides applied on top of the saved settings."""

    theme: Optional[str] = None
    mode: Optional[str] = None
    level: Optional[int] = None
    size: Optional[int] = None
    fullscreen: bool = False
    windowed: bool = False
    ui_scale: Optional[float] = None
    sound: Optional[bool] = None
    reset_settings: bool = False


class Game:
    """Owns the window, the session, the engines and the render loop."""

    def __init__(self, options: Optional[LaunchOptions] = None) -> None:
        self.options = options or LaunchOptions()
        self.settings = self._load_settings()

        try:
            sys.setswitchinterval(0.002)
        except (AttributeError, ValueError):  # pragma: no cover - platform specific
            pass

        pg.mixer.pre_init(44100, -16, 2, 512)
        pg.init()
        pg.font.init()

        self.theme = get_theme(self.settings.theme)
        window_size = (self.settings.window_width, self.settings.window_height)
        self.renderer = Renderer(
            window_size, self.settings.board_size, self.theme, self.settings.ui_scale
        )
        if self.settings.fullscreen:
            self._set_fullscreen(True)
        pg.display.set_caption(f"{APP_NAME} {VERSION}")

        self.sound = SoundBank(self.settings.sound_enabled, self.settings.sound_volume)
        self.stats = persistence.load_stats()
        self.engine = Engine(
            self.settings.ai_level, self.settings.board_size, seed=None
        )
        self.engine2 = Engine(self.settings.ai_level, self.settings.board_size, seed=7)
        self.worker = SearchWorker()
        self.hint_worker = SearchWorker()
        self.review_worker = ReviewWorker()

        self.session = Session(
            size=self.settings.board_size,
            mode=self.settings.mode,
            player_color=self.settings.player_color,
            level=self.settings.ai_level,
        )
        self._apply_clock_settings()
        self.session.clock.start(self.session.current_player, time.monotonic())

        self.overlay: Optional[str] = None
        self.overlay_data: Any = None
        self.options_tab = "Game"
        self.dragging: Optional[str] = None
        self.message = ""
        self.message_color = None
        self.thinking: Optional[SearchResult] = None
        self.ai_started_at = 0.0
        self.selected_ply: Optional[int] = None
        self.review: Optional[GameReview] = None
        self.new_achievements: List[str] = []
        self.replay_active = False
        self.paused = False
        self.ava_speed = 2
        self.sidebar_scroll = 0
        self.debug = False
        self.hint_text = ""
        self.pending_hint: Optional[Tuple[int, int]] = None
        self.game_over_reason = "board"
        self.running = True
        self.fps = 0.0
        self._last_autosave = 0
        self._last_ava_move = 0.0
        self._mouse: Optional[Tuple[int, int]] = None
        self._pressed_button: Optional[str] = None
        self._clock = pg.time.Clock()
        self._resume_path: Optional[Path] = None

        self._maybe_offer_resume()
        self._maybe_start_ai()

    # ------------------------------------------------------------------
    # Startup helpers
    # ------------------------------------------------------------------

    def _load_settings(self) -> GameSettings:
        if self.options.reset_settings:
            settings = GameSettings()
        else:
            settings = persistence.load_settings()
        if self.options.theme:
            settings.theme = self.options.theme
        if self.options.mode:
            settings.mode = self.options.mode
        if self.options.level:
            settings.ai_level = self.options.level
        if self.options.size:
            settings.board_size = self.options.size
        if self.options.ui_scale:
            settings.ui_scale = self.options.ui_scale
        if self.options.sound is not None:
            settings.sound_enabled = self.options.sound
        if self.options.fullscreen:
            settings.fullscreen = True
        if self.options.windowed:
            settings.fullscreen = False
        return settings.validated()

    def _maybe_offer_resume(self) -> None:
        autosave = persistence.find_autosave()
        if autosave is None:
            return
        try:
            saved = persistence.load_game(autosave)
        except SaveFileError as exc:
            logger.info("Ignoring unusable autosave: %s", exc)
            persistence.delete_autosave()
            return
        if saved.move_count == 0:
            return
        self._resume_path = autosave
        self.overlay = "resume"
        self.overlay_data = ResumeData(
            move_count=saved.move_count,
            mode=MODE_LABELS_FALLBACK.get(saved.mode, saved.mode),
            level=get_level(saved.level).name,
            played_at=saved.saved_at.replace("T", " ")[:16],
        )

    def _apply_clock_settings(self) -> None:
        settings = self.settings
        self.session.clock.mode = settings.clock_mode
        self.session.clock.base = settings.blitz_minutes * 60.0
        self.session.clock.increment = float(settings.blitz_increment)

    # ------------------------------------------------------------------
    # Main loop
    # ------------------------------------------------------------------

    def run(self) -> None:
        while self.running:
            dt = min(0.05, self._clock.tick(60) / 1000.0)
            self.fps = self._clock.get_fps()
            self.handle_events()
            self.update(dt)
            self.draw()
        self.shutdown()

    def handle_events(self) -> None:
        for event in pg.event.get():
            if event.type == pg.QUIT:
                self.quit()
            elif event.type == pg.VIDEORESIZE:
                width = max(760, event.w)
                height = max(660, event.h)
                self.renderer.resize((width, height))
                self.settings.window_width = self.renderer.layout.width
                self.settings.window_height = self.renderer.layout.height
            elif event.type == pg.MOUSEBUTTONDOWN and event.button == 1:
                self._mouse = event.pos
                self.on_click(event.pos)
            elif event.type == pg.MOUSEBUTTONUP and event.button == 1:
                self.dragging = None
                self._pressed_button = None
            elif event.type == pg.MOUSEMOTION:
                self._mouse = event.pos
                if self.dragging:
                    self._handle_drag(event.pos)
            elif event.type == pg.MOUSEWHEEL:
                if self.overlay is None:
                    self.sidebar_scroll = max(0, self.sidebar_scroll - event.y * 36)
            elif event.type == pg.KEYDOWN:
                self.on_key(event.key, event.mod, event.unicode)
            elif event.type == pg.WINDOWFOCUSLOST:
                self.worker.cancel()

    def update(self, dt: float) -> None:
        self.renderer.update(dt)
        self._poll_search()
        self._poll_hint()
        self._poll_review()
        self._tick_clock()
        self._tick_replay(dt)
        self._maybe_start_ai()
        if self.session.records:
            self.session.opening_name = self._opening_name()

    def draw(self) -> None:
        model = self._build_model()
        self.renderer.draw(model)

    # ------------------------------------------------------------------
    # Model assembly
    # ------------------------------------------------------------------

    def _build_model(self) -> RenderModel:
        display_board = None
        if self.selected_ply is not None:
            display_board = self.session.position_at(self.selected_ply)
        session = self.session
        thinking_text = ""
        if self.thinking is not None:
            thinking_text = "Thinking…"
        hint_text = ""
        if self.pending_hint is not None:
            hint_text = f"Hint: {self._notation(self.pending_hint)}"
        return RenderModel(
            session=session,
            theme=self.theme,
            hint_move=self.pending_hint if self.settings.show_hints else None,
            show_hints=self.settings.show_hints,
            hover_cell=self._hover_cell(),
            thinking=self.thinking,
            thinking_text=thinking_text,
            message=self.message,
            message_color=self.message_color,
            overlay=self.overlay,
            overlay_data=self.overlay_data,
            selected_ply=self.selected_ply,
            display_board=display_board,
            review=self.review,
            sidebar_scroll=self.sidebar_scroll,
            sidebar_footer=self._sidebar_footer(),
            hint_text=hint_text,
            mouse=self._mouse,
            pressed_button=self._pressed_button,
            show_coordinates=self.settings.show_coordinates,
            show_eval_bar=self.settings.show_eval_bar,
            animations_enabled=self.settings.animations,
            particles_enabled=self.settings.particles,
            debug=self.debug,
            fps=self.fps,
            badge=self.stats_badge(),
            game_over_reason=self.game_over_reason,
            review_progress=self.review_worker.progress,
            new_achievements=tuple(self.new_achievements),
            paused=self.paused,
            stats=self.stats,
        )

    def _hover_cell(self) -> Optional[Tuple[int, int]]:
        if self._mouse is None:
            return None
        if self.overlay is not None or self.selected_ply is not None:
            return None
        return self.renderer.layout.hit_cell(self._mouse)

    def _sidebar_footer(self) -> str:
        if self.review is not None:
            return self.review.summary()
        return "Click a move to review it"

    def stats_badge(self) -> str:
        if self.session.mode == MODE_HVAI and self.stats.games_played:
            return f"{self.stats.games_won}W · {self.stats.games_lost}L"
        return ""

    # ------------------------------------------------------------------
    # Input
    # ------------------------------------------------------------------

    def on_click(self, position: Tuple[int, int]) -> None:
        target = self.renderer.hit_test(position)
        if target is not None:
            self._pressed_button = (
                target.value if isinstance(target.value, str) else None
            )
            self._dispatch_target(target.action, target.value)
            return

        if self.overlay is not None:
            return

        cell = self.renderer.layout.hit_cell(position)
        if cell is None:
            return
        self.on_board_click(cell[0], cell[1])

    def _dispatch_target(self, action: str, value: Any) -> None:
        if action == "close_overlay":
            self._close_overlay()
        elif action == "button":
            self._on_button(str(value))
        elif action == "options_tab":
            self.options_tab = str(value)
            self._refresh_options()
        elif action == "set_mode":
            self._set_mode(str(value))
        elif action == "set_level":
            self._set_level(int(value))
        elif action == "set_color":
            self._set_player_color(int(value))
        elif action == "set_board_size":
            self._set_board_size(int(value))
        elif action == "set_clock":
            mode, minutes, increment = value
            self._set_clock(mode, minutes, increment)
        elif action == "set_theme":
            self._set_theme(str(value))
        elif action == "toggle":
            self._toggle_setting(str(value))
        elif action == "slider_volume":
            self._set_slider("volume", value)
        elif action == "slider_scale":
            self._set_slider("scale", value)
        elif action == "test_sound":
            self.sound.play("place")
        elif action == "sidebar_ply":
            self._review_ply(int(value))

    def on_board_click(self, row: int, col: int) -> None:
        if self.selected_ply is not None:
            self.selected_ply = None
            return
        if self.session.game_over:
            self._show_game_over()
            return
        if self.replay_active:
            self.replay_active = False
        if not self.session.is_human_turn():
            self.sound.play("invalid")
            return
        if not self.session.is_legal(row, col):
            self.sound.play("invalid")
            self.renderer.shake.trigger(self._now(), amplitude=2.0, duration=0.12)
            return
        self._play(row, col)

    def on_key(self, key: int, mods: int, text: str = "") -> None:
        if key == pg.K_ESCAPE:
            if self.overlay is not None:
                self._close_overlay()
            else:
                self.quit()
            return
        if self.overlay == "options" and key == pg.K_TAB:
            self.options_tab = "Appearance" if self.options_tab == "Game" else "Game"
            self._refresh_options()
            return

        contexts = []
        if self.overlay == "gameover" or self.selected_ply is not None:
            contexts.append(REPLAY)
        contexts.append(PLAYING)
        if self.session.mode == MODE_AVA:
            contexts.append(AI_VS_AI)

        action = None
        for context in contexts:
            action = lookup(key, mods, context)
            if action:
                break
        if action is None:
            return

        dispatch = {
            "help": self._open_help,
            "options": self._open_options,
            "fullscreen": self._toggle_fullscreen,
            "debug": self._toggle_debug,
            "save": self._save_game,
            "load": self._load_game,
            "new_game": self._new_game,
            "undo": self._undo,
            "redo": self._redo,
            "toggle_hints": self._toggle_hints,
            "hint": self._request_hint,
            "cycle_level": self._cycle_level,
            "cycle_mode": self._cycle_mode,
            "cycle_theme": self._cycle_theme,
            "cycle_board_size": self._cycle_board_size,
            "toggle_sound": self._toggle_sound,
            "analyse": self._analyse_now,
            "pause": self._toggle_pause,
            "faster": lambda: self._set_ava_speed(self.ava_speed + 1),
            "slower": lambda: self._set_ava_speed(self.ava_speed - 1),
            "replay_toggle": self._toggle_replay,
            "replay_next": lambda: self._step_review(1),
            "replay_prev": lambda: self._step_review(-1),
            "replay_end": lambda: self._set_review_ply(len(self.session.records)),
            "replay_start": lambda: self._set_review_ply(0),
            "set_level": lambda: self._set_level(int(text)) if text.isdigit() else None,
        }
        handler = dispatch.get(action)
        if handler is None:
            return
        try:
            handler()
        except IagoError as exc:
            self._warn(str(exc))

    # ------------------------------------------------------------------
    # Gameplay
    # ------------------------------------------------------------------

    def _play(self, row: int, col: int) -> None:
        try:
            record = self.session.apply_move(row, col)
        except IagoError as exc:
            self._warn(str(exc))
            return
        self._after_move(record.player, record.flips, row, col)

    def _after_move(
        self, player: int, flips: Tuple[Tuple[int, int], ...], row: int, col: int
    ) -> None:
        record = self.session.records[-1]
        self.renderer.animate_move(record)
        self.sound.play("place")
        if flips:
            self.sound.play("flip", variant=len(flips))
        self.engine.record_move(player, row, col)
        self.engine2.record_move(player, row, col)
        self.thinking = None
        self.message = ""
        self._refresh_auto_hint()
        if record.passed_next:
            self.renderer.notify("No moves — turn passed", self.theme.warn)
            self.sound.play("pass")
        if self.overlay == "gameover":
            self.overlay = None
            self.overlay_data = None
        if self.session.game_over:
            self._end_game()
        elif self.session.ply % AUTOSAVE_EVERY == 0:
            self._autosave()

    def _maybe_start_ai(self) -> None:
        if self.overlay in ("resume", "options"):
            return
        if self.session.game_over or self.session.is_human_turn():
            return
        if self.worker.busy:
            return
        if self.session.mode == MODE_AVA:
            if self.paused:
                return
            now = self._now()
            if (
                now - self._last_ava_move
                < AVA_DELAYS[min(self.ava_speed, len(AVA_DELAYS) - 1)]
            ):
                return
        engine = self._engine_for(self.session.current_player)
        limits = self._limits_for(engine)
        self.thinking = None
        self.ai_started_at = time.monotonic()
        self.worker.start(engine, self.session.board, limits)

    def _poll_search(self) -> None:
        progress, final = self.worker.poll()
        if final is None:
            if progress is not None and self.worker.busy:
                self.thinking = progress
            return
        self.worker.take_result()
        self.thinking = None
        if self.session.game_over:
            return
        player = self.session.current_player
        move = final.move
        if move is None:
            if self.session.play_pending_pass():
                self.renderer.notify("No moves — turn passed", self.theme.warn)
                self.sound.play("pass")
            return
        if not self.session.is_legal(*move):
            logger.warning("Engine returned illegal move %s; picking a legal one", move)
            legal = self.session.legal_moves()
            if not legal:
                return
            move = legal[0]
        self.session.apply_move(move[0], move[1])
        self._after_move(player, self.session.records[-1].flips, move[0], move[1])
        self._last_ava_move = self._now()

    def _refresh_auto_hint(self) -> None:
        """Keep a cheap best-move marker in sync with the position."""

        if not self.settings.show_hints or self.session.game_over:
            self.pending_hint = None
            return
        if not self.session.is_human_turn():
            self.pending_hint = None
            return
        try:
            self.pending_hint = self.engine.quick_hint(self.session.board)
        except IagoError:  # pragma: no cover - defensive
            self.pending_hint = None

    def _poll_hint(self) -> None:
        progress, final = self.hint_worker.poll()
        if final is None:
            return
        self.hint_worker.take_result()
        if final.move is not None:
            self.pending_hint = final.move
        if progress is not None and final.move is None:
            self.pending_hint = progress.move

    def _poll_review(self) -> None:
        _, review = self.review_worker.poll()
        if review is not None and self.review is None:
            self.review = self.review_worker.take()
            if self.review is not None and self.overlay in ("gameover", "review"):
                self._refresh_game_over()

    def _tick_clock(self) -> None:
        if self.session.clock.mode == "off" or self.session.game_over:
            return
        now = time.monotonic()
        flagged = self.session.clock.flagged(now)
        if flagged is not None:
            self.session.finish_on_time(now)
            self.game_over_reason = "time"
            self._end_game()

    def _tick_replay(self, dt: float) -> None:
        if not self.replay_active:
            return
        if self.selected_ply is None:
            self.selected_ply = 0
        self._replay_timer = getattr(self, "_replay_timer", 0.0) + dt
        delay = 0.55
        if self._replay_timer >= delay:
            self._replay_timer = 0.0
            self._step_review(1)

    def _end_game(self) -> None:
        self.replay_active = False
        if self.session.mode == MODE_HVAI:
            self._record_stats()
        duration = self.session.elapsed()
        self.review = None
        self.review_worker.start(self.session.to_move_log(), self.session.size, depth=2)
        self.renderer.celebrate(self.session.winner)
        winner_text = (
            "Draw"
            if self.session.winner == 0
            else ("Black wins" if self.session.winner == PLAYER_BLACK else "White wins")
        )
        self.renderer.notify(winner_text, self.theme.accent)
        if self.session.mode == MODE_HVAI:
            if self.session.winner == self.session.player_color:
                self.sound.play("win")
            elif self.session.winner == 0:
                self.sound.play("draw")
            else:
                self.sound.play("lose")
        self._show_game_over()
        self._autosave()
        logger.info(
            "Game over: winner=%s moves=%d duration=%.1fs",
            self.session.winner,
            self.session.move_count,
            duration,
        )

    def _record_stats(self) -> None:
        summary = GameSummary(
            mode=self.session.mode,
            level=self.session.level,
            player_color=self.session.player_color,
            winner=self.session.winner,
            moves=self.session.move_count,
            board_size=self.session.size,
            black_score=self.session.score()[0],
            white_score=self.session.score()[1],
            duration=self.session.elapsed(),
            lowest_probability=self.session.lowest_probability,
        )
        self.stats.record_result(
            level=self.session.level,
            winner=self.session.winner,
            player_color=self.session.player_color,
            moves=self.session.move_count,
            player_score=summary.player_score,
            opponent_score=summary.opponent_score,
            duration=summary.duration,
        )
        unlocked = evaluate_achievements(self.stats, summary)
        self.new_achievements = [achievement.title for achievement in unlocked]
        if unlocked:
            self.sound.play("unlock")
            for achievement in unlocked:
                self.renderer.notify(
                    f"Achievement: {achievement.title}", self.theme.good
                )
        persistence.save_stats(self.stats)

    # ------------------------------------------------------------------
    # Commands
    # ------------------------------------------------------------------

    def _new_game(self) -> None:
        self.worker.cancel()
        self.hint_worker.cancel()
        self.review_worker.cancel()
        self.session.reset(
            size=self.settings.board_size,
            mode=self.settings.mode,
            player_color=self.settings.player_color,
            level=self.settings.ai_level,
            clock_mode=self.settings.clock_mode,
            blitz_base=self.settings.blitz_minutes * 60.0,
            increment=float(self.settings.blitz_increment),
        )
        self.engine.resize(self.session.size)
        self.engine2.resize(self.session.size)
        self.engine.difficulty = self.settings.ai_level
        self.engine2.difficulty = self.settings.ai_level
        self.engine.reset_log()
        self.engine2.reset_log()
        self._apply_clock_settings()
        self.session.clock.start(self.session.current_player, time.monotonic())
        self._refresh_auto_hint()
        self.renderer.animations.clear()
        self.renderer.particles.clear()
        self._sync_scores()
        self.overlay = None
        self.overlay_data = None
        self.thinking = None
        self.pending_hint = None
        self.selected_ply = None
        self.review = None
        self.new_achievements = []
        self.replay_active = False
        self.game_over_reason = "board"
        self.message = ""
        self.sound.play("ui")
        self._maybe_start_ai()

    def _undo(self) -> None:
        if not self.session.can_undo():
            self.sound.play("invalid")
            return
        self.worker.cancel()
        self.session.undo()
        if (
            self.session.mode == MODE_HVAI
            and not self.session.game_over
            and not self.session.is_human_turn()
            and self.session.can_undo()
        ):
            self.session.undo()
        self._sync_engine_logs()
        self._sync_scores()
        self.thinking = None
        self.pending_hint = None
        self.overlay = None
        self.overlay_data = None
        self.selected_ply = None
        self._refresh_auto_hint()
        self.renderer.animations.clear()
        self.sound.play("ui")

    def _redo(self) -> None:
        if not self.session.can_redo():
            self.sound.play("invalid")
            return
        self.worker.cancel()
        self.session.redo()
        self._sync_engine_logs()
        self._sync_scores()
        self.thinking = None
        self.selected_ply = None
        self.sound.play("ui")

    def _sync_scores(self) -> None:
        black, white = self.session.score()
        self.renderer.sync_scores(black, white)

    def _sync_engine_logs(self) -> None:
        self.engine.reset_log()
        self.engine2.reset_log()
        for player, row, col in self.session.to_move_log():
            self.engine.record_move(player, row, col)
            self.engine2.record_move(player, row, col)

    def _request_hint(self) -> None:
        if self.session.game_over:
            return
        if self.hint_worker.busy:
            self.hint_worker.cancel()
        limits = SearchLimits(time_limit=0.6, max_depth=12, endgame_empties=10)
        self.hint_worker.start(self.engine, self.session.board, limits)
        self.sound.play("ui")

    def _analyse_now(self) -> None:
        if not self.session.move_count:
            return
        self.review = None
        self.review_worker.start(self.session.to_move_log(), self.session.size, depth=2)
        self._show_game_over()

    def _toggle_hints(self) -> None:
        self.settings.show_hints = not self.settings.show_hints
        if not self.settings.show_hints:
            self.pending_hint = None
        self.sound.play("ui")
        self._save_settings()

    def _cycle_level(self) -> None:
        self._set_level((self.settings.ai_level % MAX_DIFFICULTY) + 1)

    def _set_level(self, level: int) -> None:
        level = max(1, min(MAX_DIFFICULTY, level))
        self.settings.ai_level = level
        self.session.level = level
        self.engine.difficulty = level
        self.engine2.difficulty = level
        self.engine.reset_log()
        self._sync_engine_logs()
        self._save_settings()
        self.renderer.notify(f"Difficulty: {get_level(level).name}", self.theme.accent)
        self.sound.play("ui")

    def _cycle_mode(self) -> None:
        index = (MODES.index(self.settings.mode) + 1) % len(MODES)
        self._set_mode(MODES[index])

    def _set_mode(self, mode: str) -> None:
        if mode == self.settings.mode:
            return
        self.settings.mode = mode
        self._save_settings()
        self.renderer.notify(
            f"Mode: {MODE_LABELS_FALLBACK.get(mode, mode)}", self.theme.accent
        )
        self._new_game()

    def _set_player_color(self, color: int) -> None:
        if color == self.settings.player_color:
            return
        self.settings.player_color = color
        self._save_settings()
        self._new_game()

    def _cycle_board_size(self) -> None:
        sizes = SUPPORTED_BOARD_SIZES
        index = (
            sizes.index(self.settings.board_size)
            if self.settings.board_size in sizes
            else 1
        )
        self._set_board_size(sizes[(index + 1) % len(sizes)])

    def _set_board_size(self, size: int) -> None:
        if size == self.settings.board_size:
            return
        self.settings.board_size = size
        self.renderer.set_board_size(size)
        self._save_settings()
        self.renderer.notify(f"Board: {size}×{size}", self.theme.accent)
        self._new_game()

    def _set_clock(self, mode: str, minutes: int, increment: int) -> None:
        self.settings.clock_mode = mode
        self.settings.blitz_minutes = minutes
        self.settings.blitz_increment = increment
        self._save_settings()
        self._new_game()

    def _cycle_theme(self) -> None:
        self._set_theme(next_theme(self.settings.theme))

    def _set_theme(self, key: str) -> None:
        self.settings.theme = key
        self.theme = get_theme(key)
        self.renderer.set_theme(self.theme)
        self._save_settings()
        self.renderer.notify(f"Theme: {self.theme.name}", self.theme.accent)
        self.sound.play("ui")

    def _toggle_setting(self, key: str) -> None:
        mapping = {
            "animations": "animations",
            "particles": "particles",
            "coordinates": "show_coordinates",
            "eval_bar": "show_eval_bar",
            "sound": "sound_enabled",
        }
        attribute = mapping.get(key, key)
        value = not getattr(self.settings, attribute)
        setattr(self.settings, attribute, value)
        if attribute == "sound_enabled":
            self.sound.set_enabled(value)
        self._save_settings()
        self.sound.play("ui")
        self._refresh_options()

    def _toggle_sound(self) -> None:
        self._toggle_setting("sound")

    def _set_slider(self, kind: str, value: Optional[float] = None) -> None:
        if kind == "volume":
            self.settings.sound_volume = max(0.0, min(1.0, self.settings.sound_volume))
            self.sound.set_volume(self.settings.sound_volume)
        else:
            self.settings.ui_scale = max(0.75, min(1.5, self.settings.ui_scale))
            self.renderer.set_ui_scale(self.settings.ui_scale)
        self._save_settings()
        self._refresh_options()

    def _handle_drag(self, position: Tuple[int, int]) -> None:
        target = self._slider_target(self.dragging)
        if target is None:
            return
        fraction = (position[0] - target.x) / max(1, target.w)
        fraction = max(0.0, min(1.0, fraction))
        if self.dragging == "volume":
            self.settings.sound_volume = fraction
            self.sound.set_volume(fraction)
        elif self.dragging == "scale":
            self.settings.ui_scale = 0.75 + fraction * 0.75
            self.renderer.set_ui_scale(self.settings.ui_scale)

    def _slider_target(self, kind: Optional[str]):
        if kind is None:
            return None
        for target in self.renderer.targets:
            if target.action == f"slider_{kind}":
                return target.rect
        return None

    def _toggle_fullscreen(self) -> None:
        self._set_fullscreen(not self.settings.fullscreen)

    def _set_fullscreen(self, fullscreen: bool) -> None:
        self.settings.fullscreen = fullscreen
        try:
            if fullscreen:
                info = pg.display.Info()
                size = (info.current_w, info.current_h)
                self.renderer.surface = pg.display.set_mode(size, pg.FULLSCREEN)
                self.renderer.layout = compute_layout(
                    size, self.renderer.board_size, self.renderer.ui_scale
                )
            else:
                size = (self.settings.window_width, self.settings.window_height)
                self.renderer.resize(size)
        except pg.error as exc:  # pragma: no cover - display specific
            logger.warning("Fullscreen toggle failed: %s", exc)
        self._save_settings()

    def _toggle_debug(self) -> None:
        self.debug = not self.debug

    def _toggle_pause(self) -> None:
        self.paused = not self.paused
        if self.paused:
            self.worker.cancel()
        self.renderer.notify("Paused" if self.paused else "Resumed", self.theme.accent)

    def _set_ava_speed(self, value: int) -> None:
        self.ava_speed = max(0, min(len(AVA_DELAYS) - 1, value))
        labels = ("Instant", "Fast", "Normal", "Slow")
        self.renderer.notify(f"AI speed: {labels[self.ava_speed]}", self.theme.accent)

    # ------------------------------------------------------------------
    # Replay / review
    # ------------------------------------------------------------------

    def _review_ply(self, ply: int) -> None:
        self._set_review_ply(ply)
        self.sound.play("ui")

    def _set_review_ply(self, ply: int) -> None:
        total = len(self.session.records)
        self.selected_ply = max(0, min(total, ply))
        self.replay_active = False

    def _step_review(self, delta: int) -> None:
        current = (
            self.selected_ply
            if self.selected_ply is not None
            else len(self.session.records)
        )
        self._set_review_ply(current + delta)

    def _toggle_replay(self) -> None:
        if self.selected_ply is None:
            self.selected_ply = 0
        self.replay_active = not self.replay_active
        self._replay_timer = 0.0

    # ------------------------------------------------------------------
    # Overlays
    # ------------------------------------------------------------------

    def _open_options(self) -> None:
        self.overlay = "options"
        self._refresh_options()
        self.sound.play("ui")

    def _refresh_options(self) -> None:
        if self.overlay == "options":
            self.overlay_data = OptionsData(
                settings=self.settings,
                tab=self.options_tab,
                mouse=self._mouse,
            )

    def _open_help(self) -> None:
        self.overlay = "help"
        self.overlay_data = None
        self.sound.play("ui")

    def _open_stats(self) -> None:
        self.overlay = "stats"
        self.overlay_data = None
        self.sound.play("ui")

    def _show_game_over(self) -> None:
        self.overlay = "gameover"
        self._refresh_game_over()

    def _refresh_game_over(self) -> None:
        self.overlay_data = GameOverData(
            session=self.session,
            reason=self.game_over_reason,
            review=self.review,
            review_progress=self.review_worker.progress,
            achievements=tuple(self.new_achievements),
            selected_ply=self.selected_ply,
        )

    def _close_overlay(self) -> None:
        if self.overlay == "resume":
            self._discard_resume()
        self.overlay = None
        self.overlay_data = None
        self.dragging = None

    def _on_button(self, key: str) -> None:
        handlers = {
            "new_game": self._new_game,
            "undo": self._undo,
            "redo": self._redo,
            "hint": self._request_hint,
            "options": self._open_options,
            "help": self._open_help,
            "close": self._close_overlay,
            "close_overlay": self._close_overlay,
            "rematch": self._new_game,
            "review": self._analyse_now,
            "stats": self._open_stats,
            "resume": self._resume_game,
            "discard": self._discard_resume,
        }
        handler = handlers.get(key)
        if handler is not None:
            self.sound.play("ui")
            handler()

    # ------------------------------------------------------------------
    # Persistence
    # ------------------------------------------------------------------

    def _save_game(self) -> None:
        payload = persistence.build_save_payload(
            board_size=self.session.size,
            mode=self.session.mode,
            level=self.session.level,
            player_color=self.session.player_color,
            moves=self.session.to_move_log(),
            game_over=self.session.game_over,
            winner=self.session.winner,
            clocks={
                "mode": self.settings.clock_mode,
                "elapsed": {
                    str(player): value
                    for player, value in self.session.clock.elapsed.items()
                },
            },
        )
        try:
            path = persistence.save_game_file(payload)
        except SaveFileError as exc:
            self._warn(str(exc))
            return
        self.renderer.notify(f"Saved to {path.name}", self.theme.good)
        self.sound.play("ui")

    def _load_game(self) -> None:
        saved_path = paths.save_path()
        if not saved_path.exists():
            candidates = persistence.find_autosave()
            if candidates is None:
                self._warn("No saved game found")
                return
            saved_path = candidates
        try:
            saved = persistence.load_game(saved_path)
        except SaveFileError as exc:
            self._warn(str(exc))
            return
        self._apply_saved_game(saved)
        self.renderer.notify(f"Loaded {saved.move_count} moves", self.theme.good)

    def _apply_saved_game(self, saved: persistence.SavedGame) -> None:
        self.settings.mode = saved.mode
        self.settings.board_size = saved.board_size
        self.settings.player_color = saved.player_color
        self.settings.ai_level = saved.level
        self.renderer.set_board_size(saved.board_size)
        self.session = Session(
            size=saved.board_size,
            mode=saved.mode,
            player_color=saved.player_color,
            level=saved.level,
        )
        self._apply_clock_settings()
        self.session.load_move_log(saved.moves)
        self._sync_engine_logs()
        self.overlay = None
        self.overlay_data = None
        self.thinking = None
        self.review = None
        self.selected_ply = None
        self.replay_active = False
        self._sync_scores()
        self.session.clock.start(self.session.current_player, time.monotonic())
        self._maybe_start_ai()

    def _resume_game(self) -> None:
        if self._resume_path is None:
            self._close_overlay()
            return
        try:
            saved = persistence.load_game(self._resume_path)
        except SaveFileError as exc:
            self._warn(str(exc))
            self._discard_resume()
            return
        self._apply_saved_game(saved)
        self.renderer.notify("Game resumed", self.theme.good)

    def _discard_resume(self) -> None:
        persistence.delete_autosave()
        self._resume_path = None
        self.overlay = None
        self.overlay_data = None

    def _autosave(self) -> None:
        payload = persistence.build_save_payload(
            board_size=self.session.size,
            mode=self.session.mode,
            level=self.session.level,
            player_color=self.session.player_color,
            moves=self.session.to_move_log(),
            game_over=self.session.game_over,
            winner=self.session.winner,
        )
        try:
            persistence.save_game_file(payload, paths.autosave_path())
            self._last_autosave = self.session.ply
        except SaveFileError as exc:
            logger.info("Autosave failed: %s", exc)

    def _save_settings(self) -> None:
        self.settings.window_width = self.renderer.layout.width
        self.settings.window_height = self.renderer.layout.height
        try:
            persistence.save_settings(self.settings)
        except IagoError as exc:
            logger.warning("Could not save settings: %s", exc)

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _engine_for(self, player: int) -> Engine:
        if self.session.mode == MODE_AVA:
            return self.engine if player == PLAYER_BLACK else self.engine2
        return self.engine

    def _limits_for(self, engine: Engine) -> SearchLimits:
        level = get_level(engine.difficulty)
        return SearchLimits(
            time_limit=level.time_limit,
            max_depth=level.max_depth,
            endgame_empties=level.endgame_empties,
            noise=level.noise,
        )

    def _opening_name(self) -> Optional[str]:
        opening = identify_opening(self.session.to_move_log(), self.session.size)
        if opening is not None:
            return opening.name
        return self.engine.opening_name() or self.engine2.opening_name()

    def _notation(self, cell: Tuple[int, int]) -> str:
        from ..core.notation import move_name

        return move_name(cell[0], cell[1])

    def _warn(self, text: str) -> None:
        self.renderer.notify(text, self.theme.bad)
        self.sound.play("invalid")
        logger.warning(text)

    def _now(self) -> float:
        return pg.time.get_ticks() / 1000.0

    def quit(self) -> None:
        self.running = False

    def shutdown(self) -> None:
        self.worker.cancel()
        self.hint_worker.cancel()
        self.review_worker.cancel()
        if self.session.move_count and not self.session.game_over:
            self._autosave()
        self._save_settings()
        persistence.save_stats(self.stats)
        self.sound.shutdown()
        pg.quit()
        logger.info("Shut down cleanly")


MODE_LABELS_FALLBACK = {
    "hvai": "Human vs AI",
    "hvh": "2-Player",
    "ava": "AI vs AI",
}


__all__ = ["Game", "LaunchOptions"]
