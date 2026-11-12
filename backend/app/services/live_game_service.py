from __future__ import annotations

import threading
import time

from collections import deque
from datetime import datetime

import chess
import cv2
import numpy as np

from backend.app.chess.game_tracker import GameTracker
from backend.app.services.bot_service import bot_service
from backend.app.services.camera_service import camera_service
from backend.app.vision.fixed_calibration import (
    calculate_checker_score,
    load_fixed_board_geometry,
)
from backend.app.vision.pipeline import (
    class_to_chess_piece,
    recognize_position,
)


PROCESS_INTERVAL_SECONDS = 0.12
OBSERVATION_INTERVAL_SECONDS = 0.65
OBSERVATION_WINDOW = 3
MOVE_CONFIRMATIONS = 2

CHECKER_DROP_FOR_OCCLUSION = 0.10
FOREIGN_OBJECT_CHANGED_SQUARES = 5
MOVING_DISPLAY_SECONDS = 0.35

VALID_GAME_MODES = {
    "human_vs_human",
    "human_vs_bot",
}

VALID_POSITION_MODES = {
    "standard",
    "detect",
}

VALID_CAMERA_ORIENTATIONS = {
    "white_left",
    "black_left",
}

VALID_HUMAN_COLORS = {
    "white",
    "black",
}


class LiveGameService:

    def __init__(self):
        self.lock = threading.RLock()
        self.stop_event = threading.Event()
        self.thread: threading.Thread | None = None

        self.tracker = GameTracker()

        self.running = False
        self.status = "stopped"
        self.status_message = "Live game is stopped."

        self.game_mode = "human_vs_human"
        self.bot_type = "beginner"
        self.position_mode = "detect"
        self.camera_orientation = "white_left"
        self.selected_turn = "w"

        self.white_name = "White"
        self.black_name = "Black"

        self.human_color: str | None = None
        self.bot_color: str | None = None
        self.started_at: str | None = None

        self.board_points: list[list[float]] | None = None
        self.outer_points: list[list[float]] | None = None

        self.board_detection_score: float | None = None
        self.board_checker_score: float | None = None
        self.board_detection_method: str | None = None

        self.tracking_shift_px = 0.0
        self.observation_change_count = 0
        self.observed_board_fen: str | None = None
        self.last_error: str | None = None

        self._observations = deque(
            maxlen=OBSERVATION_WINDOW
        )

        self._previous_raw_signature: tuple[bool, ...] | None = None
        self._last_recognition_at = 0.0
        self._candidate_uci: str | None = None
        self._candidate_count = 0
        self._last_resolution: dict | None = None
        self._current_position_check: dict | None = None
        self._clean_checker_baseline: float | None = None
        self._moving_until = 0.0

        self.pending_bot_move: dict | None = None

    def _validate_setup(
        self,
        game_mode: str,
        position_mode: str,
        camera_orientation: str,
        side_to_move: str,
        human_color: str | None,
        bot_type: str,
    ):
        if game_mode not in VALID_GAME_MODES:
            raise ValueError(
                "game_mode must be human_vs_human or human_vs_bot"
            )

        if position_mode not in VALID_POSITION_MODES:
            raise ValueError(
                "position_mode must be standard or detect"
            )

        if camera_orientation not in VALID_CAMERA_ORIENTATIONS:
            raise ValueError(
                "camera_orientation must be white_left or black_left"
            )

        if side_to_move not in ("w", "b"):
            raise ValueError(
                "side_to_move must be w or b"
            )

        if game_mode == "human_vs_bot":
            bot_service.validate_bot_type(bot_type)

            if human_color not in VALID_HUMAN_COLORS:
                raise ValueError(
                    "human_color must be white or black in bot mode"
                )

    def _clean_name(
        self,
        name: str,
        fallback: str,
    ) -> str:
        cleaned = " ".join(name.strip().split())
        return cleaned or fallback

    def _clear_candidate(self):
        self._candidate_uci = None
        self._candidate_count = 0

    def _wait_for_old_thread(self):
        with self.lock:
            old_thread = self.thread

        if old_thread is not None and old_thread.is_alive():
            self.stop_event.set()
            old_thread.join(timeout=3.0)

    def _bot_chess_color(self) -> chess.Color | None:
        if self.bot_color == "white":
            return chess.WHITE

        if self.bot_color == "black":
            return chess.BLACK

        return None

    def _human_chess_color(self) -> chess.Color | None:
        if self.human_color == "white":
            return chess.WHITE

        if self.human_color == "black":
            return chess.BLACK

        return None

    def _is_bot_turn(self) -> bool:
        if (
            self.game_mode != "human_vs_bot"
            or not self.tracker.initialized
            or self.tracker.board.is_game_over(claim_draw=True)
        ):
            return False

        bot_color = self._bot_chess_color()

        return (
            bot_color is not None
            and self.tracker.board.turn == bot_color
        )

    def _prepare_bot_move(self):
        if not self._is_bot_turn():
            self.pending_bot_move = None
            return

        if self.pending_bot_move is not None:
            return

        result = bot_service.choose_move(
            self.tracker.board,
            bot_type=self.bot_type,
        )

        self.pending_bot_move = {
            "name": result["name"],
            "estimated_rating": result["estimated_rating"],
            "color": self.bot_color,
            "uci": result["uci"],
            "san": result["san"],
        }

        self.status = "waiting_bot_move"
        self.status_message = (
            f"Bot move: {result['san']}. "
            "Play this move on the physical board."
        )

        print()
        print("==========================================")
        print("BOT MOVE READY")
        print("==========================================")
        print(f"SAN: {result['san']}")
        print(f"UCI: {result['uci']}")
        print("==========================================")
        print()

    def _track_board(
        self,
        frame: np.ndarray,
    ):
        with self.lock:
            board_points = (
                None
                if self.board_points is None
                else [point[:] for point in self.board_points]
            )

            outer_points = (
                None
                if self.outer_points is None
                else [point[:] for point in self.outer_points]
            )

        if board_points is None or outer_points is None:
            raise RuntimeError(
                "Fixed board calibration is not loaded."
            )

        checker_score = calculate_checker_score(
            frame,
            board_points,
        )

        with self.lock:
            self.board_checker_score = checker_score
            self.tracking_shift_px = 0.0

        return board_points, outer_points

    def _occupancy_signature(
        self,
        recognition: dict,
    ) -> tuple[bool, ...]:
        squares = recognition["squares"]

        return tuple(
            bool(
                squares[chess.square_name(square)]["occupied"]
            )
            for square in chess.SQUARES
        )

    def _signature_difference(
        self,
        a: tuple[bool, ...],
        b: tuple[bool, ...],
    ) -> int:
        return sum(
            1
            for left, right in zip(a, b)
            if left != right
        )

    def _build_consensus(self) -> dict:
        observations = list(self._observations)
        board = chess.Board(None)
        output_squares = {}

        for square in chess.SQUARES:
            name = chess.square_name(square)

            predictions = [
                observation["squares"][name]
                for observation in observations
            ]

            empty_probability = sum(
                float(prediction["empty_probability"])
                for prediction in predictions
            ) / len(predictions)

            occupied_probability = sum(
                float(prediction["occupied_probability"])
                for prediction in predictions
            ) / len(predictions)

            occupied = (
                occupied_probability >= empty_probability
            )

            piece_scores = {}
            piece_confidences = {}

            for prediction in predictions:
                piece = prediction.get("piece")
                confidence = float(
                    prediction.get("piece_confidence") or 0.0
                )

                if piece is None:
                    continue

                piece_scores[piece] = (
                    piece_scores.get(piece, 0.0)
                    + confidence
                )

                piece_confidences.setdefault(
                    piece, []
                ).append(confidence)

            selected_piece = None
            piece_confidence = None

            if occupied and piece_scores:
                selected_piece = max(
                    piece_scores,
                    key=piece_scores.get,
                )

                values = piece_confidences[selected_piece]
                piece_confidence = sum(values) / len(values)

                try:
                    chess_piece = class_to_chess_piece(
                        selected_piece
                    )

                    board.set_piece_at(
                        square,
                        chess_piece,
                    )

                except Exception:
                    selected_piece = None
                    piece_confidence = None

            output_squares[name] = {
                "square": name,
                "occupied": occupied,
                "occupancy_confidence": max(
                    empty_probability,
                    occupied_probability,
                ),
                "empty_probability": empty_probability,
                "occupied_probability": occupied_probability,
                "piece": selected_piece,
                "piece_confidence": piece_confidence,
                "scale_predictions": [],
            }

        return {
            "board_fen": board.board_fen(),
            "squares": output_squares,
        }

    def _foreign_object_present(self) -> bool:
        if (
            self._clean_checker_baseline is None
            or self.board_checker_score is None
        ):
            return False

        return (
            self.board_checker_score
            <
            self._clean_checker_baseline
            - CHECKER_DROP_FOR_OCCLUSION
        )

    def _update_checker_baseline(self):
        if self.board_checker_score is None:
            return

        if self._clean_checker_baseline is None:
            self._clean_checker_baseline = (
                self.board_checker_score
            )
            return

        self._clean_checker_baseline = (
            self._clean_checker_baseline * 0.9
            + self.board_checker_score * 0.1
        )

    def _after_move_commit(self, san: str):
        self._clear_candidate()
        self._observations.clear()
        self._update_checker_baseline()

        if self.tracker.board.is_game_over(claim_draw=True):
            self.pending_bot_move = None
            self.status = "game_over"
            self.status_message = f"Committed {san}. Game over."
            return

        if self._is_bot_turn():
            self._prepare_bot_move()
            return

        next_player = (
            "White"
            if self.tracker.board.turn
            else "Black"
        )

        self.status = "stable"
        self.status_message = (
            f"Committed {san}. Waiting for {next_player}."
        )

    def _handle_consensus(self, consensus: dict):
        board_fen = consensus["board_fen"]
        square_predictions = consensus["squares"]

        self.observed_board_fen = board_fen

        if not self.tracker.initialized:
            result = self.tracker.initialize_from_board_fen(
                board_fen=board_fen,
                turn=self.selected_turn,
            )

            if not result["ok"]:
                self.status = "scanning_current_position"
                self.status_message = (
                    "Current board is visible, but recognition "
                    "is not yet a valid chess position."
                )
                self.last_error = result.get("reason")
                return

            self._update_checker_baseline()
            self._observations.clear()
            self._clear_candidate()
            self.last_error = None

            if self._is_bot_turn():
                self._prepare_bot_move()
            else:
                next_player = (
                    "White"
                    if self.tracker.board.turn
                    else "Black"
                )

                self.status = "stable"
                self.status_message = (
                    "Current physical position loaded. "
                    f"Waiting for {next_player}."
                )

            return

        current_check = (
            self.tracker.evaluate_current_position_from_vision(
                square_predictions
            )
        )

        self._current_position_check = current_check

        if current_check["occupancy_mismatch_count"] == 0:
            self._clear_candidate()
            self._update_checker_baseline()

            if self.tracker.board.is_game_over(claim_draw=True):
                self.status = "game_over"
                self.status_message = "Game over."
                return

            if self.pending_bot_move is not None:
                self.status = "waiting_bot_move"
                self.status_message = (
                    f"Bot move: {self.pending_bot_move['san']}. "
                    "Play this move on the physical board."
                )
                return

            if self._is_bot_turn():
                self._prepare_bot_move()
                return

            next_player = (
                "White"
                if self.tracker.board.turn
                else "Black"
            )

            self.status = "stable"
            self.status_message = (
                f"Board stable. Waiting for {next_player}."
            )
            return

        resolution = (
            self.tracker.resolve_move_from_vision(
                square_predictions
            )
        )

        self._last_resolution = {
            key: value
            for key, value in resolution.items()
            if key != "move"
        }

        move = resolution.get("move")

        if move is None:
            self._clear_candidate()

            if self._foreign_object_present():
                self.status = "occluded"
                self.status_message = (
                    "Board is partially covered. "
                    "Digital state remains frozen."
                )
            else:
                self.status = "unrecognized"
                self.status_message = (
                    "Observed position changed, but it is "
                    "not yet a clear legal move."
                )

            return

        uci = move.uci()

        if self.pending_bot_move is not None:
            expected_uci = self.pending_bot_move["uci"]

            if uci != expected_uci:
                self._clear_candidate()
                self.status = "wrong_bot_move"
                self.status_message = (
                    f"Bot expects {self.pending_bot_move['san']}. "
                    "The detected physical move is different."
                )
                return

        elif (
            self.game_mode == "human_vs_bot"
            and self._is_bot_turn()
        ):
            self._prepare_bot_move()
            self._clear_candidate()
            return

        if self._candidate_uci == uci:
            self._candidate_count += 1
        else:
            self._candidate_uci = uci
            self._candidate_count = 1

        if self._candidate_count < MOVE_CONFIRMATIONS:
            self.status = "verifying"

            if self.pending_bot_move is not None:
                self.status_message = (
                    f"Detected bot move "
                    f"{self.pending_bot_move['san']}. "
                    "Verifying once more..."
                )
            else:
                try:
                    san = self.tracker.board.san(move)
                except Exception:
                    san = uci

                self.status_message = (
                    f"Detected {san}. Verifying once more..."
                )

            return

        record = self.tracker.commit_move(move)

        if (
            self.pending_bot_move is not None
            and uci == self.pending_bot_move["uci"]
        ):
            self.pending_bot_move = None

        self._after_move_commit(record["san"])

    def _handle_recognition(self, recognition: dict):
        signature = self._occupancy_signature(
            recognition
        )

        change_count = 0

        if self._previous_raw_signature is not None:
            change_count = self._signature_difference(
                self._previous_raw_signature,
                signature,
            )

        self._previous_raw_signature = signature
        self.observation_change_count = change_count

        now = time.monotonic()

        if (
            self.tracker.initialized
            and self._foreign_object_present()
            and change_count >= FOREIGN_OBJECT_CHANGED_SQUARES
        ):
            self._moving_until = (
                now + MOVING_DISPLAY_SECONDS
            )

            self.status = "moving"
            self.status_message = (
                "Hand / foreign object entered the board. "
                "Digital board is frozen briefly."
            )
            self._observations.clear()
            self._clear_candidate()
            return

        if (
            self.tracker.initialized
            and self._foreign_object_present()
        ):
            self.status = "occluded"
            self.status_message = (
                "Board is partially covered. "
                "Waiting for a clear view."
            )
            self._observations.clear()
            self._clear_candidate()
            return

        self._observations.append(recognition)

        if len(self._observations) < OBSERVATION_WINDOW:
            if not self.tracker.initialized:
                self.status = "scanning_current_position"
                self.status_message = (
                    "Reading current physical position..."
                )

            elif now > self._moving_until:
                if self.pending_bot_move is not None:
                    self.status = "waiting_bot_move"
                    self.status_message = (
                        f"Bot move: "
                        f"{self.pending_bot_move['san']}. "
                        "Waiting for it on the board."
                    )
                else:
                    self.status = "sampling"
                    self.status_message = (
                        "Comparing board observations..."
                    )

            return

        consensus = self._build_consensus()
        self._handle_consensus(consensus)

    def start(
        self,
        white_name: str = "White",
        black_name: str = "Black",
        game_mode: str = "human_vs_human",
        human_color: str | None = None,
        bot_type: str = "beginner",
        side_to_move: str = "w",
        camera_orientation: str = "white_left",
        position_mode: str = "detect",
    ) -> dict:

        self._validate_setup(
            game_mode=game_mode,
            position_mode=position_mode,
            camera_orientation=camera_orientation,
            side_to_move=side_to_move,
            human_color=human_color,
            bot_type=bot_type,
        )

        with self.lock:
            if self.running:
                return self.get_state()

        self._wait_for_old_thread()

        if game_mode == "human_vs_bot":
            bot_service.ensure_ready(bot_type)

        frame = camera_service.get_frame(
            timeout=5.0
        )

        calibration = load_fixed_board_geometry(frame)

        board_points = calibration["board_points"]
        outer_points = calibration["outer_points"]

        checker_score = calculate_checker_score(
            frame,
            board_points,
        )

        with self.lock:
            self.game_mode = game_mode
            self.bot_type = (
                bot_type
                if game_mode == "human_vs_bot"
                else "beginner"
            )
            self.position_mode = position_mode
            self.camera_orientation = camera_orientation
            self.selected_turn = side_to_move

            self.human_color = (
                human_color
                if game_mode == "human_vs_bot"
                else None
            )

            if self.human_color == "white":
                self.bot_color = "black"
            elif self.human_color == "black":
                self.bot_color = "white"
            else:
                self.bot_color = None

            clean_white_name = self._clean_name(
                white_name,
                "White",
            )

            clean_black_name = self._clean_name(
                black_name,
                "Black",
            )

            if game_mode == "human_vs_bot":
                if self.bot_color == "white":
                    clean_white_name = (
                        bot_service.get_name(self.bot_type)
                    )
                else:
                    clean_black_name = (
                        bot_service.get_name(self.bot_type)
                    )

            self.white_name = clean_white_name
            self.black_name = clean_black_name
            self.started_at = datetime.utcnow().isoformat()

            self.tracker.reset_uninitialized()

            if position_mode == "standard":
                standard_board = chess.Board()

                result = (
                    self.tracker.initialize_from_board_fen(
                        board_fen=standard_board.board_fen(),
                        turn=side_to_move,
                    )
                )

                if not result["ok"]:
                    raise RuntimeError(
                        result.get(
                            "reason",
                            "Could not initialize standard position.",
                        )
                    )

            self.board_points = board_points
            self.outer_points = outer_points
            self.board_detection_score = float(
                calibration["score"]
            )
            self.board_checker_score = checker_score
            self.board_detection_method = str(
                calibration["method"]
            )

            self.tracking_shift_px = 0.0
            self.observation_change_count = 0
            self.observed_board_fen = None
            self.last_error = None

            self._observations.clear()
            self._previous_raw_signature = None
            self._last_recognition_at = 0.0
            self._clear_candidate()
            self._last_resolution = None
            self._current_position_check = None
            self._clean_checker_baseline = checker_score
            self._moving_until = 0.0
            self.pending_bot_move = None

            self.stop_event.clear()
            self.running = True

            if position_mode == "detect":
                self.status = "scanning_current_position"
                self.status_message = (
                    "Fixed calibration loaded. "
                    "Reading current physical position..."
                )
            else:
                self.status = "stable"
                self.status_message = (
                    "Fixed calibration loaded. "
                    "Standard starting position loaded."
                )

            if self._is_bot_turn():
                try:
                    self._prepare_bot_move()

                except Exception as error:
                    self.running = False
                    self.stop_event.set()
                    self.pending_bot_move = None
                    self.status = "error"
                    self.status_message = (
                        "Could not prepare the first bot move."
                    )
                    self.last_error = str(error)
                    raise

            print()
            print("==========================================")
            print("LIVE GAME STARTED")
            print("==========================================")
            print(f"Mode: {self.game_mode}")
            print(f"White: {self.white_name}")
            print(f"Black: {self.black_name}")
            print(f"Position mode: {self.position_mode}")
            print(f"Side to move: {self.selected_turn}")
            print(f"Camera: {self.camera_orientation}")
            print("Geometry: fixed_calibration")
            print("==========================================")
            print()

            self.thread = threading.Thread(
                target=self._run_loop,
                daemon=True,
                name="LiveGameProcessor",
            )

            self.thread.start()

            return self.get_state()

    def stop(self) -> dict:
        self.stop_event.set()

        with self.lock:
            thread = self.thread

        if (
            thread is not None
            and thread.is_alive()
            and thread is not threading.current_thread()
        ):
            thread.join(timeout=3.0)

        with self.lock:
            self.running = False
            self.status = "stopped"
            self.status_message = "Live game is stopped."

            return self.get_state()

    def _run_loop(self):
        while not self.stop_event.is_set():
            started = time.monotonic()

            try:
                frame = camera_service.get_frame(
                    timeout=2.0
                )

                board_points, outer_points = self._track_board(
                    frame
                )

                now = time.monotonic()

                if (
                    now - self._last_recognition_at
                    >= OBSERVATION_INTERVAL_SECONDS
                ):
                    self._last_recognition_at = now

                    recognition = recognize_position(
                        frame=frame,
                        outer_points=outer_points,
                        board_points=board_points,
                        camera_orientation=self.camera_orientation,
                    )

                    with self.lock:
                        self.last_error = None
                        self._handle_recognition(
                            recognition
                        )

            except Exception as error:
                with self.lock:
                    self.status = "error"
                    self.status_message = (
                        "Live processing error. "
                        "Digital board is frozen."
                    )
                    self.last_error = str(error)

                print()
                print("LIVE GAME ERROR")
                print(error)
                print()

                self.stop_event.wait(0.4)

            finally:
                elapsed = time.monotonic() - started
                remaining = (
                    PROCESS_INTERVAL_SECONDS - elapsed
                )

                if remaining > 0:
                    self.stop_event.wait(remaining)

        with self.lock:
            self.running = False

    def draw_debug_overlay(
        self,
        frame: np.ndarray,
    ) -> np.ndarray:

        output = frame.copy()

        with self.lock:
            board_points = (
                None
                if self.board_points is None
                else [point[:] for point in self.board_points]
            )

            outer_points = (
                None
                if self.outer_points is None
                else [point[:] for point in self.outer_points]
            )

            status = self.status
            checker = self.board_checker_score
            orientation = self.camera_orientation

        if board_points is None:
            try:
                calibration = load_fixed_board_geometry(
                    frame
                )

                board_points = calibration["board_points"]
                outer_points = calibration["outer_points"]

                checker = calculate_checker_score(
                    frame,
                    board_points,
                )

                with self.lock:
                    self.board_points = board_points
                    self.outer_points = outer_points
                    self.board_detection_score = 1.0
                    self.board_checker_score = checker
                    self.board_detection_method = (
                        "fixed_calibration"
                    )
                    self.tracking_shift_px = 0.0

            except Exception:
                cv2.rectangle(
                    output,
                    (10, 10),
                    (min(output.shape[1] - 10, 760), 88),
                    (0, 0, 0),
                    -1,
                )

                cv2.putText(
                    output,
                    "FIXED CALIBRATION REQUIRED",
                    (20, 40),
                    cv2.FONT_HERSHEY_SIMPLEX,
                    0.78,
                    (0, 0, 255),
                    2,
                    cv2.LINE_AA,
                )

                cv2.putText(
                    output,
                    "Run: python src/calibration.py",
                    (20, 70),
                    cv2.FONT_HERSHEY_SIMPLEX,
                    0.58,
                    (255, 255, 255),
                    1,
                    cv2.LINE_AA,
                )

                return output

        board = np.asarray(
            board_points,
            dtype=np.float32,
        )

        if outer_points is not None:
            outer = np.asarray(
                outer_points,
                dtype=np.int32,
            )

            cv2.polylines(
                output,
                [outer.reshape(-1, 1, 2)],
                True,
                (0, 220, 255),
                2,
                cv2.LINE_AA,
            )

        board_int = board.astype(np.int32)

        cv2.polylines(
            output,
            [board_int.reshape(-1, 1, 2)],
            True,
            (0, 255, 0),
            3,
            cv2.LINE_AA,
        )

        canonical = np.array(
            [
                [0, 0],
                [800, 0],
                [800, 800],
                [0, 800],
            ],
            dtype=np.float32,
        )

        homography = cv2.getPerspectiveTransform(
            canonical,
            board,
        )

        def project(points):
            array = np.asarray(
                points,
                dtype=np.float32,
            ).reshape(-1, 1, 2)

            transformed = cv2.perspectiveTransform(
                array,
                homography,
            ).reshape(-1, 2)

            return transformed.astype(np.int32)

        for index in range(9):
            p = index * 100

            vertical = project(
                [[p, 0], [p, 800]]
            )

            horizontal = project(
                [[0, p], [800, p]]
            )

            cv2.line(
                output,
                tuple(vertical[0]),
                tuple(vertical[1]),
                (0, 255, 0),
                1,
                cv2.LINE_AA,
            )

            cv2.line(
                output,
                tuple(horizontal[0]),
                tuple(horizontal[1]),
                (0, 255, 0),
                1,
                cv2.LINE_AA,
            )

        labels = ["TL", "TR", "BR", "BL"]

        for label, point in zip(labels, board_int):
            x = int(point[0])
            y = int(point[1])

            cv2.circle(
                output,
                (x, y),
                6,
                (0, 255, 0),
                -1,
            )

            cv2.putText(
                output,
                label,
                (x + 7, y - 7),
                cv2.FONT_HERSHEY_SIMPLEX,
                0.55,
                (0, 255, 0),
                2,
                cv2.LINE_AA,
            )

        left_label = (
            "WHITE"
            if orientation == "white_left"
            else "BLACK"
        )

        right_label = (
            "BLACK"
            if orientation == "white_left"
            else "WHITE"
        )

        center_left = (
            board[0] + board[3]
        ) / 2.0

        center_right = (
            board[1] + board[2]
        ) / 2.0

        cv2.putText(
            output,
            left_label,
            (
                int(center_left[0]) + 8,
                int(center_left[1]),
            ),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.55,
            (255, 255, 0),
            2,
            cv2.LINE_AA,
        )

        cv2.putText(
            output,
            right_label,
            (
                int(center_right[0]) - 65,
                int(center_right[1]),
            ),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.55,
            (255, 255, 0),
            2,
            cv2.LINE_AA,
        )

        text = f"{status} | FIXED CALIBRATION"

        if checker is not None:
            text += f" | checker {checker:.2f}"

        cv2.rectangle(
            output,
            (10, 10),
            (min(output.shape[1] - 10, 620), 55),
            (0, 0, 0),
            -1,
        )

        cv2.putText(
            output,
            text,
            (20, 40),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.65,
            (255, 255, 255),
            2,
            cv2.LINE_AA,
        )

        return output

    def get_state(self) -> dict:
        with self.lock:
            game_state = self.tracker.get_state()

            return {
                "running": self.running,
                "status": self.status,
                "status_message": self.status_message,
                "game_mode": self.game_mode,
                "bot_type": self.bot_type,
                "position_mode": self.position_mode,
                "camera_orientation": self.camera_orientation,
                "selected_turn": self.selected_turn,
                "white_name": self.white_name,
                "black_name": self.black_name,
                "human_color": self.human_color,
                "bot_color": self.bot_color,
                "started_at": self.started_at,
                "pending_bot_move": self.pending_bot_move,
                "tracking_shift_px": self.tracking_shift_px,
                "observation_change_count":
                    self.observation_change_count,
                "observed_board_fen": self.observed_board_fen,
                "board_detection_score":
                    self.board_detection_score,
                "board_checker_score":
                    self.board_checker_score,
                "board_detection_method":
                    self.board_detection_method,
                "board_points": self.board_points,
                "last_error": self.last_error,
                "current_position_check":
                    self._current_position_check,
                "move_resolution": self._last_resolution,
                "eco_code": None,
                "opening_name": None,
                **game_state,
            }


live_game_service = LiveGameService()