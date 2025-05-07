import asyncio
import collections  # specifically for deque
import logging
import re
import sys
import termios
import time
import tty
from collections.abc import Callable
from dataclasses import dataclass, field  # Added for dataclasses
from enum import Enum, auto  # Added for Enum
from pathlib import Path

from rich.columns import Columns
from rich.console import Group
from rich.live import Live
from rich.panel import Panel
from rich.progress import (
    Progress,  # Keep for potential future use within this module
    SpinnerColumn,
    TaskID,
    TextColumn,
    TimeElapsedColumn,
)
from rich.spinner import Spinner
from rich.table import Table
from rich.text import Text

from .config import Config
from .k8s_utils import create_async_kubectl_process

# Import the shared async runner
from .live_display import _run_async_main
from .memory import update_memory
from .model_adapter import get_model_adapter
from .types import (  # Removed StatsProtocol as it's not directly used
    Error,
    OutputFlags,
    Result,
    Success,
)
from .utils import console_manager

logger = logging.getLogger(__name__)


# --- State and Actions for Keypress Handling (Module Level) ---
@dataclass
class WatchDisplayState:
    wrap_text: bool = True
    is_paused: bool = False
    filter_regex_str: str | None = None
    filter_compiled_regex: re.Pattern | None = None


class WatchKeypressAction(Enum):
    EXIT = auto()
    TOGGLE_WRAP = auto()
    TOGGLE_PAUSE = auto()
    PROMPT_SAVE = auto()
    PROMPT_FILTER = auto()
    UPDATE_STATE_ONLY = auto()  # Use when only state changes (e.g. wrap toggle)
    NO_ACTION = auto()  # For unrecognized keys


def process_keypress(
    char: str,
    current_state: WatchDisplayState,
) -> tuple[WatchDisplayState, WatchKeypressAction]:
    """Processes a keypress, returning updated state and requested action."""
    new_state = current_state  # Start with current state
    action = WatchKeypressAction.NO_ACTION  # Default action

    char_lower = char.lower()

    if char_lower == "e":
        action = WatchKeypressAction.EXIT
        # State does not change
    elif char_lower == "w":
        new_state = WatchDisplayState(
            wrap_text=not current_state.wrap_text,
            is_paused=current_state.is_paused,  # Preserve other state
            filter_regex_str=current_state.filter_regex_str,
            filter_compiled_regex=current_state.filter_compiled_regex,
        )
        action = WatchKeypressAction.TOGGLE_WRAP  # Signify wrap toggled
    elif char_lower == "p":
        new_state = WatchDisplayState(
            wrap_text=current_state.wrap_text,  # Preserve other state
            is_paused=not current_state.is_paused,
            filter_regex_str=current_state.filter_regex_str,
            filter_compiled_regex=current_state.filter_compiled_regex,
        )
        action = WatchKeypressAction.TOGGLE_PAUSE  # Signify pause toggled
    elif char_lower == "s":
        action = WatchKeypressAction.PROMPT_SAVE
        # State does not change here; prompt handler will manage temporary pause
    elif char_lower == "f":
        action = WatchKeypressAction.PROMPT_FILTER
        # State does not change here; prompt handler will manage temporary pause and update state

    # Return the (potentially updated) state and the determined action
    return new_state, action


def _create_watch_summary_table(
    command_str: str,
    final_status: str,
    elapsed_time: float,
    lines_streamed: int,
    error_message: str | None,
    operation_had_error: bool,
) -> Table:
    """Creates the summary table for a watch session."""
    summary_table = Table(
        title="Watch Session Summary",
        title_style="bold cyan",
        show_header=True,
        header_style="bold magenta",
    )
    summary_table.add_column("Parameter", style="dim")
    summary_table.add_column("Value")
    summary_table.add_row("Command", f"`kubectl {command_str}`")
    summary_table.add_row("Status", final_status)
    summary_table.add_row("Duration", f"{elapsed_time:.2f} seconds")
    summary_table.add_row("Lines Streamed", str(lines_streamed))

    if error_message and (
        operation_had_error
        or "warning" in final_status.lower()
        or "cancel" in final_status.lower()
    ):
        style = "red" if operation_had_error else "yellow"
        summary_table.add_row("Message", Text(error_message, style=style))

    return summary_table


# --- Pure Save Logic Helper ---
def _perform_save_to_file(
    save_dir: Path,
    filename_suggestion: str,
    user_provided_filename: str | None,
    all_lines: collections.deque[str],
    filter_re: re.Pattern | None,
) -> Path:
    """Handles filename logic and writing filtered lines to a file.

    Raises:
        OSError/IOError: If file writing fails.
    """
    save_filename = user_provided_filename or filename_suggestion
    save_path = save_dir / save_filename

    # Apply filter before saving
    if filter_re:
        lines_to_save = [line for line in all_lines if filter_re.search(line)]
    else:
        lines_to_save = list(all_lines)

    # Write the file (can raise IOError/OSError)
    save_path.write_text("\n".join(lines_to_save), encoding="utf-8")
    logger.info(f"Watch output saved to {save_path}")
    return save_path


# --- Main Watch Execution ---
async def _execute_watch_with_live_display(
    command: str,
    resource: str,
    args: tuple[str, ...],
    output_flags: OutputFlags,
    display_text: str,
) -> Result:
    """Executes the core logic for commands with `--watch` using a live display.

    Handles running the kubectl command, streaming its output to a Rich Live display,
    managing user interactions (exit, pause, wrap, save, filter), and summarizing
    the output with an LLM after the watch session concludes.

    Args:
        command: The kubectl command verb (e.g., 'get', 'describe').
        resource: The resource type (e.g., pod, deployment).
        args: Command arguments including resource name and conditions.
        output_flags: Flags controlling output format and LLM interaction.
        display_text: The initial text/title for the live display panel.

    Returns:
        A Result object, either Success (with raw output) or Error.
    """
    start_time = time.time()
    cfg = Config()
    live_display_max_lines = cfg.get("live_display_max_lines")
    live_display_wrap_text = cfg.get("live_display_wrap_text")
    live_display_save_dir = cfg.get("live_display_save_dir")
    live_display_filter_regex = cfg.get("live_display_default_filter_regex")
    # Fetch the buffer max lines for the main stream history
    stream_buffer_max_lines = cfg.get("live_display_stream_buffer_max_lines", 10000) # Default to 10000 if not set

    command_str = f"{command} {resource} {' '.join(args)}"
    vibe_output: dict | None = None
    accumulated_output_lines: list[str] = []
    error_message: str | None = None

    live_display_content = Text("", no_wrap=not live_display_wrap_text)
    loop = asyncio.get_running_loop()

    # --- Module-level state (managed via nonlocals in callbacks) ---
    current_session_wrap_state = live_display_wrap_text
    is_display_paused_state = False
    current_filter_regex_str_state: str | None = live_display_filter_regex
    current_filter_compiled_regex_state: re.Pattern | None = None
    if current_filter_regex_str_state:
        try:
            current_filter_compiled_regex_state = re.compile(
                current_filter_regex_str_state
            )
        except re.error as e_re:
            logger.warning(
                f"Invalid initial filter regex '{current_filter_regex_str_state}': {e_re}"
            )
            current_filter_regex_str_state = None

    all_streamed_lines: collections.deque[str] = collections.deque(maxlen=stream_buffer_max_lines)
    total_lines_actually_streamed_counter = 0

    footer_controls_text_obj = Text("", style="dim")
    status_bar_text_obj = Text("Initializing...", style="dim i")

    overall_layout = Group(
        Panel(
            live_display_content,
            title=display_text,
            border_style="blue",
            height=live_display_max_lines + 2,
        ),
        status_bar_text_obj,
        footer_controls_text_obj,
    )

    save_dir = Path(live_display_save_dir).expanduser()
    try:
        save_dir.mkdir(parents=True, exist_ok=True)
    except OSError as e:
        logger.error(f"Could not create save directory {save_dir}: {e}")

    # --- Nested Helper Functions ---
    async def main_watch_task() -> Result:
        """Runs watch command, streams output, and handles user interactions."""
        nonlocal error_message, vibe_output, accumulated_output_lines, save_dir
        nonlocal footer_controls_text_obj, live_display_content, all_streamed_lines
        nonlocal total_lines_actually_streamed_counter, resource
        nonlocal current_session_wrap_state, is_display_paused_state
        nonlocal current_filter_regex_str_state, current_filter_compiled_regex_state
        nonlocal loop

        original_termios_settings = None
        input_reader_active = False
        exit_requested_event = asyncio.Event()
        process: asyncio.subprocess.Process | None = None
        stream_handler_task: asyncio.Task | None = None
        process_wait_task_local: asyncio.Task | None = None
        exit_monitor_task_local: asyncio.Task | None = None
        final_status = "Unknown"  # Default

        def _refresh_footer_controls_text() -> None:
            """Updates the footer text based on current state object."""
            wrap_status = "on" if current_session_wrap_state else "off"
            pause_status = "paused" if is_display_paused_state else "running"
            filter_status = (
                f"'{current_filter_regex_str_state}'"
                if current_filter_regex_str_state
                else "off"
            )
            controls = [
                "[E]xit",
                f"[W]rap: {wrap_status}",
                f"[P]ause: {pause_status}",
                "[S]ave",
                f"[F]ilter: {filter_status}",
            ]
            footer_controls_text_obj.plain = " | ".join(controls)

        async def _wrapped_process_wait(proc: asyncio.subprocess.Process) -> None:
            if proc:
                await proc.wait()

        async def _wrapped_event_wait(event: asyncio.Event) -> None:
            if event:
                await event.wait()

        def _apply_filter_to_lines(
            lines_to_filter: collections.deque[str] | list[str],
            compiled_filter_regex: re.Pattern | None,
        ) -> list[str]:
            if not compiled_filter_regex:
                return list(lines_to_filter)
            return [
                line for line in lines_to_filter if compiled_filter_regex.search(line)
            ]

        def _handle_save_action() -> None:
            """Handles the 'Save' action: TTY, prompts, calls pure save logic, updates status."""
            # Dependencies needed for TTY and UI updates remain non-local for now
            nonlocal original_termios_settings, input_reader_active, loop
            nonlocal \
                status_bar_text_obj, \
                save_dir, \
                all_streamed_lines, \
                current_filter_compiled_regex_state, \
                resource

            if not sys.stdin.isatty():
                status_bar_text_obj.plain = "Save failed: No TTY for input."
                logger.warning("Save action ignored: Not running in a TTY.")
                _refresh_footer_controls_text()  # Restore footer
                return

            status_bar_text_obj.plain = "Preparing to save..."
            _refresh_footer_controls_text()  # Show updated status bar

            # Temporarily pause input reader and restore TTY
            if input_reader_active:
                loop.remove_reader(sys.stdin.fileno())
            if original_termios_settings:
                termios.tcsetattr(
                    sys.stdin.fileno(), termios.TCSADRAIN, original_termios_settings
                )

            filename_suggestion = f"vibectl_watch_{resource.replace('/', '_')}_{time.strftime('%Y%m%d_%H%M%S')}.log"
            prompt_text = f"Enter filename to save output (in {save_dir}) [Default: {filename_suggestion}]: "

            saved_path: Path | None = None
            error_msg: str | None = None

            try:
                user_input = input(prompt_text).strip()
                # Call the pure helper function
                saved_path = _perform_save_to_file(
                    save_dir=save_dir,
                    filename_suggestion=filename_suggestion,
                    user_provided_filename=user_input or None,
                    all_lines=all_streamed_lines,
                    filter_re=current_filter_compiled_regex_state,
                )
                status_bar_text_obj.plain = (
                    f"Output saved to {saved_path}. Press any key to continue..."
                )
            except (OSError, IOError) as e:
                error_msg = f"Save failed: {e}"
                logger.error(f"Error saving watch output: {e}", exc_info=True)
            except (EOFError, KeyboardInterrupt) as e:
                error_msg = f"Save cancelled: {e}"
                logger.warning(f"Save input cancelled: {e}")
            finally:
                if error_msg:
                    status_bar_text_obj.plain = (
                        f"{error_msg}. Press any key to continue..."
                    )
                # Wait briefly for user to see status, then restore TTY cbreak & reader
                # Need a small delay even if successful
                loop.call_later(
                    1.5, _restore_tty_and_reader
                )  # Use call_later for delay

        def _restore_tty_and_reader() -> None:
            """Helper to restore TTY and re-add input reader."""
            nonlocal \
                original_termios_settings, \
                input_reader_active, \
                loop, \
                status_bar_text_obj
            if sys.stdin.isatty():
                if original_termios_settings:
                    try:
                        tty.setcbreak(sys.stdin.fileno())
                        if input_reader_active:
                            loop.add_reader(sys.stdin.fileno(), _input_reader_callback)
                    except Exception as e_restore:
                        logger.warning(
                            f"Failed during TTY/reader restore after save/filter: {e_restore}"
                        )
                status_bar_text_obj.plain = ""  # Clear status bar
                _refresh_footer_controls_text()  # Restore normal footer

        def _handle_filter_action() -> None:
            """Handles the 'Filter' action: prompts for regex and updates state/display."""
            nonlocal \
                original_termios_settings, \
                input_reader_active, \
                loop, \
                status_bar_text_obj
            nonlocal current_filter_regex_str_state, current_filter_compiled_regex_state
            nonlocal all_streamed_lines, live_display_content, live_display_max_lines

            if not sys.stdin.isatty():
                status_bar_text_obj.plain = "Filter failed: No TTY for input."
                logger.warning("Filter action ignored: Not running in a TTY.")
                _refresh_footer_controls_text()
                return

            current_filter_display = (
                f" (current: '{current_filter_regex_str_state}')"
                if current_filter_regex_str_state
                else " (currently off)"
            )
            prompt_text = (
                f"Enter filter regex (leave empty to clear){current_filter_display}: "
            )

            # Temporarily pause input reader and restore TTY
            loop.remove_reader(sys.stdin.fileno())
            if original_termios_settings:
                termios.tcsetattr(
                    sys.stdin.fileno(), termios.TCSADRAIN, original_termios_settings
                )

            new_filter_str: str | None = None
            new_filter_re: re.Pattern | None = None
            filter_update_status = "Filter cleared."

            try:
                user_input = input(prompt_text).strip()
                if user_input:
                    try:
                        new_filter_re = re.compile(user_input)
                        new_filter_str = user_input
                        filter_update_status = f"Filter set to '{new_filter_str}'."
                        logger.info(f"Watch filter regex set to: {new_filter_str}")
                    except re.error as e_re:
                        filter_update_status = (
                            f"Invalid regex: {e_re}. Filter not changed."
                        )
                        logger.warning(
                            f"Invalid filter regex provided: {user_input} ({e_re})"
                        )
                        # Keep old filter state if compilation failed
                        new_filter_str = current_filter_regex_str_state
                        new_filter_re = current_filter_compiled_regex_state
                else:
                    logger.info("Watch filter cleared.")
                    # Keep new_filter_str/re as None

                # Update state regardless of success/failure (keep old on failure)
                current_filter_regex_str_state = new_filter_str
                current_filter_compiled_regex_state = new_filter_re

                # Re-apply filter and update display immediately
                filtered_lines = _apply_filter_to_lines(
                    all_streamed_lines, current_filter_compiled_regex_state
                )
                latest_lines_to_display = filtered_lines[-live_display_max_lines:]
                num_padding = max(
                    0, live_display_max_lines - len(latest_lines_to_display)
                )
                padded_display_lines = ([" "] * num_padding) + latest_lines_to_display
                live_display_content.plain = "\n".join(padded_display_lines)

                status_bar_text_obj.plain = (
                    f"{filter_update_status} Press any key to continue..."
                )

            except (EOFError, KeyboardInterrupt) as e:
                status_bar_text_obj.plain = (
                    f"Filter input cancelled: {e}. Press any key..."
                )
                logger.warning(f"Filter input cancelled: {e}")
            finally:
                # Wait briefly, restore TTY cbreak & reader
                time.sleep(0.5)
                if sys.stdin.isatty():
                    tty.setcbreak(sys.stdin.fileno())
                    loop.add_reader(sys.stdin.fileno(), _input_reader_callback)
                status_bar_text_obj.plain = ""  # Clear status bar
                _refresh_footer_controls_text()  # Restore normal footer

        def _input_reader_callback() -> None:
            """Callback function for handling keypresses."""
            nonlocal current_session_wrap_state, is_display_paused_state
            nonlocal original_termios_settings, input_reader_active, loop  # original_termios_settings needed for restore in S/F
            nonlocal current_filter_regex_str_state, current_filter_compiled_regex_state
            nonlocal status_bar_text_obj, all_streamed_lines, live_display_content, live_display_max_lines  # Needed for S/F/Resume side effects

            try:
                char = sys.stdin.read(1)
                if not char:
                    return

                new_state, requested_action = process_keypress(
                    char,
                    WatchDisplayState(
                        wrap_text=current_session_wrap_state,
                        is_paused=is_display_paused_state,
                        filter_regex_str=current_filter_regex_str_state,
                        filter_compiled_regex=current_filter_compiled_regex_state,
                    ),
                )

                # Update state variables
                current_session_wrap_state = new_state.wrap_text
                is_display_paused_state = new_state.is_paused
                current_filter_regex_str_state = new_state.filter_regex_str
                current_filter_compiled_regex_state = new_state.filter_compiled_regex

                # Perform side effects based on action
                if requested_action == WatchKeypressAction.EXIT:
                    logger.debug("Exit action requested by keypress.")
                    loop.call_soon_threadsafe(exit_requested_event.set)

                elif (
                    requested_action == WatchKeypressAction.TOGGLE_PAUSE
                    and not is_display_paused_state
                ):
                    logger.debug(
                        "Display content update requested by keypress (Resume)."
                    )
                    live_display_content.no_wrap = (
                        not current_session_wrap_state
                    )  # Ensure wrap state is applied
                    filtered_lines_on_resume = _apply_filter_to_lines(
                        all_streamed_lines, current_filter_compiled_regex_state
                    )
                    latest_lines_to_display = filtered_lines_on_resume[
                        -live_display_max_lines:
                    ]
                    num_padding = max(
                        0, live_display_max_lines - len(latest_lines_to_display)
                    )
                    padded_display_lines = (
                        [" "] * num_padding
                    ) + latest_lines_to_display
                    live_display_content.plain = "\n".join(padded_display_lines)
                    _refresh_footer_controls_text()  # Update footer (shows 'running')

                elif requested_action in [
                    WatchKeypressAction.TOGGLE_WRAP,
                    WatchKeypressAction.TOGGLE_PAUSE,
                ]:
                    is_just_pause = (
                        requested_action == WatchKeypressAction.TOGGLE_PAUSE
                        and is_display_paused_state
                    )
                    is_just_wrap = requested_action == WatchKeypressAction.TOGGLE_WRAP
                    if is_just_pause or is_just_wrap:
                        logger.debug(
                            "Footer update requested by keypress (Pause/Wrap)."
                        )
                        live_display_content.no_wrap = (
                            not current_session_wrap_state
                        )  # Update wrap state display effect
                        _refresh_footer_controls_text()  # Update footer text

                elif requested_action == WatchKeypressAction.PROMPT_SAVE:
                    logger.debug("Save prompt requested by keypress.")
                    _handle_save_action()  # Call save helper

                elif requested_action == WatchKeypressAction.PROMPT_FILTER:
                    logger.debug("Filter prompt requested by keypress.")
                    _handle_filter_action()  # Call filter helper

            except Exception as e_callback:
                logger.debug(
                    f"Error in input reader callback: {e_callback}", exc_info=True
                )

        async def nested_stream_output(
            proc_to_stream: asyncio.subprocess.Process,
            text_content_to_update: Text,
            master_line_buffer: collections.deque[str],
            max_lines_for_disp: int,
        ) -> None:
            """Reads stdout/stderr from process, updates display and master buffer."""
            nonlocal error_message, total_lines_actually_streamed_counter
            nonlocal is_display_paused_state, live_display_content  # live_display_content for live.update

            pending_stream_tasks = set()

            async def _read_stream_line(
                stream: asyncio.StreamReader | None, stream_name: str
            ) -> bytes:
                if stream is None or stream.at_eof():
                    # logger.debug(f"Stream {stream_name} is None or at EOF before read.") # Too noisy
                    return b""
                try:
                    # logger.debug(f"Attempting readline from {stream_name}...") # Too noisy
                    line = await stream.readline()
                    # logger.debug(f"Read from {stream_name}: {line[:60]!r}...") # Too noisy
                    return line
                except Exception as e_read:
                    logger.error(
                        f"Exception reading from {stream_name}: {e_read}", exc_info=True
                    )
                    return b""

            if proc_to_stream.stdout:
                stdout_task = asyncio.create_task(
                    _read_stream_line(proc_to_stream.stdout, "stdout"),
                    name="stdout_reader_nested",
                )
                pending_stream_tasks.add(stdout_task)
            if proc_to_stream.stderr:
                stderr_task = asyncio.create_task(
                    _read_stream_line(proc_to_stream.stderr, "stderr"),
                    name="stderr_reader_nested",
                )
                pending_stream_tasks.add(stderr_task)

            if not pending_stream_tasks:
                logger.warning(
                    "Watch command (nested_stream) has no stdout/stderr stream initially."
                )
                return

            try:
                while pending_stream_tasks:
                    done_stream, pending_stream_tasks_after_wait = await asyncio.wait(
                        pending_stream_tasks, return_when=asyncio.FIRST_COMPLETED
                    )
                    pending_stream_tasks = (
                        pending_stream_tasks_after_wait  # Update the set
                    )

                    for task_done in done_stream:
                        task_name = task_done.get_name() or "unknown_stream_task"
                        try:
                            line_bytes = (
                                await task_done
                            )  # Handles exceptions from _read_stream_line

                            if not line_bytes:  # EOF or read error for this stream
                                # logger.debug(f"Stream {task_name} task returned no data (EOF/read error).") # Noisy
                                continue  # Don't re-add task for this stream if it's ended

                            line_str = line_bytes.decode(
                                "utf-8", errors="replace"
                            ).strip()
                            total_lines_actually_streamed_counter += 1
                            master_line_buffer.append(line_str)  # Add to central deque
                            accumulated_output_lines.append(
                                line_str
                            )  # Also to list for Vibe

                            if "stderr_reader_nested" in task_name:
                                logger.warning(f"Watch STDERR (nested): {line_str}")
                                if error_message is None:
                                    error_message = line_str  # Capture first error
                            elif "stdout_reader_nested" in task_name:
                                if not is_display_paused_state:
                                    filtered_lines = _apply_filter_to_lines(
                                        master_line_buffer,
                                        current_filter_compiled_regex_state,
                                    )
                                    actual_lines_for_disp = filtered_lines[
                                        -max_lines_for_disp:
                                    ]
                                    num_padding = max(
                                        0,
                                        max_lines_for_disp - len(actual_lines_for_disp),
                                    )
                                    padded_display_lines = (
                                        [" "] * num_padding
                                    ) + actual_lines_for_disp
                                    new_text_plain = "\n".join(padded_display_lines)
                                    text_content_to_update.plain = new_text_plain

                            # Re-add task to read next line if process is still running and stream has data
                            if (
                                proc_to_stream.returncode is None
                            ):  # Process still running
                                if (
                                    "stdout_reader_nested" in task_name
                                    and proc_to_stream.stdout
                                    and not proc_to_stream.stdout.at_eof()
                                ):
                                    new_stdout_task = asyncio.create_task(
                                        _read_stream_line(
                                            proc_to_stream.stdout, "stdout"
                                        ),
                                        name="stdout_reader_nested",
                                    )
                                    pending_stream_tasks.add(new_stdout_task)
                                elif (
                                    "stderr_reader_nested" in task_name
                                    and proc_to_stream.stderr
                                    and not proc_to_stream.stderr.at_eof()
                                ):
                                    new_stderr_task = asyncio.create_task(
                                        _read_stream_line(
                                            proc_to_stream.stderr, "stderr"
                                        ),
                                        name="stderr_reader_nested",
                                    )
                                    pending_stream_tasks.add(new_stderr_task)
                            # else: logger.debug(f"Process ended (rc={proc_to_stream.returncode}), not re-adding task for {task_name}.") # Noisy

                        except Exception as e_proc_stream_item:
                            logger.error(
                                f"Error processing item from {task_name} (nested): {e_proc_stream_item}",
                                exc_info=True,
                            )
                            if error_message is None:
                                error_message = (
                                    f"Stream error ({task_name}): {e_proc_stream_item}"
                                )

                    if (
                        not pending_stream_tasks
                        and proc_to_stream.returncode is not None
                    ):
                        # logger.debug("All stream tasks done and process has ended (nested_stream_output).") # Noisy
                        break  # Exit while loop

            except asyncio.CancelledError:
                logger.info("Output streaming task (nested) cancelled.")
            finally:
                # Ensure all pending stream tasks are cancelled on exit
                active_remaining = [t for t in pending_stream_tasks if not t.done()]
                if active_remaining:
                    for t_cancel in active_remaining:
                        t_cancel.cancel()
                    await asyncio.gather(*active_remaining, return_exceptions=True)
                # logger.debug("nested_stream_output finished.") # Noisy

        # ----- main_watch_task body starts here -----
        try:
            # Initialize state (wrap, pause, filter) - pause/filter start off
            current_session_wrap_state = live_display_wrap_text
            is_display_paused_state = False
            current_filter_regex_str_state = live_display_filter_regex
            current_filter_compiled_regex_state = None
            if current_filter_regex_str_state:
                try:
                    current_filter_compiled_regex_state = re.compile(
                        current_filter_regex_str_state
                    )
                except re.error as e:
                    logger.warning(f"Bad initial filter: {e}")
                    current_filter_regex_str_state = None

            live_display_content.no_wrap = (
                not current_session_wrap_state
            )  # Initial UI sync
            _refresh_footer_controls_text()  # Set initial footer

            if sys.stdin.isatty():
                try:
                    original_termios_settings = termios.tcgetattr(sys.stdin.fileno())
                    tty.setcbreak(sys.stdin.fileno())
                    loop.add_reader(sys.stdin.fileno(), _input_reader_callback)
                    input_reader_active = True
                    logger.debug("TTY set to cbreak mode and stdin reader added.")
                except Exception as e_tty_setup:
                    logger.warning(
                        f"Failed to set cbreak or add reader: {e_tty_setup}. Key controls disabled."
                    )

            # --- Restore Kubectl Process ---
            cmd_list_for_proc = [command, resource, *args]
            logger.info(
                f"Executing watch command: kubectl {' '.join(cmd_list_for_proc)}"
            )
            process = await create_async_kubectl_process(cmd_list_for_proc, config=cfg)
            logger.info(f"Watch command process started (PID: {process.pid}).")

            # --- Restore Task Creation ---
            stream_handler_task = asyncio.create_task(
                nested_stream_output(
                    process,
                    live_display_content,
                    all_streamed_lines,
                    live_display_max_lines,
                ),
                name="stream_handler_master",
            )
            active_monitor_tasks = []
            process_wait_task_local = asyncio.create_task(
                _wrapped_process_wait(process), name="k8s_process_wait_wrapper"
            )
            active_monitor_tasks.append(process_wait_task_local)

            if input_reader_active:  # Only monitor exit event if TTY input is active
                exit_monitor_task_local = asyncio.create_task(
                    _wrapped_event_wait(exit_requested_event),
                    name="user_exit_event_wait_wrapper",
                )
                active_monitor_tasks.append(exit_monitor_task_local)

            if not active_monitor_tasks:
                logger.error("No monitoring tasks started for watch operation.")
                return Error("Watch internal error: No monitoring tasks.")

            # --- Restore Wait Logic ---
            done_monitors, pending_monitors = await asyncio.wait(
                active_monitor_tasks, return_when=asyncio.FIRST_COMPLETED
            )

            # --- Restore Exit Reason Handling ---
            if exit_monitor_task_local and exit_monitor_task_local in done_monitors:
                logger.info("User requested exit via 'E' key.")
                raise asyncio.CancelledError(
                    "Watch cancelled by user via 'E' key"
                )  # Handled by _run_async_main

            # Process ended, wait for stream handler to finish
            if stream_handler_task and not stream_handler_task.done():
                logger.debug(
                    "Kubectl process ended, waiting for stream handler to flush..."
                )
                try:
                    async with asyncio.timeout(2.0):
                        await stream_handler_task
                    logger.debug("Stream handler flushed and completed.")
                except TimeoutError:
                    logger.warning("Timeout waiting for stream handler. Cancelling it.")
                    if not stream_handler_task.done():
                        stream_handler_task.cancel()
                        await asyncio.sleep(0)  # Allow cancellation
                except Exception as e_sh_wait:
                    logger.error(
                        f"Error waiting for stream handler: {e_sh_wait}", exc_info=True
                    )

            # --- Restore Final Status Determination ---
            run_error: Error | None = None
            if process.returncode is None:
                logger.warning("Kubectl process wait completed but returncode is None.")
                final_status = "Unknown (process)"
                if error_message is None:
                    error_message = "Kubectl process ended without a clear exit code."
                run_error = Error(error=error_message)
            elif process.returncode == 0:
                if error_message:  # stderr might have content even with rc=0
                    final_status = "Completed with warnings"
                    logger.info(
                        f"Watch command completed (rc=0) but stderr had content: {error_message}"
                    )
                else:
                    final_status = "Completed"
                    logger.info("Watch command completed successfully (rc=0).")
            else:  # Non-zero exit code
                final_status = f"Error (kubectl rc={process.returncode})"
                if error_message is None:
                    error_message = (
                        f"kubectl command failed with exit code {process.returncode}."
                    )
                logger.error(
                    f"Watch command kubectl error: {error_message} (rc={process.returncode})"
                )
                run_error = Error(error=error_message)

            if run_error:
                return run_error  # Return actual kubectl execution errors

            # If no direct run_error, it's a success path for the command execution itself
            return Success(
                data={
                    "status": final_status,
                    "message_from_stderr": error_message or "",
                    "input_reader_active": input_reader_active,
                }
            )

        except asyncio.CancelledError as e_cancel:
            logger.info(f"main_watch_task caught CancelledError: {e_cancel!s}")
            # final_status = "Cancelled by user" # Status is handled by _run_async_main return
            if error_message is None:
                error_message = (
                    str(e_cancel) if str(e_cancel) else "Operation cancelled by user."
                )
            raise e_cancel  # Re-raise; _run_async_main will format the Error object.

        except FileNotFoundError as e_fnf:  # Kubectl not found
            logger.error(f"Watch setup error (FileNotFound): {e_fnf}", exc_info=True)
            final_status = "Error (Setup)"
            error_message = str(e_fnf)
            return Error(error=error_message, exception=e_fnf)
        except Exception as e_unhandled:
            logger.error(
                f"Unhandled exception in main_watch_task: {e_unhandled}", exc_info=True
            )
            final_status = "Error (Internal)"
            error_message = str(e_unhandled)
            return Error(error=error_message, exception=e_unhandled)
        finally:
            logger.debug("Entering main_watch_task finally block.")
            # --- Restore Cleanup Logic ---
            if input_reader_active and sys.stdin.isatty():
                try:
                    loop.remove_reader(sys.stdin.fileno())
                    logger.debug("Stdin reader removed.")
                except Exception as e:
                    logger.warning(f"Failed to remove stdin reader: {e}")
                if original_termios_settings:
                    try:
                        termios.tcsetattr(
                            sys.stdin.fileno(),
                            termios.TCSADRAIN,
                            original_termios_settings,
                        )
                        logger.debug("TTY settings restored.")
                    except Exception as e:
                        logger.warning(f"Failed to restore TTY settings: {e}")

            tasks_to_clean = [
                t
                for t in [
                    stream_handler_task,
                    process_wait_task_local,
                    exit_monitor_task_local,
                ]
                if t and not t.done()
            ]
            if tasks_to_clean:
                # logger.debug(f"Cancelling {len(tasks_to_clean)} tasks in finally...") # Noisy
                for task_to_cancel in tasks_to_clean:
                    task_to_cancel.cancel()
                await asyncio.gather(*tasks_to_clean, return_exceptions=True)
                # logger.debug("Finished gathering cancelled tasks.") # Noisy

            if process and process.returncode is None:
                logger.debug(
                    f"Terminating kubectl process (PID: {process.pid}) in finally."
                )
                process.terminate()
                try:
                    async with asyncio.timeout(1.5):
                        await process.wait()
                    logger.debug(
                        f"Kubectl process terminated with rc={process.returncode}."
                    )
                except TimeoutError:
                    logger.warning(
                        f"Timeout terminating kubectl (PID: {process.pid}). Killing."
                    )
                    process.kill()
                    try:
                        async with asyncio.timeout(0.5):
                            await process.wait()
                    except Exception:  # Indent this except
                        logger.warning(
                            f"kubectl (PID: {process.pid}) did not exit cleanly after kill."
                        )
                except Exception as e:  # Indent this except
                    logger.error(f"Error during final process termination: {e}")
            # logger.debug("Exiting main_watch_task finally block.") # Noisy

    # --- Use the _run_async_main runner for the main_watch_task ---
    with Live(
        overall_layout,
        console=console_manager.console,
        refresh_per_second=10,
        transient=False,
        vertical_overflow="visible",
    ) as live_instance:
        # Restore call to _run_async_main
        loop_result = await _run_async_main(
            main_watch_task(),
            cancel_message="Watch cancelled by user (Ctrl+C)",
            error_message_prefix="Watch execution",
        )

        # --- Restore Post-Watch Processing ---
        elapsed_time = time.time() - start_time
        final_status = "Unknown"  # Default
        overall_operation_had_error = True  # Default

        if isinstance(loop_result, Error):
            if not error_message:
                error_message = loop_result.error
            final_status = "Error"
            if "cancelled by user" in (error_message or "").lower():
                final_status = "Cancelled by user"
                overall_operation_had_error = False  # User cancel is not a failure
        elif isinstance(loop_result, Success):
            final_status = (
                loop_result.data.get("status", "Completed")
                if loop_result.data
                else "Completed"
            )
            if loop_result.data and loop_result.data.get("message_from_stderr"):
                if not error_message:
                    error_message = loop_result.data.get("message_from_stderr", "")
            if "error" in final_status.lower():
                overall_operation_had_error = True
            else:
                overall_operation_had_error = False
        else:  # Should not happen
            logger.error(
                f"Unexpected result type from _run_async_main: {type(loop_result)}"
            )
            if not error_message:
                error_message = "Unknown internal error during watch."
            final_status = "Error (Internal)"

        status_bar_text_obj.plain = "Watch ended. Preparing summary..."
        live_instance.refresh()  # Explicit refresh might be needed here

        # --- Restore Summary Table Creation ---
        summary_table = _create_watch_summary_table(
            command_str=command_str,
            final_status=final_status,
            elapsed_time=elapsed_time,
            lines_streamed=total_lines_actually_streamed_counter,
            error_message=error_message,
            operation_had_error=overall_operation_had_error,
        )

        summary_layout = Group(
            Panel(
                summary_table,
                title="Watch Session Ended",
                border_style="green" if not overall_operation_had_error else "red",
            ),
            status_bar_text_obj,
            footer_controls_text_obj,
        )
        live_instance.update(summary_layout)  # Update display with summary

        # If Vibe is not shown (handled by caller), we just show a generic exit message.
        status_bar_text_obj.plain = (
            "Watch session concluded. Press any key to exit..."
        )
        live_instance.update(summary_layout) # Ensure summary is updated with this message

    # --- Final Result Return ---
    raw_output_str = "\n".join(accumulated_output_lines)

    if overall_operation_had_error:
        # Ensure error_message is populated for hard errors
        final_error_msg = error_message or f"Watch command failed ({final_status}). {total_lines_actually_streamed_counter} lines streamed."
        return Error(error=final_error_msg)
    else:
        success_msg = f"Watch session '{command_str}' {final_status.lower()[:200]}"
        if elapsed_time > 0.1:
            success_msg += f" after {elapsed_time:.1f}s."
        success_msg += f" {total_lines_actually_streamed_counter} lines streamed."
        if error_message and (
            "warning" in final_status.lower() or "cancel" in final_status.lower()
        ): # Append non-critical messages
            success_msg += f" Message: {error_message[:200]}"
        
        # For Success, data should be the raw output string for Vibe processing by the caller
        return Success(message=success_msg, data=raw_output_str)
