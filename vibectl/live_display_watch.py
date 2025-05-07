import asyncio
import collections  # specifically for deque
import functools
import logging
import re
import sys
import termios
import time
import tty
from dataclasses import dataclass
from enum import Enum, auto
from pathlib import Path
from typing import Callable, Iterable

from rich.console import Console, ConsoleOptions, Group, RenderResult
from rich.live import Live
from rich.panel import Panel
from rich.spinner import Spinner
from rich.table import Table
from rich.text import Text

from .config import Config
from .k8s_utils import create_async_kubectl_process
from .live_display import _run_async_main
from .types import Error, OutputFlags, Result, Success
from .utils import console_manager

logger = logging.getLogger(__name__)


# --- Custom Rich Renderable for Live Status Bar ---
class LiveStatusDisplay:
    def __init__(
        self,
        start_time: float,
        get_current_lines_func: Callable[[], int],
        spinner: Spinner,
        text_obj: Text,
    ):
        self.start_time = start_time
        self.get_current_lines_func = get_current_lines_func
        self.spinner = spinner
        self.text_obj = text_obj
        self._last_lines_streamed = (
            -1
        )  # To help with conditional refresh if needed, though Rich handles it
        self._last_elapsed_str = ""

    def __rich_console__(
        self, console: Console, options: ConsoleOptions
    ) -> RenderResult:
        elapsed_seconds = time.time() - self.start_time
        # Format to 1 decimal place, but ensure it updates even if only milliseconds change
        elapsed_str = f"{elapsed_seconds:.1f}s"
        lines_streamed = self.get_current_lines_func()

        # Update text object only if content changed to avoid unnecessary re-rendering triggers if Rich doesn\'t diff
        current_text = f"{elapsed_str} | {lines_streamed} lines"
        if self.text_obj.plain != current_text:
            self.text_obj.plain = current_text

        yield self.spinner
        yield Text(" ", style="dim")  # For spacing
        yield self.text_obj


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
    elif char_lower == "f":
        action = WatchKeypressAction.PROMPT_FILTER

    # Return the (potentially updated) state and the determined action
    return new_state, action


# Add New Enums and Dataclass here
class WatchOutcome(Enum):
    SUCCESS = auto()
    ERROR = auto()
    CANCELLED = auto()


class WatchReason(Enum):
    PROCESS_EXIT_0 = auto()  # Kubectl exited normally with code 0
    PROCESS_EXIT_NONZERO = auto()  # Kubectl exited with non-zero code
    USER_EXIT_KEY = auto()  # User pressed 'E' key
    CTRL_C = auto()  # User pressed Ctrl+C
    STREAM_ERROR = auto()  # Error reading stdout/stderr
    SETUP_ERROR = auto()  # Error before process started (e.g., file not found)
    INTERNAL_ERROR = auto()  # Unexpected exception within the task


@dataclass
class WatchStatusInfo:
    outcome: WatchOutcome
    reason: WatchReason
    detail: str | None = None  # e.g., Stderr message, cancellation reason
    exit_code: int | None = None  # Kubectl exit code if applicable


def _create_watch_summary_table(
    command_str: str,
    status_info: WatchStatusInfo,
    elapsed_time: float,
    lines_streamed: int,
) -> Table:
    """Creates the summary table for a watch session using structured status."""
    summary_table = Table(
        title="Watch Session Summary",
        title_style="bold cyan",
        show_header=True,
        header_style="bold magenta",
    )
    summary_table.add_column("Parameter", style="dim")
    summary_table.add_column("Value")

    # Determine display status string and style based on outcome/reason
    status_text = f"{status_info.outcome.name.capitalize()}"
    if status_info.reason != WatchReason.PROCESS_EXIT_0:
        # Replace underscores with spaces for readability
        status_text += f" ({status_info.reason.name.replace('_', ' ')})"
    if status_info.exit_code is not None:
        status_text += f" (rc={status_info.exit_code})"

    status_style = "green"
    if status_info.outcome == WatchOutcome.ERROR:
        status_style = "red"
    elif status_info.outcome == WatchOutcome.CANCELLED:
        status_style = "yellow"
    elif status_info.reason != WatchReason.PROCESS_EXIT_0:  # Success but with stderr
        status_style = "yellow"

    summary_table.add_row("Command", f"`kubectl {command_str}`")
    summary_table.add_row("Status", Text(status_text, style=status_style))
    summary_table.add_row("Duration", f"{elapsed_time:.2f} seconds")
    summary_table.add_row("Lines Streamed", str(lines_streamed))

    # Add detail message if present
    if status_info.detail:
        message_style = "yellow"  # Default for cancellation/warnings
        if status_info.outcome == WatchOutcome.ERROR:
            message_style = "red"
        summary_table.add_row("Message", Text(status_info.detail, style=message_style))

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


def _apply_filter_to_lines(
    lines_to_filter: collections.deque[str] | list[str],
    compiled_filter_regex: re.Pattern | None,
) -> list[str]:
    """Filters a list or deque of lines based on a compiled regex."""
    if not compiled_filter_regex:
        return list(lines_to_filter)
    return [line for line in lines_to_filter if compiled_filter_regex.search(line)]


def _refresh_footer_controls_text(
    footer_controls_text_obj: Text, current_display_state: WatchDisplayState
) -> None:
    """Updates the footer text object based on the current display state."""
    wrap_status = "on" if current_display_state.wrap_text else "off"
    pause_status = "paused" if current_display_state.is_paused else "running"
    filter_status = (
        f"'{current_display_state.filter_regex_str}'"
        if current_display_state.filter_regex_str
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


async def _process_stream_output(
    process: asyncio.subprocess.Process,
    text_content_to_update: Text,
    master_line_buffer: collections.deque[str],
    accumulated_output_lines: list[str],
    max_lines_for_disp: int,
    get_is_showing_temporary_message_func: Callable[[], bool],
    get_current_display_state_func: Callable[[], WatchDisplayState],
    shared_line_counter_ref: list[int],
) -> tuple[str | None, int]:
    """Reads stdout/stderr from process, updates display and master buffer."""
    captured_stderr: str | None = None
    lines_read_count = 0
    pending_stream_tasks = set()

    async def _read_stream_line(
        stream: asyncio.StreamReader | None, stream_name: str
    ) -> bytes:
        if stream is None or stream.at_eof():
            return b""
        try:
            line = await stream.readline()
            logger.debug(f"_read_stream_line ({stream_name}): read {len(line)} bytes: {line[:100]!r}")
            return line
        except Exception as e_read:
            # Log error but return empty bytes, let main loop handle stream ending
            logger.error(
                f"Exception reading from {stream_name}: {e_read}", exc_info=True
            )
            return b""

    if process.stdout:
        stdout_task = asyncio.create_task(
            _read_stream_line(process.stdout, "stdout"),
            name="stdout_reader_stream_proc",
        )
        pending_stream_tasks.add(stdout_task)
    if process.stderr:
        stderr_task = asyncio.create_task(
            _read_stream_line(process.stderr, "stderr"),
            name="stderr_reader_stream_proc",
        )
        pending_stream_tasks.add(stderr_task)

    if not pending_stream_tasks:
        logger.warning(
            "Watch command (_process_stream) has no stdout/stderr initially."
        )
        return None, 0  # No streams, no lines read

    try:
        while pending_stream_tasks:
            done_stream, pending_stream_tasks_after_wait = await asyncio.wait(
                pending_stream_tasks, return_when=asyncio.FIRST_COMPLETED
            )
            pending_stream_tasks = pending_stream_tasks_after_wait

            for task_done in done_stream:
                task_name = task_done.get_name() or "unknown_stream_task"
                try:
                    line_bytes = await task_done

                    if not line_bytes:
                        continue

                    line_str = line_bytes.decode("utf-8", errors="replace").strip()
                    lines_read_count += 1
                    shared_line_counter_ref[0] += 1
                    master_line_buffer.append(line_str)  # Add to central deque
                    accumulated_output_lines.append(line_str)  # Also to list for Vibe

                    if "stderr_reader_stream_proc" in task_name:
                        logger.warning(f"Watch STDERR: {line_str}")
                        if captured_stderr is None:
                            captured_stderr = line_str  # Capture first error
                    elif "stdout_reader_stream_proc" in task_name:
                        current_state = get_current_display_state_func()
                        if not current_state.is_paused:
                            filtered_lines = _apply_filter_to_lines(
                                master_line_buffer,
                                current_state.filter_compiled_regex,
                            )
                            actual_lines_for_disp = filtered_lines[-max_lines_for_disp:]
                            new_text_plain = "\n".join(actual_lines_for_disp)
                            text_content_to_update.plain = new_text_plain

                    # Stats are updated by LiveStatusDisplay via Rich's refresh cycle

                    # Log conditions before deciding to re-add task
                    if process.stdout:
                        logger.debug(f"Re-add check (task: {task_name}): stdout EOF? {process.stdout.at_eof()}, pending: {len(pending_stream_tasks)}, rc: {process.returncode}")
                    else:
                        logger.debug(f"Re-add check (task: {task_name}): stdout is None, pending: {len(pending_stream_tasks)}, rc: {process.returncode}")

                    # Re-add task to read next line if process is still running
                    if process.returncode is None:
                        if (
                            "stdout_reader_stream_proc" in task_name # Check specific task
                            and process.stdout
                            and not process.stdout.at_eof()
                        ):
                            new_stdout_task = asyncio.create_task(
                                _read_stream_line(process.stdout, "stdout"),
                                name="stdout_reader_stream_proc",
                            )
                            pending_stream_tasks.add(new_stdout_task)
                        elif (
                            "stderr_reader_stream_proc" in task_name # Check specific task
                            and process.stderr
                            and not process.stderr.at_eof()
                        ):
                            new_stderr_task = asyncio.create_task(
                                _read_stream_line(process.stderr, "stderr"),
                                name="stderr_reader_stream_proc",
                            )
                            pending_stream_tasks.add(new_stderr_task)

                except Exception as e_proc_stream_item:
                    logger.error(
                        f"Error processing item from {task_name}: {e_proc_stream_item}",
                        exc_info=True,
                    )
                    if captured_stderr is None:
                        captured_stderr = (
                            f"Stream error ({task_name}): {e_proc_stream_item}"
                        )

            if not pending_stream_tasks and process.returncode is not None:
                break

    except asyncio.CancelledError:
        logger.info("Stream processing task cancelled.")
        # Set a specific detail if cancelled
        if captured_stderr is None:
            captured_stderr = "Stream processing cancelled."
    finally:
        active_remaining = [t for t in pending_stream_tasks if not t.done()]
        if active_remaining:
            for t_cancel in active_remaining:
                t_cancel.cancel()
            await asyncio.gather(*active_remaining, return_exceptions=True)

    return captured_stderr, lines_read_count


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
    start_time_session = time.time()
    cfg = Config()
    live_display_max_lines = cfg.get("live_display_max_lines")
    live_display_wrap_text = cfg.get("live_display_wrap_text")
    live_display_save_dir = cfg.get("live_display_save_dir")
    live_display_filter_regex = cfg.get("live_display_default_filter_regex")
    stream_buffer_max_lines = cfg.get("live_display_stream_buffer_max_lines", 10000)

    command_str = f"{command} {resource} {' '.join(args)}"
    vibe_output: dict | None = None
    accumulated_output_lines: list[str] = []
    error_message: str | None = None

    live_display_content = Text("", no_wrap=not live_display_wrap_text)
    loop = asyncio.get_running_loop()

    # --- Centralized Display State (Initialized before Live starts) ---
    initial_filter_compiled: re.Pattern | None = None
    if live_display_filter_regex:
        try:
            initial_filter_compiled = re.compile(live_display_filter_regex)
        except re.error as e_init_re:
            logger.warning(
                "Invalid initial filter regex from config "
                f"'{live_display_filter_regex}': {e_init_re}"
            )

    # Initialize the state object in the outer scope
    current_display_state_obj = WatchDisplayState(
        wrap_text=live_display_wrap_text,
        is_paused=False,
        filter_regex_str=live_display_filter_regex if initial_filter_compiled else None,
        filter_compiled_regex=initial_filter_compiled,
    )

    all_streamed_lines: collections.deque[str] = collections.deque(
        maxlen=stream_buffer_max_lines
    )
    total_lines_actually_streamed_counter = 0

    footer_controls_text_obj = Text("", style="dim")
    live_stats_spinner_obj = Spinner("dots", style="dim", speed=1.5)
    live_stats_text_obj = Text("", style="dim")
    live_status_bar_renderable = Group(live_stats_spinner_obj, " ", live_stats_text_obj)

    temporary_status_message_text_obj = Text("", style="dim i")

    # Initialize with a temporary message for "Initializing..."
    temporary_status_message_text_obj.plain = "Initializing..."
    status_bar_content_holder = Panel(
        temporary_status_message_text_obj, border_style="none", padding=0
    )

    overall_layout = Group(
        Panel(
            live_display_content,
            title=display_text,
            border_style="blue",
            height=live_display_max_lines + 2,
        ),
        status_bar_content_holder,
        footer_controls_text_obj,
    )

    # --- Set initial footer text BEFORE starting Live ---
    _refresh_footer_controls_text(footer_controls_text_obj, current_display_state_obj)

    save_dir = Path(live_display_save_dir).expanduser()
    try:
        save_dir.mkdir(parents=True, exist_ok=True)
    except OSError as e:
        logger.error(f"Could not create save directory {save_dir}: {e}")

    # --- Nested Helper Functions ---
    async def main_watch_task(live_instance_ref: Live) -> Result:
        """Runs watch command, streams output, and handles user interactions."""
        nonlocal error_message, vibe_output, accumulated_output_lines, save_dir
        nonlocal footer_controls_text_obj, live_display_content, all_streamed_lines
        nonlocal loop
        nonlocal current_display_state_obj
        nonlocal start_time_session
        nonlocal live_stats_spinner_obj, live_stats_text_obj
        nonlocal temporary_status_message_text_obj, status_bar_content_holder

        is_showing_temporary_message: bool = False
        shared_line_counter = [0]

        live_status_renderable = LiveStatusDisplay(
            start_time_session,
            lambda: shared_line_counter[0],
            live_stats_spinner_obj,
            live_stats_text_obj,
        )

        original_termios_settings = None
        input_reader_active = False
        exit_requested_event = asyncio.Event()
        process: asyncio.subprocess.Process | None = None
        stream_handler_task: asyncio.Task | None = None
        process_wait_task_local: asyncio.Task | None = None
        exit_monitor_task_local: asyncio.Task | None = None

        def _input_reader_callback(max_lines: int) -> None:
            nonlocal original_termios_settings, input_reader_active, loop
            nonlocal all_streamed_lines, live_display_content
            nonlocal current_display_state_obj
            nonlocal is_showing_temporary_message
            
            try:
                # Handle temporary message dismissal first
                if is_showing_temporary_message:
                    _revert_to_live_status()
                    try: 
                        sys.stdin.read(1) # Consume the keypress
                    except Exception as e_read_dismiss_key:
                         logger.warning(f"Could not read dismissal key: {e_read_dismiss_key}")
                    return

                char = sys.stdin.read(1)
                if not char:
                    return

                new_state_from_keypress, requested_action = process_keypress(
                    char,
                    current_display_state_obj,
                )
                current_display_state_obj = new_state_from_keypress

                if requested_action == WatchKeypressAction.EXIT:
                    logger.debug("Exit action requested by keypress.")
                    loop.call_soon_threadsafe(exit_requested_event.set)
                elif (
                    requested_action == WatchKeypressAction.TOGGLE_PAUSE
                    and not current_display_state_obj.is_paused
                ):
                    live_display_content.no_wrap = (
                        not current_display_state_obj.wrap_text
                    )
                    filtered_lines_on_resume = _apply_filter_to_lines(
                        all_streamed_lines,
                        current_display_state_obj.filter_compiled_regex,
                    )
                    latest_lines_to_display = filtered_lines_on_resume[-max_lines:]
                    live_display_content.plain = "\n".join(latest_lines_to_display)
                    _refresh_footer_controls_text(
                        footer_controls_text_obj, current_display_state_obj
                    )
                elif requested_action in [
                    WatchKeypressAction.TOGGLE_WRAP,
                    WatchKeypressAction.TOGGLE_PAUSE,
                ]:
                    is_just_pause = (
                        requested_action == WatchKeypressAction.TOGGLE_PAUSE
                        and current_display_state_obj.is_paused
                    )
                    is_just_wrap = requested_action == WatchKeypressAction.TOGGLE_WRAP
                    if is_just_pause or is_just_wrap:
                        live_display_content.no_wrap = (
                            not current_display_state_obj.wrap_text
                        )
                        _refresh_footer_controls_text(
                            footer_controls_text_obj, current_display_state_obj
                        )
                elif requested_action == WatchKeypressAction.PROMPT_SAVE:
                    _handle_save_action()
                elif requested_action == WatchKeypressAction.PROMPT_FILTER:
                    _handle_filter_action(max_lines=max_lines)
            except Exception as e_callback:
                logger.debug(f"Error in callback: {e_callback}", exc_info=True)

        reader_callback_with_args = functools.partial(
            _input_reader_callback, max_lines=live_display_max_lines
        )

        async def _wrapped_process_wait(proc: asyncio.subprocess.Process) -> None:
            if proc:
                await proc.wait()

        async def _wrapped_event_wait(event: asyncio.Event) -> None:
            if event:
                await event.wait()

        def _handle_save_action() -> None:
            nonlocal original_termios_settings, input_reader_active, loop, resource
            nonlocal save_dir, all_streamed_lines
            nonlocal current_display_state_obj, is_showing_temporary_message
            nonlocal live_instance_ref

            if not sys.stdin.isatty():
                _set_temporary_status_message("Save failed: No TTY.", True)
                logger.warning("Save action ignored: Not running in a TTY.")
                _refresh_footer_controls_text(
                    footer_controls_text_obj, current_display_state_obj
                )
                return

            live_instance_ref.stop()
            if input_reader_active:
                loop.remove_reader(sys.stdin.fileno())
            if original_termios_settings:
                termios.tcsetattr(
                    sys.stdin.fileno(), termios.TCSADRAIN, original_termios_settings
                )

            filename_suggestion = f"vibectl_watch_{resource.replace('/', '_')}_{time.strftime('%Y%m%d_%H%M%S')}.log"
            prompt_text = f"Enter filename to save output (in {save_dir}) [Default: {filename_suggestion}]: "

            error_msg_save: str | None = None
            try:
                user_input = input(prompt_text).strip()
                saved_path = _perform_save_to_file(
                    save_dir=save_dir,
                    filename_suggestion=filename_suggestion,
                    user_provided_filename=user_input or None,
                    all_lines=all_streamed_lines,
                    filter_re=current_display_state_obj.filter_compiled_regex,
                )
                _set_temporary_status_message(f"Saved to {saved_path}.", True)
            except OSError as e:
                error_msg_save = f"Save failed: {e}"
                _set_temporary_status_message(error_msg_save, True)
            except (EOFError, KeyboardInterrupt) as e:
                error_msg_save = f"Save cancelled: {e}"
                _set_temporary_status_message(error_msg_save, True)
            finally:
                _restore_tty_and_reader()
                live_instance_ref.start(refresh=True)

        def _restore_tty_and_reader() -> None:
            nonlocal original_termios_settings, input_reader_active, loop
            if sys.stdin.isatty():
                if original_termios_settings:
                    try:
                        tty.setcbreak(sys.stdin.fileno())
                        if input_reader_active:
                            loop.add_reader(
                                sys.stdin.fileno(), reader_callback_with_args
                            )
                    except Exception as e_restore:
                        logger.warning(f"TTY restore failed: {e_restore}")
                _refresh_footer_controls_text(
                    footer_controls_text_obj, current_display_state_obj
                )

        def _handle_filter_action(max_lines: int) -> None:
            nonlocal original_termios_settings, input_reader_active, loop
            nonlocal all_streamed_lines, live_display_content
            nonlocal current_display_state_obj, is_showing_temporary_message
            nonlocal live_instance_ref

            if not sys.stdin.isatty():
                _set_temporary_status_message("Filter failed: No TTY.", True)
                logger.warning("Filter action ignored: Not running in a TTY.")
                _refresh_footer_controls_text(
                    footer_controls_text_obj, current_display_state_obj
                )
                return

            live_instance_ref.stop()
            if input_reader_active:
                loop.remove_reader(sys.stdin.fileno())
            if original_termios_settings:
                termios.tcsetattr(
                    sys.stdin.fileno(), termios.TCSADRAIN, original_termios_settings
                )

            current_filter_display = (
                f" (current: '{current_display_state_obj.filter_regex_str}')"
                if current_display_state_obj.filter_regex_str
                else " (off)"
            )
            prompt_text = (
                f"Enter filter regex (empty to clear){current_filter_display}: "
            )

            new_filter_str: str | None = None
            new_filter_re: re.Pattern | None = None
            filter_update_status = "Filter cleared."
            error_during_input = False
            try:
                user_input = input(prompt_text).strip()
                if user_input:
                    try:
                        new_filter_re = re.compile(user_input)
                        new_filter_str = user_input
                        filter_update_status = f"Filter set to '{new_filter_str}'."
                    except re.error as e_re:
                        filter_update_status = (
                            f"Invalid regex: {e_re}. Filter unchanged."
                        )
                else:
                    new_filter_str, new_filter_re = None, None

                if not (
                    user_input and not new_filter_re and new_filter_str is not None
                ):
                    current_display_state_obj = WatchDisplayState(
                        current_display_state_obj.wrap_text,
                        current_display_state_obj.is_paused,
                        new_filter_str,
                        new_filter_re,
                    )

                filtered_lines = _apply_filter_to_lines(
                    all_streamed_lines, current_display_state_obj.filter_compiled_regex
                )
                latest_lines_to_display = filtered_lines[-max_lines:]
                live_display_content.plain = "\n".join(latest_lines_to_display)
                _set_temporary_status_message(filter_update_status, True)

            except (EOFError, KeyboardInterrupt) as e:
                error_during_input = True
                _set_temporary_status_message(f"Filter input cancelled: {e}", True)
            finally:
                _restore_tty_and_reader()
                live_instance_ref.start(refresh=True)

        def _set_temporary_status_message(
            message: str, require_keypress: bool = True
        ) -> None:
            nonlocal temporary_status_message_text_obj, status_bar_content_holder
            nonlocal is_showing_temporary_message

            msg_to_display = message
            if require_keypress:
                msg_to_display += " Press any key to continue..."
            temporary_status_message_text_obj.plain = msg_to_display
            status_bar_content_holder.renderable = temporary_status_message_text_obj
            if require_keypress:
                is_showing_temporary_message = True

        def _revert_to_live_status() -> None:
            nonlocal status_bar_content_holder, live_status_renderable
            nonlocal is_showing_temporary_message
            status_bar_content_holder.renderable = live_status_renderable
            is_showing_temporary_message = False

        # ----- main_watch_task body starts here -----
        try:
            live_display_content.no_wrap = not current_display_state_obj.wrap_text
            if sys.stdin.isatty():
                try:
                    original_termios_settings = termios.tcgetattr(sys.stdin.fileno())
                    tty.setcbreak(sys.stdin.fileno())
                    loop.add_reader(sys.stdin.fileno(), reader_callback_with_args)
                    input_reader_active = True
                except Exception as e_tty_setup:
                    logger.warning(f"TTY/Reader setup failed: {e_tty_setup}")

            _revert_to_live_status()

            cmd_list_for_proc = [command, resource, *args]
            process = await create_async_kubectl_process(cmd_list_for_proc, config=cfg)

            stream_handler_task = asyncio.create_task(
                _process_stream_output(
                    process,
                    live_display_content,
                    all_streamed_lines,
                    accumulated_output_lines,
                    live_display_max_lines,
                    lambda: is_showing_temporary_message,
                    lambda: current_display_state_obj,
                    shared_line_counter,
                ),
                name="stream_handler_master",
            )

            active_monitor_tasks = []
            process_wait_task_local = asyncio.create_task(
                _wrapped_process_wait(process), name="k8s_proc_wait"
            )
            active_monitor_tasks.append(process_wait_task_local)
            if input_reader_active:
                exit_monitor_task_local = asyncio.create_task(
                    _wrapped_event_wait(exit_requested_event), name="user_exit_wait"
                )
                active_monitor_tasks.append(exit_monitor_task_local)

            if not active_monitor_tasks:
                return Error(error="Watch internal error: No monitoring tasks.")

            done_monitors, _ = await asyncio.wait(
                active_monitor_tasks, return_when=asyncio.FIRST_COMPLETED
            )

            if exit_monitor_task_local and exit_monitor_task_local in done_monitors:
                raise asyncio.CancelledError("Watch cancelled by user via 'E' key")

            stream_stderr: str | None = None
            stream_lines_read_this_run: int = 0
            if stream_handler_task:
                if not stream_handler_task.done():
                    try:
                        async with asyncio.timeout(2.0):
                            (
                                stream_stderr,
                                stream_lines_read_this_run,
                            ) = await stream_handler_task
                    except TimeoutError:
                        if not stream_handler_task.done():
                            stream_handler_task.cancel()
                        if error_message is None:
                            error_message = "Stream handler timeout."
                    except Exception as e_sh_wait:
                        if error_message is None:
                            error_message = f"Stream handler error: {e_sh_wait}"
                elif stream_handler_task.done():
                    try:
                        stream_stderr, stream_lines_read_this_run = (
                            stream_handler_task.result()
                        )
                    except Exception as e_sh_res:
                        if error_message is None:
                            error_message = f"Stream result error: {e_sh_res}"

            if stream_stderr and error_message is None:
                error_message = stream_stderr

            final_outcome = WatchOutcome.SUCCESS
            final_reason = WatchReason.PROCESS_EXIT_0
            final_detail = error_message
            final_exit_code = process.returncode if process else None

            if process is None:
                final_outcome, final_reason, final_detail = (
                    WatchOutcome.ERROR,
                    WatchReason.SETUP_ERROR,
                    final_detail or "Process not started.",
                )
            elif process.returncode is None:
                final_outcome, final_reason, final_detail = (
                    WatchOutcome.ERROR,
                    WatchReason.INTERNAL_ERROR,
                    final_detail or "Process ended without exit code.",
                )
            elif process.returncode != 0:
                final_outcome, final_reason = (
                    WatchOutcome.ERROR,
                    WatchReason.PROCESS_EXIT_NONZERO,
                )
                if final_detail is None:
                    final_detail = f"kubectl failed (rc={process.returncode})."

            current_status_info = WatchStatusInfo(
                final_outcome, final_reason, final_detail, final_exit_code
            )
            if final_outcome == WatchOutcome.ERROR:
                return Error(error=current_status_info.detail or "Unknown watch error.")
            return Success(data=current_status_info)

        except asyncio.CancelledError as e_cancel:
            detail = str(e_cancel) if str(e_cancel) else "Operation cancelled."
            # Determine reason based on detail
            reason_cancel = WatchReason.CTRL_C
            if "via 'E' key" in detail:  # Note: single quotes 'E'
                reason_cancel = WatchReason.USER_EXIT_KEY

            # Ensure status is updated before returning Error for cancellation
            # No, _run_async_main will create the WatchStatusInfo for cancellation
            return Error(error=detail)  # _run_async_main will wrap this
        except FileNotFoundError as e_fnf:
            return Error(error=str(e_fnf))  # _run_async_main will wrap this
        except Exception as e_unhandled:
            logger.error(f"Unhandled in main_watch_task: {e_unhandled}", exc_info=True)
            return Error(error=str(e_unhandled))  # _run_async_main will wrap this
        finally:
            if input_reader_active and sys.stdin.isatty() and original_termios_settings:
                try:
                    loop.remove_reader(sys.stdin.fileno())
                except:
                    pass
                try:
                    termios.tcsetattr(
                        sys.stdin.fileno(), termios.TCSADRAIN, original_termios_settings
                    )
                except:
                    pass

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
                for task_to_cancel in tasks_to_clean:
                    task_to_cancel.cancel()
                await asyncio.gather(*tasks_to_clean, return_exceptions=True)

            if process and process.returncode is None:
                process.terminate()
                try:
                    async with asyncio.timeout(1.0):
                        await process.wait()  # Shorter timeout
                except Exception:
                    process.kill()
                    try:
                        async with asyncio.timeout(0.5):
                            await process.wait()
                    except Exception:
                        pass  # Best effort kill

    # --- Use the _run_async_main runner for the main_watch_task ---
    with Live(
        overall_layout,
        console=console_manager.console,
        refresh_per_second=10,  # For continuous time update
        transient=False,  # Keep final summary
        vertical_overflow="visible",
    ) as live_instance:  # live_instance is now available
        # Pass live_instance to main_watch_task
        loop_result = await _run_async_main(
            main_watch_task(live_instance),  # Pass it here
            cancel_message="Watch cancelled by user (Ctrl+C)",  # For _run_async_main's own handling
            error_message_prefix="Watch execution",
        )

        # total_lines_actually_streamed_counter for the summary needs to be obtained
        # from the shared_line_counter if main_watch_task completed successfully
        # or based on accumulated_output_lines if it errored early.
        # For now, main_watch_task returns WatchStatusInfo which doesn't have the line count.
        # The accumulated_output_lines is still the most reliable source for final count.
        # Let's assume shared_line_counter was correctly updated if loop_result is Success.

        # The line count for summary should come from the shared counter if possible,
        # or fallback to len(accumulated_output_lines)
        # This is tricky because shared_line_counter is inside main_watch_task.
        # The easiest is to rely on len(accumulated_output_lines) for the final summary table,
        # as it's always populated. LiveStatusDisplay handles the live count.

        final_lines_for_summary = len(accumulated_output_lines)

        elapsed_time = time.time() - start_time_session
        final_status_info: WatchStatusInfo

        if isinstance(loop_result, Error):
            error_detail_str = loop_result.error or "Unknown Error"
            reason = WatchReason.INTERNAL_ERROR
            outcome = WatchOutcome.ERROR
            exit_code_parsed = None

            if "cancelled by user (ctrl+c)" in error_detail_str.lower():
                reason, outcome = WatchReason.CTRL_C, WatchOutcome.CANCELLED
            elif (
                "Watch cancelled by user via 'E' key" in error_detail_str
            ):  # This is from main_watch_task directly
                reason, outcome = WatchReason.USER_EXIT_KEY, WatchOutcome.CANCELLED
            elif isinstance(loop_result.exception, FileNotFoundError):
                reason = WatchReason.SETUP_ERROR
            # Add more detailed parsing if needed, e.g., from kubectl exit codes in error_detail_str

            final_status_info = WatchStatusInfo(
                outcome, reason, error_detail_str, exit_code_parsed
            )
            if error_message is None:
                error_message = error_detail_str  # Ensure overall error_message is set

        elif isinstance(loop_result, Success) and isinstance(
            loop_result.data, WatchStatusInfo
        ):
            final_status_info = loop_result.data
            if (
                final_status_info.detail and error_message is None
            ):  # If success had a detail (e.g. stderr)
                error_message = final_status_info.detail
        else:  # Should not happen
            final_status_info = WatchStatusInfo(
                WatchOutcome.ERROR,
                WatchReason.INTERNAL_ERROR,
                "Unknown internal error.",
            )
            if error_message is None:
                error_message = final_status_info.detail

        overall_operation_had_error = final_status_info.outcome == WatchOutcome.ERROR

        temporary_status_message_text_obj.plain = "Watch ended. Preparing summary..."
        status_bar_content_holder.renderable = temporary_status_message_text_obj
        live_instance.refresh()

        summary_table = _create_watch_summary_table(
            command_str=command_str,
            status_info=final_status_info,
            elapsed_time=elapsed_time,
            lines_streamed=final_lines_for_summary,  # Use len(accumulated_output_lines)
        )

        summary_layout = Group(
            Panel(
                summary_table,
                title="Watch Session Ended",
                border_style="green" if not overall_operation_had_error else "red",
            ),
            status_bar_content_holder,  # Shows "Watch ended..."
            footer_controls_text_obj,
        )
        live_instance.update(summary_layout)
        # No "Press any key to exit..." needed here, transient=False keeps it.

    raw_output_str = "\n".join(accumulated_output_lines)
    if overall_operation_had_error:
        final_error_msg_report = final_status_info.detail or "Watch command failed."
        return Error(error=final_error_msg_report)
    else:
        success_msg_parts = [
            f"Watch session '{command_str}' {final_status_info.outcome.name.lower()}"
        ]
        if final_status_info.reason not in [
            WatchReason.PROCESS_EXIT_0,
            WatchReason.USER_EXIT_KEY,
            WatchReason.CTRL_C,
        ]:
            success_msg_parts.append(
                f"({final_status_info.reason.name.replace('_', ' ')})"
            )
        elif final_status_info.reason in [
            WatchReason.USER_EXIT_KEY,
            WatchReason.CTRL_C,
        ]:
            success_msg_parts.append(
                f"({final_status_info.reason.name.replace('_', ' ').lower()})"
            )

        if elapsed_time > 0.1:
            success_msg_parts.append(f"after {elapsed_time:.1f}s.")
        success_msg_parts.append(f"{final_lines_for_summary} lines streamed.")
        if final_status_info.detail and final_status_info.outcome != WatchOutcome.ERROR:
            success_msg_parts.append(f"Message: {final_status_info.detail[:100]}")

        return Success(message=" ".join(success_msg_parts), data=raw_output_str)
