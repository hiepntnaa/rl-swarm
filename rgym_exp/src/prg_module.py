from enum import Enum
import json
import os
from genrl.logging_utils.global_defs import get_logger
from rgym_exp.src.coordinator import PRGCoordinator


class PRGGameStatus(Enum):
    ERROR = "Error"
    NO_ACTIVE_GAME = "No active game"
    ALREADY_ANSWERED = "Already answered"
    SUCCESS = "Success"


class PRGModule:
    def __init__(self, log_dir, **kwargs):
        """
        PRGModule quản lý trạng thái chơi PRG cho từng peer.

        Thêm các tham số debug sau để tiện test / ghi log chi tiết:
        - debug: bật/tắt chế độ debug (mặc định False)
        - debug_override_bet_amt: nếu không None, dùng giá trị này (wei) thay cho bet tính toán
        - debug_token_balance: nếu không None, dùng giá trị này (wei) thay cho gọi coordinator
        - debug_verbose: nếu True sẽ ghi nhiều log hơn
        """
        prg_game_config = kwargs.get("prg_game_config", None)
        self._prg_game = False
        self.log_dir = log_dir

        # peer_id có thể được truyền vào kwargs, hoặc để None ban đầu
        self.peer_id = kwargs.get("peer_id", None)

        # Debug/test flags (chỉ bật ở môi trường dev/test)
        self.debug = kwargs.get("debug", False)
        self.debug_override_bet_amt = kwargs.get("debug_override_bet_amt", None)
        self.debug_token_balance = kwargs.get("debug_token_balance", None)
        self.debug_verbose = kwargs.get("debug_verbose", True) if self.debug else False

        if prg_game_config:
            prg_game = prg_game_config.get("prg_game", False)
            self._prg_game = True if prg_game in [True, "true"] else False
            if self._prg_game:
                modal_proxy_url = prg_game_config.get("modal_proxy_url", None)
                org_id = prg_game_config.get("org_id", None)
                if not modal_proxy_url or not org_id:
                    self._prg_game = False
                    get_logger().debug(
                        "PRG game disabled due to missing configuration."
                    )
                else:
                    self.prg_coordinator = PRGCoordinator(
                        org_id,
                        modal_proxy_url,
                    )
                    self._prg_history_dict = {}
                    self.prg_last_game_claimed = None
                    self.prg_last_game_played = None

    def _set_peer_files(self, peer_id):
        """Thiết lập đường dẫn file cho 1 peer cụ thể và load state nếu có."""
        self.peer_id = peer_id
        self.prg_state_file = os.path.join(
            self.log_dir, f"prg_state_{peer_id}.json"
        )
        self.prg_record = os.path.join(
            self.log_dir, f"prg_record_{peer_id}.txt"
        )
        self.load_state()

    def backup_state(self):
        """Ghi trạng thái hiện tại ra file JSON để có thể restore sau này."""
        with open(self.prg_state_file, "w") as f:
            json.dump(
                {
                    "prg_history_dict": self._prg_history_dict,
                    "prg_last_game_claimed": self.prg_last_game_claimed,
                    "prg_last_game_played": self.prg_last_game_played,
                },
                f,
            )

    def load_state(self):
        """Nạp state từ file nếu có."""
        # Nếu chưa set peer files thì không làm gì
        if not hasattr(self, 'prg_state_file'):
            return

        if os.path.exists(self.prg_state_file):
            with open(self.prg_state_file, "r") as f:
                state = json.load(f)
                # prg_history_dict keys được convert về int để dễ dùng làm key
                self._prg_history_dict = {
                    int(k): v for k, v in state.get("prg_history_dict", {}).items()
                }
                self.prg_last_game_claimed = state.get("prg_last_game_claimed")
                self.prg_last_game_played = state.get("prg_last_game_played")
            get_logger().info(
                "Loaded PRG state from file:\n\t"
                f"last game claimed - {self.prg_last_game_claimed},\n\t"
                f"last game played - {self.prg_last_game_played}"
            )

    @property
    def prg_game(self):
        return self._prg_game

    @property
    def prg_history_dict(self):
        return self._prg_history_dict

    def play_prg_game(self, results_dict, peer_id):
        """Chơi 1 ván PRG và lưu log theo peer_id.

        Các log chi tiết:
        - token_balance(before): số dư token (wei) trước khi đặt cược
        - calculated_bet: giá trị bet tính toán (wei) trước khi gọi guess_answer()
        - expected_remaining: số dư ước tính sau khi trừ bet (wei)
        - token_balance(after): số dư thực tế (nếu có thể lấy lại từ coordinator) sau khi đặt cược

        Lưu ý: convert sang token dạng float bằng chia 1e18 dùng helper `fmt` để hiển thị đẹp.
        """
        # Thiết lập file cho peer hiện tại nếu khác
        if self.peer_id != peer_id:
            self._set_peer_files(peer_id)
            # Gán đáp án
            results_dict["choice_idx"] = 0
            results_dict["choice"] = "Jalebi"

        status = results_dict.get("status", PRGGameStatus.ERROR)
        if status == PRGGameStatus.SUCCESS:
            # Chỉ xử lý khi có choice_idx hợp lệ
            if results_dict.get("choice_idx", -1) >= 0:
                current_game = results_dict["game_idx"]
                try:
                    # ------------------
                    # Lấy số dư token trước khi bet
                    # ------------------
                    # Nếu đang bật debug và có debug_token_balance thì dùng giá trị đó
                    if self.debug and self.debug_token_balance is not None:
                        token_balance = int(self.debug_token_balance)
                    else:
                        token_balance = self.prg_coordinator.bet_token_balance(peer_id)

                    # rounds_remaining tối thiểu là 1 để tránh chia cho 0
                    rounds_remaining = max(1, results_dict["rounds_remaining"])

                    # Tính bet mặc định bằng chia đều số dư cho số round còn lại
                    bet_amt = token_balance // rounds_remaining

                    # Nếu debug override bet amt được cung cấp (dùng cho test), áp dụng
                    if self.debug and self.debug_override_bet_amt is not None:
                        bet_amt = int(self.debug_override_bet_amt)

                    # Helper format: chuyển wei -> token (float) để in log dễ đọc
                    def fmt(wei):
                        try:
                            return f"{wei / 1e18:.6f}"
                        except Exception:
                            return str(wei)

                    # expected_remaining: số dư ước tính còn lại nếu bet thành công
                    expected_remaining = max(0, token_balance - bet_amt)

                    # ------------------
                    # Log chi tiết trước khi bet
                    # ------------------
                    # Comment: Dòng này in ra số dư trước khi bet, rounds_remaining, bet tính toán,
                    # và số dư ước tính sau khi trừ bet. Giúp bạn biết code đang tính toán gì.
                    get_logger().info(
                        f"PRG DEBUG: peer={peer_id}, game={current_game}, clue={results_dict['clue_idx']}, "
                        f"token_balance(before)={fmt(token_balance)} tokens, rounds_remaining={rounds_remaining}, "
                        f"calculated_bet={fmt(bet_amt)} tokens, expected_remaining={fmt(expected_remaining)} tokens"
                    )

                    # ------------------
                    # Gọi guess_answer() nếu bet_amt > 0
                    # ------------------
                    if bet_amt > 0:
                        # Thực hiện đặt cược / gửi dự đoán lên coordinator (có thể là gọi API hoặc tx)
                        self.prg_coordinator.guess_answer(
                            current_game,
                            peer_id,
                            results_dict["clue_idx"],
                            results_dict["choice_idx"],
                            bet_amt,
                        )

                        # ------------------
                        # Thử lấy lại số dư thực tế sau khi bet
                        # ------------------
                        # Comment: Nếu backend cập nhật ngay thì giá trị này sẽ giảm đúng bằng bet_amt.
                        # Nếu backend xử lý không ngay lập tức, giá trị có thể chưa thay đổi —
                        # nhưng log này vẫn hữu ích để debug timing/cadence.
                        try:
                            actual_remaining = self.prg_coordinator.bet_token_balance(peer_id)
                        except Exception:
                            actual_remaining = None

                        if actual_remaining is not None:
                            get_logger().info(
                                # Comment: Dòng này in số dư thực tế sau khi gọi guess_answer().
                                f"PRG DEBUG: peer={peer_id}, token_balance(after)={fmt(actual_remaining)} tokens"
                            )
                            # Ghi vào file prg_record cả before/after để tiện tra cứu
                            with open(self.prg_record, "a") as f:
                                f.write(
                                    f"Game {current_game} Round {results_dict['clue_idx']}: "
                                    f"Peer {peer_id} token_before={fmt(token_balance)} tokens, "
                                    f"placed_bet={fmt(bet_amt)} tokens, token_after={fmt(actual_remaining)} tokens, "
                                    f"choice={results_dict['choice']}\n"
                                )
                        else:
                            get_logger().info(
                                "PRG DEBUG: could not fetch actual token balance after bet."
                            )
                            # Nếu không lấy được actual_remaining thì vẫn ghi expected info vào prg_record
                            with open(self.prg_record, "a") as f:
                                f.write(
                                    f"Game {current_game} Round {results_dict['clue_idx']}: "
                                    f"Peer {peer_id} token_before={fmt(token_balance)} tokens, "
                                    f"placed_bet={fmt(bet_amt)} tokens, token_after=UNKNOWN, "
                                    f"choice={results_dict['choice']}\n"
                                )

                    else:
                        # Không đặt cược do bet_amt bằng 0
                        get_logger().info(
                            f"PRG DEBUG: bet amount is zero (bet_amt={fmt(bet_amt)}). No guess_answer() called."
                        )
                        with open(self.prg_record, "a") as f:
                            f.write(
                                f"Game {current_game} Round {results_dict['clue_idx']}: "
                                f"Peer {peer_id} placed NO bet (bet_amt=0), choice={results_dict['choice']}\n"
                            )

                    # ------------------
                    # Cập nhật lịch sử nội bộ và backup state
                    # ------------------
                    self._prg_history_dict[current_game] = results_dict["clue_idx"]

                    # Log dòng tóm tắt như trước (phiên bản human-friendly)
                    log_str = (
                        f'Game {current_game} Round {results_dict["clue_idx"]}: '
                        f"Peer {peer_id} placed bet of {fmt(bet_amt)} tokens "
                        f'on choice - {results_dict["choice"]}\n'
                    )
                    get_logger().info(log_str)

                except Exception as e:
                    # Ghi log exception ở mức debug để không spam production error
                    get_logger().debug(str(e))

                # ------------------
                # Nếu sang game mới thì claim game cũ
                # ------------------
                if self.prg_last_game_played and current_game != self.prg_last_game_played:
                    try:
                        self.prg_coordinator.claim_reward(
                            self.prg_last_game_played, peer_id
                        )
                        get_logger().info(
                            f"successfully claimed reward for previous game {self.prg_last_game_played}"
                        )
                        with open(self.prg_record, "a") as f:
                            f.write(
                                f"successfully claimed reward for previous game {self.prg_last_game_played}\n"
                            )
                        self.prg_last_game_claimed = self.prg_last_game_played
                    except Exception as e:
                        get_logger().debug(str(e))

                self.prg_last_game_played = current_game
                self.backup_state()

        elif status == PRGGameStatus.NO_ACTIVE_GAME:
            # game kết thúc, thử claim nếu chưa
            if (
                self.prg_last_game_played
                and self.prg_last_game_played != self.prg_last_game_claimed
            ):
                try:
                    self.prg_coordinator.claim_reward(
                        self.prg_last_game_played, peer_id
                    )
                    get_logger().info(
                        f"successfully claimed reward for previous game {self.prg_last_game_played}"
                    )
                    with open(self.prg_record, "a") as f:
                        f.write(
                            f"successfully claimed reward for previous game {self.prg_last_game_played}\n"
                        )
                    self.prg_last_game_claimed = self.prg_last_game_played
                    self.prg_last_game_played = None
                    self.backup_state()
                except Exception as e:
                    get_logger().debug(str(e))
