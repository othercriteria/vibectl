import asyncio
import collections  # specifically for deque
import contextlib
import functools
import logging
import re
import sys
import termios
import time
import tty
from collections.abc import Callable
from dataclasses import dataclass
from enum import Enum, auto
from pathlib import Path

from rich.columns import Columns
from rich.console import Console, ConsoleOptions, Group, RenderResult
from rich.live import Live
from rich.panel import Panel
from rich.spinner import Spinner
from rich.table import Table
from rich.text import Text

from .config import Config
from .k8s_utils import create_async_kubectl_process
from .live_display import _run_async_main

# Import type hint from types.py
from .types import Error, OutputFlags, Result, Success, SummaryPromptFragmentFunc
from .utils import console_manager

logger = logging.getLogger(__name__)


# ustom Renderable to Manage Status Bar Content
class StatusBarManager:
    def __init__(
        self,
        start_time: float,
        get_current_lines_func: Callable[[], int],
        spinner: Spinner,
        live_stats_text_obj: Text,
        temporary_message_text_obj: Text,
        get_show_temporary_message_func: Callable[[], bool],
        footer_controls_text_obj: Text,
        get_input_mode_state_func: Callable[
            [], tuple[bool, str, str]
        ],  # New: (is_active, prompt, buffer)
    ):
        self.start_time = start_time
        self.get_current_lines_func = get_current_lines_func
        self.spinner = spinner
        self.live_stats_text_obj = live_stats_text_obj
        self.temp_message = temporary_message_text_obj
        self.get_show_temp_func = get_show_temporary_message_func
        self.footer_controls = footer_controls_text_obj
        self.get_input_mode_state = get_input_mode_state_func

    def __rich_console__(
        self, console: Console, options: ConsoleOptions
    ) -> RenderResult:
        show_temp = self.get_show_temp_func()
        input_mode_active, input_prompt, input_buffer = self.get_input_mode_state()

        if input_mode_active:
            # Render prompt and user's current input buffer
            yield Text(
                f"{input_prompt}{input_buffer}", style="bold cyan"
            )  # Example style
        elif show_temp:
            yield self.temp_message
        else:
            # Calculate stats
            elapsed_seconds = time.time() - self.start_time
            elapsed_str = f"{elapsed_seconds:.1f}s"
            lines_streamed = self.get_current_lines_func()
            current_text = f"{elapsed_str} | {lines_streamed} lines"
            if self.live_stats_text_obj.plain != current_text:
                self.live_stats_text_obj.plain = current_text

            # Yield Columns for spinner, stats, and footer controls
            yield Columns(
                [
                    self.spinner,
                    Text(" ", style="dim"),  # Spacer
                    self.live_stats_text_obj,
                    Text("  |  ", style="dim"),  # Spacer & Separator
                    self.footer_controls,
                ],
                padding=0,
                expand=False,
            )


# State and Actions for Keypress Handling
@dataclass
class WatchDisplayState:
    wrap_text: bool = True
    is_paused: bool = False
    filter_regex_str: str | None = None
    filter_compiled_regex: re.Pattern | None = None
    input_mode_active: bool = False
    input_prompt: str = ""
    input_buffer: str = ""
    input_target_action: "WatchKeypressAction | None" = None  # Fixed forward reference


class WatchKeypressAction(Enum):
    EXIT = auto()
    TOGGLE_WRAP = auto()
    TOGGLE_PAUSE = auto()
    PROMPT_SAVE = auto()
    PROMPT_FILTER = auto()
    UPDATE_STATE_ONLY = auto()  # Use when only state changes (e.g. wrap toggle)
    ENTER_INPUT_MODE = auto()  # New action to signal entering input mode
    SUBMIT_INPUT = auto()  # New action for Enter key in input mode
    CANCEL_INPUT = auto()  # New action for Esc key in input mode
    APPEND_CHAR_TO_INPUT = auto()  # New action for appending to input buffer
    BACKSPACE_INPUT = auto()  # New action for backspace
    NO_ACTION = auto()  # For unrecognized keys


def process_keypress(
    char: str,
    current_state: WatchDisplayState,
    resource: str,
) -> tuple[WatchDisplayState, WatchKeypressAction]:
    """Processes a keypress, returning updated state and requested action."""
    action = WatchKeypressAction.NO_ACTION

    if current_state.input_mode_active:
        # Input mode key handling (delegated to _input_reader_callback,
        # but process_keypress needs to map char to specific input actions)
        if char == "\r" or char == "\n":  # Enter key
            action = WatchKeypressAction.SUBMIT_INPUT
        elif char == "\x1b":  # Escape key
            action = WatchKeypressAction.CANCEL_INPUT
        # Add Backspace handling (e.g., '\x7f' for DEL or '\x08' for BS)
        # For simplicity, we'll handle specific backspace chars if detected by read(1)
        # This is OS/terminal dependent. A more robust solution uses curses or similar.
        elif char == "\x7f" or char == "\x08":  # DEL or Backspace
            action = WatchKeypressAction.BACKSPACE_INPUT
        elif char.isprintable():
            # The char itself will be the data for APPEND_CHAR_TO_INPUT
            # The callback will handle appending it to current_state.input_buffer
            action = WatchKeypressAction.APPEND_CHAR_TO_INPUT
        # else: no action for other control chars in input mode for now
        return WatchDisplayState(
            **current_state.__dict__
        ), action  # Return current state, action is key

    # Normal mode key handling
    char_lower = char.lower()
    new_state_dict = current_state.__dict__.copy()

    if char_lower == "e":
        action = WatchKeypressAction.EXIT
    elif char_lower == "w":
        new_state_dict["wrap_text"] = not current_state.wrap_text
        action = WatchKeypressAction.TOGGLE_WRAP
    elif char_lower == "p":
        new_state_dict["is_paused"] = not current_state.is_paused
        action = WatchKeypressAction.TOGGLE_PAUSE
    elif char_lower == "s":
        new_state_dict["input_mode_active"] = True
        new_state_dict["input_prompt"] = "Save to: "
        new_state_dict["input_buffer"] = ""
        new_state_dict["input_target_action"] = WatchKeypressAction.PROMPT_SAVE
        action = WatchKeypressAction.ENTER_INPUT_MODE
    elif char_lower == "f":
        new_state_dict["input_mode_active"] = True
        new_state_dict["input_prompt"] = "Filter: "
        new_state_dict["input_buffer"] = ""
        new_state_dict["input_target_action"] = WatchKeypressAction.PROMPT_FILTER
        action = WatchKeypressAction.ENTER_INPUT_MODE

    return WatchDisplayState(**new_state_dict), action


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
    elif (
        status_info.outcome == WatchOutcome.CANCELLED
        or status_info.reason != WatchReason.PROCESS_EXIT_0
    ):
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
    get_current_display_state_func: Callable[[], WatchDisplayState],
    shared_line_counter_ref: list[int],
) -> str | None:
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
            logger.debug(
                f"_read_stream_line ({stream_name}): read {len(line)} bytes: "
                f"{line[:100]!r}"
            )
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
        return None

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

                    # Re-add task to read next line if process is still running
                    if process.returncode is None:
                        if (
                            "stdout_reader_stream_proc"
                            in task_name  # Check specific task
                            and process.stdout
                            and not process.stdout.at_eof()
                        ):
                            new_stdout_task = asyncio.create_task(
                                _read_stream_line(process.stdout, "stdout"),
                                name="stdout_reader_stream_proc",
                            )
                            pending_stream_tasks.add(new_stdout_task)
                        elif (
                            "stderr_reader_stream_proc"
                            in task_name  # Check specific task
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

    return captured_stderr


async def _execute_watch_with_live_display(
    command: str,
    resource: str,
    args: tuple[str, ...],
    output_flags: OutputFlags,
    summary_prompt_func: SummaryPromptFragmentFunc,
    allowed_exit_codes: tuple[int, ...] = (0,),
    config: Config | None = None,
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
        summary_prompt_func: Function to generate a summary prompt based on the output.
        allowed_exit_codes: Tuple of exit codes that should be treated as success.
        config: Configuration object for the command.

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

    initial_filter_compiled: re.Pattern | None = None
    if live_display_filter_regex:
        try:
            initial_filter_compiled = re.compile(live_display_filter_regex)
        except re.error as e_init_re:
            logger.warning(
                "Invalid initial filter regex from config "
                f"'{live_display_filter_regex}': {e_init_re}"
            )

    current_display_state_obj = WatchDisplayState(
        wrap_text=live_display_wrap_text,
        is_paused=False,
        filter_regex_str=live_display_filter_regex if initial_filter_compiled else None,
        filter_compiled_regex=initial_filter_compiled,
    )

    all_streamed_lines: collections.deque[str] = collections.deque(
        maxlen=stream_buffer_max_lines
    )

    footer_controls_text_obj = Text("", style="dim")
    live_stats_spinner_obj = Spinner("dots", style="dim", speed=1.5)
    live_stats_text_obj = Text("", style="dim")

    temporary_status_message_text_obj = Text("", style="dim i")
    temporary_status_message_text_obj.plain = "Initializing..."

    status_bar_renderable_placeholder = Text("")

    initial_overall_layout = Group(
        Panel(
            live_display_content,
            title=command_str,
            border_style="blue",
            height=live_display_max_lines + 2,
        ),
        status_bar_renderable_placeholder,
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
        nonlocal temporary_status_message_text_obj, status_bar_renderable_placeholder
        nonlocal resource

        is_showing_temporary_message: bool = False

        shared_line_counter = [0]

        # Create the StatusBarManager instance HERE, passing necessary components/data
        status_bar_manager = StatusBarManager(
            start_time=start_time_session,
            get_current_lines_func=lambda: shared_line_counter[0],
            spinner=live_stats_spinner_obj,
            live_stats_text_obj=live_stats_text_obj,
            temporary_message_text_obj=temporary_status_message_text_obj,
            get_show_temporary_message_func=lambda: is_showing_temporary_message,
            footer_controls_text_obj=footer_controls_text_obj,
            get_input_mode_state_func=lambda: (
                current_display_state_obj.input_mode_active,
                current_display_state_obj.input_prompt,
                current_display_state_obj.input_buffer,
            ),
        )

        # Replace the placeholder in the live instance's layout
        if (
            live_instance_ref
            and hasattr(live_instance_ref, "renderable")
            and isinstance(live_instance_ref.renderable, Group)
            and len(live_instance_ref.renderable.renderables) > 1
        ):
            live_instance_ref.renderable.renderables[1] = status_bar_manager
            live_instance_ref.refresh()

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
                    with contextlib.suppress(Exception):
                        sys.stdin.read(1)  # Consume the keypress
                    return

                char = sys.stdin.read(1)
                if not char:
                    return

                # Get new state and action from process_keypress
                new_state_from_keypress, requested_action = process_keypress(
                    char, current_display_state_obj, resource
                )

                # If in input mode, and action is APPEND_CHAR_TO_INPUT, char is the data
                char_to_append = (
                    char
                    if requested_action == WatchKeypressAction.APPEND_CHAR_TO_INPUT
                    and char.isprintable()
                    else None
                )

                current_display_state_obj = (
                    new_state_from_keypress  # Update state first
                )

                # Handle actions
                if requested_action == WatchKeypressAction.EXIT:
                    logger.debug("Exit action requested by keypress.")
                    loop.call_soon_threadsafe(exit_requested_event.set)

                elif requested_action == WatchKeypressAction.ENTER_INPUT_MODE:
                    # Finalize the prompt string based on the target action
                    if (
                        current_display_state_obj.input_target_action
                        == WatchKeypressAction.PROMPT_SAVE
                    ):
                        filename_path = resource.replace("/", "_")
                        filename_suffix = time.strftime("%Y%m%d_%H%M%S")
                        filename_suggestion = (
                            f"vibectl_watch_{filename_path}_{filename_suffix}.log"
                        )
                        current_display_state_obj.input_prompt = (
                            f"Save to [{filename_suggestion}]: "
                        )
                    elif (
                        current_display_state_obj.input_target_action
                        == WatchKeypressAction.PROMPT_FILTER
                    ):
                        filter_regex_str = current_display_state_obj.filter_regex_str
                        current_filter_display = (
                            f" (current: '{filter_regex_str}')"
                            if filter_regex_str
                            else " (off)"
                        )
                        current_display_state_obj.input_prompt = (
                            f"Filter regex (empty to clear){current_filter_display}: "
                        )
                    # Else: prompt already set generically by process_keypress or
                    # invalid state?
                    # Let StatusBarManager pick up the updated prompt on next refresh.
                    pass  # State change already handled activation

                elif requested_action == WatchKeypressAction.APPEND_CHAR_TO_INPUT:
                    if char_to_append:
                        current_display_state_obj.input_buffer += char_to_append
                    # StatusBarManager will show updated buffer on refresh

                elif requested_action == WatchKeypressAction.BACKSPACE_INPUT:
                    if current_display_state_obj.input_buffer:
                        current_display_state_obj.input_buffer = (
                            current_display_state_obj.input_buffer[:-1]
                        )
                    # StatusBarManager will show updated buffer on refresh

                elif requested_action == WatchKeypressAction.SUBMIT_INPUT:
                    # Finalize the input
                    target_action = current_display_state_obj.input_target_action
                    buffer_content = current_display_state_obj.input_buffer

                    # Reset input mode state FIRST
                    current_display_state_obj.input_mode_active = False
                    current_display_state_obj.input_prompt = ""
                    current_display_state_obj.input_buffer = ""
                    current_display_state_obj.input_target_action = None

                    _finalize_input_action(target_action, buffer_content, max_lines)
                    # _finalize_input_action will call _set_temporary_status_message
                    # for confirmation

                elif requested_action == WatchKeypressAction.CANCEL_INPUT:
                    current_display_state_obj.input_mode_active = False
                    current_display_state_obj.input_prompt = ""
                    current_display_state_obj.input_buffer = ""
                    current_display_state_obj.input_target_action = None
                    _set_temporary_status_message("Input cancelled.", True)
                    _refresh_footer_controls_text(
                        footer_controls_text_obj, current_display_state_obj
                    )  # Refresh to show normal controls

                elif requested_action in [
                    WatchKeypressAction.TOGGLE_WRAP,
                    WatchKeypressAction.TOGGLE_PAUSE,
                ]:
                    # Update display content for wrap/pause changes
                    live_display_content.no_wrap = (
                        not current_display_state_obj.wrap_text
                    )
                    if (
                        not current_display_state_obj.is_paused
                    ):  # If unpausing, refresh content
                        filtered_lines = _apply_filter_to_lines(
                            all_streamed_lines,
                            current_display_state_obj.filter_compiled_regex,
                        )
                        latest_lines_to_display = filtered_lines[-max_lines:]
                        live_display_content.plain = "\n".join(latest_lines_to_display)

                    # Footer text IS part of StatusBarManager, but the underlying Text
                    # object needs its .plain updated.
                    _refresh_footer_controls_text(
                        footer_controls_text_obj, current_display_state_obj
                    )

            except Exception as e_callback:
                logger.debug(f"Error in callback: {e_callback}", exc_info=True)

        def _finalize_input_action(
            target_action: WatchKeypressAction | None,
            buffer: str,
            max_lines_for_display: int,
        ) -> None:
            nonlocal \
                current_display_state_obj, \
                save_dir, \
                resource, \
                all_streamed_lines, \
                live_display_content

            if target_action == WatchKeypressAction.PROMPT_SAVE:
                filename_path = resource.replace("/", "_")
                filename_suffix = time.strftime("%Y%m%d_%H%M%S")
                filename_suggestion = (
                    f"vibectl_watch_{filename_path}_{filename_suffix}.log"
                )
                try:
                    saved_path = _perform_save_to_file(
                        save_dir=save_dir,
                        filename_suggestion=filename_suggestion,
                        user_provided_filename=buffer or None,  # Use buffer as filename
                        all_lines=all_streamed_lines,
                        filter_re=current_display_state_obj.filter_compiled_regex,
                    )
                    _set_temporary_status_message(f"Saved to {saved_path}", True)
                except OSError as e:
                    _set_temporary_status_message(f"Save failed: {e}", True)
                except Exception as e_save_final:
                    _set_temporary_status_message(f"Save error: {e_save_final}", True)

            elif target_action == WatchKeypressAction.PROMPT_FILTER:
                new_filter_str: str | None = None
                new_filter_re: re.Pattern | None = None
                filter_update_status = "Filter cleared."

                if buffer:  # User entered something
                    try:
                        new_filter_re = re.compile(buffer)
                        new_filter_str = buffer
                        filter_update_status = f"Filter set to '{new_filter_str}'."
                    except re.error as e_re:
                        filter_update_status = (
                            f"Invalid regex: {e_re}. Filter unchanged."
                        )
                        # Keep old filter if new one is invalid
                        new_filter_str = current_display_state_obj.filter_regex_str
                        new_filter_re = current_display_state_obj.filter_compiled_regex
                else:  # User submitted empty buffer, clear filter
                    new_filter_str, new_filter_re = None, None

                current_display_state_obj = WatchDisplayState(
                    current_display_state_obj.wrap_text,
                    current_display_state_obj.is_paused,
                    new_filter_str,
                    new_filter_re,
                    input_mode_active=False,  # Ensure these are reset
                    input_prompt="",
                    input_buffer="",
                    input_target_action=None,
                )

                # Refresh main display content based on new filter
                if not current_display_state_obj.is_paused:
                    filtered_lines = _apply_filter_to_lines(
                        all_streamed_lines,
                        current_display_state_obj.filter_compiled_regex,
                    )
                    latest_lines_to_display = filtered_lines[-max_lines_for_display:]
                    live_display_content.plain = "\n".join(latest_lines_to_display)

                _set_temporary_status_message(filter_update_status, True)

            # After finalizing, ensure footer controls text is up-to-date
            _refresh_footer_controls_text(
                footer_controls_text_obj, current_display_state_obj
            )

        reader_callback_with_args = functools.partial(
            _input_reader_callback, max_lines=live_display_max_lines
        )

        async def _wrapped_process_wait(proc: asyncio.subprocess.Process) -> None:
            if proc:
                await proc.wait()

        async def _wrapped_event_wait(event: asyncio.Event) -> None:
            if event:
                await event.wait()

        def _set_temporary_status_message(
            message: str, require_keypress: bool = True
        ) -> None:
            nonlocal \
                temporary_status_message_text_obj, \
                status_bar_renderable_placeholder
            nonlocal is_showing_temporary_message

            msg_to_display = message
            if require_keypress:
                msg_to_display += " Press any key to continue..."
            temporary_status_message_text_obj.plain = msg_to_display
            is_showing_temporary_message = True

        def _revert_to_live_status() -> None:
            nonlocal is_showing_temporary_message
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

            cmd_list_for_proc = [command, resource, *args]
            process = await create_async_kubectl_process(cmd_list_for_proc, config=cfg)

            stream_handler_task = asyncio.create_task(
                _process_stream_output(
                    process,
                    live_display_content,
                    all_streamed_lines,
                    accumulated_output_lines,
                    live_display_max_lines,
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
            if stream_handler_task:
                if not stream_handler_task.done():
                    try:
                        async with asyncio.timeout(2.0):
                            stream_stderr = await stream_handler_task
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
                        stream_stderr = stream_handler_task.result()
                    except Exception as e_sh_res:
                        if error_message is None:
                            error_message = f"Stream result error: {e_sh_res}"

            if stream_stderr and error_message is None:
                error_message = stream_stderr

            final_outcome = WatchOutcome.SUCCESS
            final_reason = WatchReason.PROCESS_EXIT_0
            final_detail = error_message
            final_exit_code = process.returncode

            # Check process exit code status
            if process.returncode is None:
                final_outcome, final_reason, final_detail = (
                    WatchOutcome.ERROR,
                    WatchReason.INTERNAL_ERROR,
                    final_detail or "Process ended without exit code.",
                )
            elif process.returncode not in allowed_exit_codes:
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
            return Success(
                data=current_status_info,
                original_exit_code=process.returncode,
            )

        except asyncio.CancelledError as e_cancel:
            detail = str(e_cancel) if str(e_cancel) else "Operation cancelled."
            # Determine reason based on detail
            if "via 'E' key" in detail:  # Note: single quotes 'E'
                pass  # reason_cancel = WatchReason.USER_EXIT_KEY

            return Error(error=detail)  # _run_async_main will wrap this
        except FileNotFoundError as e_fnf:
            return Error(error=str(e_fnf))  # _run_async_main will wrap this
        except Exception as e_unhandled:
            logger.error(f"Unhandled in main_watch_task: {e_unhandled}", exc_info=True)
            return Error(error=str(e_unhandled))  # _run_async_main will wrap this
        finally:
            if input_reader_active and sys.stdin.isatty() and original_termios_settings:
                with contextlib.suppress(Exception):
                    loop.remove_reader(sys.stdin.fileno())
                with contextlib.suppress(Exception):
                    termios.tcsetattr(
                        sys.stdin.fileno(), termios.TCSADRAIN, original_termios_settings
                    )

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
        initial_overall_layout,
        console=console_manager.console,
        refresh_per_second=10,
        transient=False,  # Keep final summary
        vertical_overflow="visible",
    ) as live_instance:  # live_instance is now available
        # Pass live_instance to main_watch_task
        loop_result = await _run_async_main(
            main_watch_task(live_instance),  # Pass it here
            cancel_message="Watch cancelled by user (Ctrl+C)",
            error_message_prefix="Watch execution",
        )

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
            # Add more detailed parsing if needed, e.g., from
            # kubectl exit codes in error_detail_str

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
        live_instance.refresh()

        summary_table = _create_watch_summary_table(
            command_str=command_str,
            status_info=final_status_info,
            elapsed_time=elapsed_time,
            lines_streamed=final_lines_for_summary,  # Use len(accumulated_output_lines)
        )

        final_status_message = Text("Watch ended.", style="dim")  # Simple static text

        final_layout = Group(
            # Use the summary table IN a panel for the final display main content
            Panel(
                summary_table,
                title="Watch Session Ended",
                border_style="green" if not overall_operation_had_error else "red",
            ),
            final_status_message,  # Use the simple static text for the status line
            # footer_final, # REMOVED - This was causing the duplicate controls
        )
        live_instance.update(
            final_layout, refresh=True
        )  # Update with the final static layout

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

        return Success(
            message=" ".join(success_msg_parts),
            data=raw_output_str,
            original_exit_code=final_status_info.exit_code,
        )
