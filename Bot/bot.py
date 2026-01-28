import os
import platform
import re
import sys
import threading
import time
import tkinter as tk
import tkinter.font as tkFont
from datetime import datetime
from typing import Any, List, Tuple

import pyautogui
from loguru import logger

from Bot import config as cfg
from Bot import functions as fe
from Bot.event_listener import EveEventListener

config = cfg.ConfigHandler("config.properties")  # type: ignore

logger.remove()

log_level = config.get_log_level()
logger.add(
    "client.log",
    level=log_level,
    format="[{time}] [{level}] {name}:{function}:{line} - {message}",
    colorize=False,
    backtrace=True,
    diagnose=True,
    rotation="1 day",
    retention="31 days",
)

logger.add(sys.stdout, level=log_level)

# When cargo hold is full, the ship will dock up and unload cargo, undock and warp to another belt
cargo_loading_time_adjustment = config.get_cargo_loading_time_adjustment()

# take screenshots after clearing cargo
take_screenshots = config.get_take_screenshots()

# warping to belt time
warping_time = config.get_warping_time()

# auto reset miners before selecting and activating new targets
auto_reset_miners = config.get_auto_reset_miners()

# CONSTANTS

SMALL_SLEEP = 12
MEDIUM_SLEEP = 70
LONG_SLEEP = 100

# globals (just for reference, not actually needed)

stop_flag = False
selected_eve_window: Any = None
event_listener: EveEventListener = EveEventListener()
cargo_full_event = threading.Event()
under_attack_event = threading.Event()
asteroid_depleted_event = threading.Event()
warp_complete_event = threading.Event()

# Mining functions
#########################################################


def get_estimated_run_time(
    mining_runs: int, cargo_loading_time: float, cargo_loading_time_adjustment: int
) -> float:
    return mining_runs * (
        cargo_loading_time + (cargo_loading_time_adjustment if mining_runs > 1 else 0)
    )


def get_cargo_loading_time(mining_hold: int, mining_yield: float) -> float:
    if mining_hold == 0:
        return 0
    time = mining_hold / mining_yield if mining_yield > 0 else 0
    if time < LONG_SLEEP:
        logger.error("Mining yield misconfiguration: loading time < warp-out time.")
    return time


# GUI settings
#########################################################

# Create Tkinter window
root = tk.Tk()
root.wm_attributes("-topmost", 1)
root.title("Mining Bot Owl-Edition")
screen_width = root.winfo_screenwidth()
screen_height = root.winfo_screenheight()
window_width = 480
window_height = 720
x_pos = screen_width - window_width
y_pos = 0
root.geometry(f"{window_width}x{window_height}+{x_pos}+{y_pos}")

# Make window not resizable
root.resizable(False, True)

# close everything on window close
root.protocol("WM_DELETE_WINDOW", lambda: os._exit(0))

# Create frame for input and buttons
input_frame = tk.Frame(root)
input_frame.pack(pady=10)

# Create frame for start- and stop buttons
button_frame = tk.Frame(root)
button_frame.pack(pady=10)

# EVE window selection
#########################################################


def get_windows_with_title(title) -> List[Any]:
    if platform.system() == "Windows":
        # since there is not types for this libary, we ignore the types
        import pygetwindow as gw  # type: ignore

        return gw.getWindowsWithTitle(title)
    else:
        return []


# For some reason cant use global reference as in the function below
# propably because its passed in lambda
def activate_eve_window() -> None:
    selected_eve_window = globals().get("selected_eve_window")
    if selected_eve_window is not None:
        selected_eve_window.activate()


def on_window_select(selection: str) -> None:
    global selected_eve_window
    windows = get_windows_with_title(selection)
    if windows:
        selected_eve_window = windows[0]


# Label for the EVE window selector
window_label = tk.Label(input_frame, text="Select EVE window:")
window_label.grid(row=0, column=0, sticky="w")

# Get list of EVE windows
window_titles: List[str] = []
eve_windows = get_windows_with_title("EVE -")
if eve_windows:
    window_titles = [window.title for window in eve_windows]
else:
    window_titles = ["No EVE windows"]

# Dropdown menu
# Default selection
eve_window = tk.StringVar()
if window_titles:
    eve_window.set(window_titles[0])
    if eve_windows:
        selected_eve_window = eve_windows[0]
        logger.info("Selected the first EVE window")
else:
    eve_window.set("No EVE windows")


# Function to update the OptionMenu text
def update_option_menu(selection: str) -> None:
    if selection:
        eve_window.set(re.sub(r"EVE - .*", "EVE - REDACTED", selection))
    else:
        eve_window.set("No EVE windows")


window_select = tk.OptionMenu(
    input_frame, eve_window, *window_titles, command=on_window_select
)
update_option_menu(eve_window.get())  # Update initial text
eve_window.trace_add(
    "write", lambda *args: update_option_menu(eve_window.get())
)  # Update text on selection change
window_select.grid(row=0, column=1, padx=5, pady=4, sticky="w")

# Mining time
#########################################################


def format_coo(coo: List[int]) -> str:
    return ", ".join(map(str, coo))


def format_list_coo(coo_list: List[List[int]]) -> str:
    return "\n".join(format_coo(coo) for coo in coo_list)


# Label for the number of mining runs
entry_label = tk.Label(input_frame, text="Set number of mining runs:")
entry_label.grid(row=1, column=0, sticky="w")

# Entry field for the number of mining runs
entry_var = tk.StringVar()
entry = tk.Entry(input_frame, textvariable=entry_var)
entry.grid(row=1, column=1, padx=5, pady=4, sticky="w")
entry.insert(tk.END, config.get_mining_runs())

# Mining Hold
#########################################################

# Create input field for mining hold in m3
mining_hold_var = tk.StringVar()
mining_hold_label = tk.Label(input_frame, text="Mining Hold (m3):")
mining_hold_label.grid(row=2, column=0, sticky="w")
mining_hold_entry = tk.Entry(input_frame, textvariable=mining_hold_var)
mining_hold_entry.grid(row=2, column=1, padx=5, pady=4, sticky="w")
mining_hold_entry.insert(tk.END, config.get_mining_hold())

# Mining Yield
#########################################################

# Create input field for mining yield in m3/s
mining_yield_var = tk.StringVar()
mining_yield_label = tk.Label(input_frame, text="Mining Yield (m3/s):")
mining_yield_label.grid(row=3, column=0, sticky="w")
mining_yield_entry = tk.Entry(input_frame, textvariable=mining_yield_var)
mining_yield_entry.grid(row=3, column=1, padx=5, pady=4, sticky="w")
mining_yield_entry.insert(tk.END, config.get_mining_yield())

# Undock
#########################################################

# create input field for undock coordinates
undock_coo_label = tk.Label(input_frame, text="Undock-Button Position:")
undock_coo_label.grid(row=4, column=0, sticky="w")
undock_coo_entry = tk.Entry(input_frame)
undock_coo_entry.grid(row=4, column=1, padx=5, pady=4, sticky="w")
undock_coo_entry.insert(tk.END, format_coo(config.get_undock_coo()))


def test_undock():
    save_properties()
    try:
        x, y = get_coo_or_error(config.get_undock_coo(), "undock_coo")
        pyautogui.moveTo(x, y)
    except ValueError as e:
        logger.error(str(e))


undock_test_button = tk.Button(
    input_frame,
    text="Test",
    command=lambda: execute_and_enable(undock_test_button, test_undock),
)
undock_test_button.grid(row=4, column=2, padx=5, pady=4, sticky="w")

# Clear Cargo Position
#########################################################

# Create input field for clear-cargo position
clear_cargo_coo_label = tk.Label(input_frame, text="Clear-Cargo Position:")
clear_cargo_coo_label.grid(row=5, column=0, sticky="w")
clear_cargo_coo_entry = tk.Entry(input_frame)
clear_cargo_coo_entry.grid(row=5, column=1, padx=5, pady=4, sticky="w")
clear_cargo_coo_entry.insert(tk.END, format_coo(config.get_clear_cargo_coo()))

# check if the coordinate is set correctly


def execute_and_enable(button, func):
    # Disable the button to prevent further clicks.
    button.config(state=tk.DISABLED)

    def execute_function():
        func()

        # Enable the button after the function completes.
        root.after(1, lambda: button.config(state=tk.NORMAL))

    # Run function in a separate thread
    thread = threading.Thread(target=execute_function, daemon=True)
    thread.start()


def test_clear_cargo():
    save_properties()
    try:
        x, y = get_coo_or_error(config.get_clear_cargo_coo(), "clear_cargo_coo")
        fe.clear_cargo(x=x, y=y)
    except ValueError as e:
        logger.error(str(e))


clear_cargo_check_button = tk.Button(
    input_frame,
    text="Test",
    compound="left",
    command=lambda: execute_and_enable(clear_cargo_check_button, test_clear_cargo),
)
clear_cargo_check_button.grid(row=5, column=2, padx=5, pady=4, sticky="w")

# Target-One-Position
########################################################

# Create input field for target-one position
target_one_coo_label = tk.Label(input_frame, text="Target-One Overview Position:")
target_one_coo_label.grid(row=6, column=0, sticky="w")
target_one_coo_entry = tk.Entry(input_frame)
target_one_coo_entry.grid(row=6, column=1, padx=5, pady=4, sticky="w")
target_one_coo_entry.insert(tk.END, format_coo(config.get_target_one_coo()))


def test_target_one():
    save_properties()
    try:
        x, y = get_coo_or_error(config.get_target_one_coo(), "target_one_coo")
        pyautogui.moveTo(x, y)
    except ValueError as e:
        logger.error(str(e))


target_one_coo_test_button = tk.Button(
    input_frame,
    text="Test",
    command=lambda: execute_and_enable(
        target_one_coo_test_button,
        test_target_one,
    ),
)
target_one_coo_test_button.grid(row=6, column=2, padx=5, pady=4, sticky="w")

# Target-Two-Position
#######################################################

# Create input field for target-two position
target_two_coo_label = tk.Label(input_frame, text="Target-Two Overview Position:")
target_two_coo_label.grid(row=7, column=0, sticky="w")
target_two_coo_entry = tk.Entry(input_frame)
target_two_coo_entry.grid(row=7, column=1, padx=5, pady=4, sticky="w")
target_two_coo_entry.insert(tk.END, format_coo(config.get_target_two_coo()))


def test_target_two():
    save_properties()
    try:
        x, y = get_coo_or_error(config.get_target_two_coo(), "target_two_coo")
        pyautogui.moveTo(x, y)
    except ValueError as e:
        logger.error(str(e))


target_two_coo_test_button = tk.Button(
    input_frame,
    text="Test",
    command=lambda: execute_and_enable(
        target_one_coo_test_button,
        test_target_two,
    ),
)
target_two_coo_test_button.grid(row=7, column=2, padx=5, pady=4, sticky="w")

# Target-Reset-Position
#######################################################

# Create input field for mouse reset
mouse_reset_coo_label = tk.Label(input_frame, text="Mouse Reset Position:")
mouse_reset_coo_label.grid(row=8, column=0, sticky="w")
mouse_reset_coo_entry = tk.Entry(input_frame)
mouse_reset_coo_entry.grid(row=8, column=1, padx=5, pady=4, sticky="w")
mouse_reset_coo_entry.insert(tk.END, format_coo(config.get_mouse_reset_coo()))


def test_mouse_reset():
    save_properties()
    try:
        x, y = get_coo_or_error(config.get_mouse_reset_coo(), "mouse_reset_coo")
        pyautogui.moveTo(x, y)
    except ValueError as e:
        logger.error(str(e))


mouse_reset_coo_test_button = tk.Button(
    input_frame,
    text="Test",
    command=lambda: execute_and_enable(
        target_one_coo_test_button,
        test_mouse_reset,
    ),
)
mouse_reset_coo_test_button.grid(row=8, column=2, padx=5, pady=4, sticky="w")

# Home Position
##########################################################

# Create input field for warp-to position
home_coo_label = tk.Label(input_frame, text="Home Bookmark:")
home_coo_label.grid(row=9, column=0, sticky="w")
home_coo_entry = tk.Entry(input_frame)
home_coo_entry.grid(row=9, column=1, padx=5, pady=4, sticky="w")
home_coo_entry.insert(tk.END, format_coo(config.get_home_coo()))


def test_warp_to():
    save_properties()
    try:
        x, y = get_coo_or_error(config.get_home_coo(), "warp_to_coo")
        pyautogui.moveTo(x, y)
    except ValueError as e:
        logger.error(str(e))


home_coo_test_button = tk.Button(
    input_frame,
    text="Test",
    command=lambda: execute_and_enable(
        target_one_coo_test_button,
        test_warp_to,
    ),
)
home_coo_test_button.grid(row=9, column=2, padx=5, pady=4, sticky="w")

# Belt Bookmarks
#########################################################

# Create input field for mining position
mining_coo_label = tk.Label(input_frame, text="Belt Bookmarks:")
mining_coo_label.grid(row=10, column=0, sticky="w")
mining_coo_entry = tk.Text(input_frame, width=15, height=5)
mining_coo_entry.grid(row=10, column=1, padx=5, pady=4, sticky="w")
mining_coo_entry.insert(tk.END, format_list_coo(config.get_mining_coo()))

#########################################################

# Create start button
start_button = tk.Button(button_frame, text="Start")
start_button.grid(row=0, column=0, padx=(0, 10), pady=10, ipadx=5)

# Create stop button
stop_button = tk.Button(button_frame, text="Stop")
stop_button.grid(row=0, column=1, padx=(10, 0), pady=10, ipadx=5)
stop_button.config(state=tk.DISABLED)

panic_button = tk.Button(button_frame, text="Panic", bg="red", fg="white")
panic_button.grid(row=0, column=2, padx=(10, 0), pady=10, ipadx=5)

# Create global save button
save_button = tk.Button(button_frame, text="Save")
save_button.grid(row=0, column=3, padx=(20, 0), pady=10, ipadx=5)

# Start from step selection
########################################################
start_from_label = tk.Label(button_frame, text="Начать с этапа:")
start_from_label.grid(row=1, column=0, padx=(0, 5), pady=5, sticky="w")

start_from_var = tk.StringVar(value="undock")
start_from_options = [
    ("Отстыковка", "undock"),
    ("Варп на бельт", "warp"),
    ("Сбор руды", "mining"),
    ("Пристыковка", "dock"),
    ("Очистка трюма", "clear_cargo")
]

start_from_menu = tk.OptionMenu(
    button_frame, 
    start_from_var, 
    "undock",
    "warp",
    "mining",
    "dock",
    "clear_cargo"
)
start_from_menu.grid(row=1, column=1, padx=5, pady=5, sticky="w")

########################################################
# Step-by-step control buttons
########################################################

step_control_frame = tk.Frame(root)
step_control_frame.pack(pady=10)

bold_font = tkFont.Font(weight="bold")
step_label = tk.Label(step_control_frame, text="Пошаговое управление:", font=bold_font)
step_label.grid(row=0, column=0, columnspan=5, pady=(0, 5), sticky="w")

########################################################


def insert_mouse_position(event) -> None:
    x, y = pyautogui.position()
    if isinstance(event.widget, tk.Text):
        event.widget.insert(tk.END, f"\n{x}, {y}")
    elif isinstance(event.widget, tk.Entry):
        event.widget.delete(0, tk.END)
        event.widget.insert(tk.END, f"{x}, {y}")


# Create a label to display the mouse position
mouse_position_label = tk.Label(root, text="")
mouse_position_label.pack(pady=10)


# Function to update the mouse position
def update_mouse_position() -> None:
    x, y = pyautogui.position()
    mouse_position_label.config(text=f"Mouse-Position: {x}, {y}", font=("Arial", 12))
    mouse_position_label.after(100, update_mouse_position)


# Start update mouse position
update_mouse_position()

# icon_bitmap
root.iconbitmap("")

root.bind("<Control-i>", insert_mouse_position)


def update_estimated_run_time(*args) -> None:
    config.set_mining_runs(entry_var.get())
    config.set_mining_hold(mining_hold_var.get())
    config.set_mining_yield(mining_yield_var.get())
    if mining_hold_var.get() and mining_yield_var.get() and entry_var.get():
        estimated_run_time = get_estimated_run_time(
            mining_runs=config.get_mining_runs(),
            cargo_loading_time=get_cargo_loading_time(
                config.get_mining_hold(), config.get_mining_yield()
            ),
            cargo_loading_time_adjustment=cargo_loading_time_adjustment,
        )
        total_time_label.config(
            text=f"Estimated time to complete: {fe.get_remaining_time(estimated_run_time)}"
        )
        start_button.config(state=tk.ACTIVE)
    else:
        total_time_label.config(text="Estimated time to complete: N/A")
        start_button.config(state=tk.DISABLED)


mining_hold_var.trace_add("write", update_estimated_run_time)
mining_yield_var.trace_add("write", update_estimated_run_time)
entry_var.trace_add("write", update_estimated_run_time)

total_time_label = tk.Label(root, text="", font=("Arial", 12))
total_time_label.pack(pady=10)

update_estimated_run_time()


# label for completed/remaining mining runs
def update_mining_runs(actual: int, wanted: int):
    mining_runs_result.config(text=f"Completed runs: {actual}/{wanted}")


mining_runs_result = tk.Label(root, text="", font=("Arial", 12))
mining_runs_result.pack(pady=10)
update_mining_runs(0, 0)

# Create a label to display the countdown timer
cargo_hold_time_label = tk.Label(root, text="", font=("Arial", 12))
cargo_hold_time_label.pack(pady=10)

# Start updating the countdown timer
fe.update_timer(cargo_hold_time_label, fe.CARGO_LOAD_TIME)

# Create a label to display the countdown timer
next_reset_label = tk.Label(root, text="", font=("Arial", 12))
next_reset_label.pack(pady=10)

# Start updating the countdown timer
fe.update_timer(next_reset_label, fe.NEXT_RESET_IN)


def disable_fields() -> None:
    # Disable input fields
    entry.config(state=tk.DISABLED)
    undock_coo_entry.config(state=tk.DISABLED)
    clear_cargo_coo_entry.config(state=tk.DISABLED)
    mining_hold_entry.config(state=tk.DISABLED)
    mining_yield_entry.config(state=tk.DISABLED)
    target_one_coo_entry.config(state=tk.DISABLED)
    target_two_coo_entry.config(state=tk.DISABLED)
    mouse_reset_coo_entry.config(state=tk.DISABLED)
    home_coo_entry.config(state=tk.DISABLED)
    mining_coo_entry.config(state=tk.NORMAL)
    mining_coo_entry.tag_configure("disabled", foreground="gray")
    mining_coo_entry.config(state=tk.DISABLED)
    mining_coo_entry.insert(tk.END, format_list_coo(config.get_mining_coo()))
    mining_coo_entry.tag_add("disabled", "1.0", "end")

    # Disable buttons
    start_button.config(state=tk.DISABLED)
    save_button.config(state=tk.DISABLED)
    clear_cargo_coo_entry.config(state=tk.DISABLED)
    stop_button.config(state=tk.NORMAL)


def enable_fields() -> None:
    # Enable input fields
    entry.config(state=tk.NORMAL)
    undock_coo_entry.config(state=tk.NORMAL)
    clear_cargo_coo_entry.config(state=tk.NORMAL)
    mining_hold_entry.config(state=tk.NORMAL)
    mining_yield_entry.config(state=tk.NORMAL)
    target_one_coo_entry.config(state=tk.NORMAL)
    target_two_coo_entry.config(state=tk.NORMAL)
    mouse_reset_coo_entry.config(state=tk.NORMAL)
    home_coo_entry.config(state=tk.NORMAL)
    mining_coo_entry.config(state=tk.NORMAL)
    mining_coo_entry.tag_remove("disabled", "1.0", "end")

    # Enable buttons
    start_button.config(state=tk.NORMAL)
    save_button.config(state=tk.NORMAL)
    clear_cargo_coo_entry.config(state=tk.NORMAL)
    stop_button.config(state=tk.DISABLED)


def stop_function() -> None:
    global stop_flag
    stop_flag = True
    stop_button.config(state=tk.DISABLED)
    logger.warning("The mining script will end on next reset!")


def get_coo_or_error(coo_list: List[int], param_name: str) -> Tuple[int, int]:
    if len(coo_list) != 2:
        raise ValueError(
            f"Координаты '{param_name}' не заданы в config.properties. "
            f"Пожалуйста, укажите координаты в формате: {param_name} = x, y"
        )
    return coo_list[0], coo_list[1]


def on_cargo_full_event(event_type: str, line: str) -> None:
    logger.warning(f"Обнаружено событие: Карго заполнено! Строка: {line.strip()[:150]}")
    cargo_full_event.set()
    logger.info("Событие cargo_full_event установлено")


def on_under_attack_event(event_type: str, line: str) -> None:
    logger.warning("Обнаружено событие: Атака!")
    under_attack_event.set()


def on_asteroid_depleted_event(event_type: str, line: str) -> None:
    logger.warning("Обнаружено событие: Астероид истощен!")
    asteroid_depleted_event.set()


def on_warp_complete_event(event_type: str, line: str) -> None:
    logger.info(f"Обнаружено событие: Варп завершен! Строка: {line.strip()[:150]}")
    warp_complete_event.set()


def init_event_listener() -> None:
    try:
        event_listener.register_event('cargo_full', on_cargo_full_event)
        event_listener.register_event('under_attack', on_under_attack_event)
        event_listener.register_event('mining_complete', on_asteroid_depleted_event)
        event_listener.register_event('warp_complete', on_warp_complete_event)
        
        if event_listener.start():
            logger.info("Слушатель событий Eve Online успешно запущен")
        else:
            logger.warning("Не удалось запустить слушатель событий")
    except Exception as e:
        logger.error(f"Ошибка при инициализации слушателя событий: {e}")


def stop_event_listener() -> None:
    try:
        event_listener.stop()
        logger.info("Слушатель событий остановлен")
    except Exception as e:
        logger.error(f"Ошибка при остановке слушателя событий: {e}")


def step_undock() -> None:
    def execute_function() -> None:
        try:
            activate_eve_window()
            undock_x, undock_y = get_coo_or_error(config.get_undock_coo(), "undock_coo")
            fe.undock(x=undock_x, y=undock_y)
            fe.sleep_and_log(SMALL_SLEEP)
            fe.set_hardener_online(config.get_hardener_keys())
            logger.info("Отстыковка завершена")
        except ValueError as e:
            logger.error(str(e))
        except Exception as e:
            logger.error(f"Ошибка при отстыковке: {e}")
    
    thread = threading.Thread(target=execute_function, daemon=True)
    thread.start()


def step_dock() -> None:
    def execute_function() -> None:
        try:
            activate_eve_window()
            home_coo = config.get_home_coo()
            if len(home_coo) != 2:
                raise ValueError("Координаты 'warp_to_coo' не заданы в config.properties")
            fe.auto_dock_to_station(home_coo)
            fe.sleep_and_log(LONG_SLEEP)
            logger.info("Пристыковка завершена")
        except ValueError as e:
            logger.error(str(e))
        except Exception as e:
            logger.error(f"Ошибка при пристыковке: {e}")
    
    thread = threading.Thread(target=execute_function, daemon=True)
    thread.start()


def step_warp_to_belt() -> None:
    def execute_function() -> None:
        try:
            activate_eve_window()
            mining_coo_list = config.get_mining_coo()
            if not mining_coo_list:
                raise ValueError("Координаты 'mining_coo' не заданы в config.properties")
            item = fe.get_random_coord(mining_coo_list)
            fe.click_top_left_circle_menu(item[0], item[1])
            fe.sleep_and_log(warping_time)
            logger.info("Варп на бельт завершен")
        except ValueError as e:
            logger.error(str(e))
        except Exception as e:
            logger.error(f"Ошибка при варпе на бельт: {e}")
    
    thread = threading.Thread(target=execute_function, daemon=True)
    thread.start()


def step_mining() -> None:
    def execute_function() -> None:
        try:
            cargo_full_event.clear()
            activate_eve_window()
            rm_x, rm_y = get_coo_or_error(config.get_mouse_reset_coo(), "mouse_reset_coo")
            fe.drone_out(x=rm_x, y=rm_y)
            tx1, ty1 = get_coo_or_error(config.get_target_one_coo(), "target_one_coo")
            tx2, ty2 = get_coo_or_error(config.get_target_two_coo(), "target_two_coo")
            
            mining_hold = config.get_mining_hold()
            mining_yield = config.get_mining_yield()
            cargo_loading_time = get_cargo_loading_time(mining_hold, mining_yield)
            
            def check_cargo_full() -> bool:
                return cargo_full_event.is_set()
            
            def check_asteroid_depleted() -> bool:
                return asteroid_depleted_event.is_set()
            
            fe.mining_behaviour(
                tx1=tx1,
                ty1=ty1,
                tx2=tx2,
                ty2=ty2,
                mining_reset=config.get_mining_reset_timer(),
                mining_loop=cargo_loading_time,
                rm_x=rm_x,
                rm_y=rm_y,
                unlock_all_targets_keys=config.get_unlock_all_targets_key(),
                activate_eve_window=activate_eve_window,
                is_stopped=check_cargo_full,
                auto_reset_miners=auto_reset_miners,
                asteroid_depleted=check_asteroid_depleted,
            )
            fe.drone_in()
            fe.sleep_and_log(SMALL_SLEEP)
            logger.info("Сбор руды завершен")
        except ValueError as e:
            logger.error(str(e))
        except Exception as e:
            logger.error(f"Ошибка при сборе руды: {e}")
    
    thread = threading.Thread(target=execute_function, daemon=True)
    thread.start()


def step_clear_cargo() -> None:
    def execute_function() -> None:
        try:
            activate_eve_window()
            cg_x, cg_y = get_coo_or_error(config.get_clear_cargo_coo(), "clear_cargo_coo")
            fe.clear_cargo(x=cg_x, y=cg_y)
            logger.info("Очистка трюма завершена")
        except ValueError as e:
            logger.error(str(e))
        except Exception as e:
            logger.error(f"Ошибка при очистке трюма: {e}")
    
    thread = threading.Thread(target=execute_function)
    thread.start()


undock_step_button = tk.Button(
    step_control_frame,
    text="Отстыковка",
    command=step_undock,
    bg="#4CAF50",
    fg="white"
)
undock_step_button.grid(row=1, column=0, padx=5, pady=5, ipadx=5)

dock_step_button = tk.Button(
    step_control_frame,
    text="Пристыковка",
    command=step_dock,
    bg="#2196F3",
    fg="white"
)
dock_step_button.grid(row=1, column=1, padx=5, pady=5, ipadx=5)

warp_belt_step_button = tk.Button(
    step_control_frame,
    text="Варп на бельт",
    command=step_warp_to_belt,
    bg="#FF9800",
    fg="white"
)
warp_belt_step_button.grid(row=1, column=2, padx=5, pady=5, ipadx=5)

mining_step_button = tk.Button(
    step_control_frame,
    text="Сбор руды",
    command=step_mining,
    bg="#9C27B0",
    fg="white"
)
mining_step_button.grid(row=1, column=3, padx=5, pady=5, ipadx=5)

clear_cargo_step_button = tk.Button(
    step_control_frame,
    text="Очистить трюм",
    command=step_clear_cargo,
    bg="#F44336",
    fg="white"
)
clear_cargo_step_button.grid(row=1, column=4, padx=5, pady=5, ipadx=5)

########################################################


def panic_function() -> None:
    logger.warning("Panic! Bring in drones and dock to station")
    panic_button.config(state=tk.DISABLED)

    def execute_function() -> None:
        stop_function()
        activate_eve_window()
        x, y = get_coo_or_error(config.get_mouse_reset_coo(), "mouse_reset_coo")
        pyautogui.moveTo(x, y)
        pyautogui.click(button="left")
        fe.drone_in()
        fe.sleep_and_log(1)
        fe.auto_dock_to_station(config.get_home_coo())
        os._exit(0)

    thread = threading.Thread(target=execute_function, daemon=True)
    thread.start()


def save_properties() -> None:
    config.set_mining_runs(entry.get())
    config.set_undock_coo(undock_coo_entry.get())
    config.set_clear_cargo_coo(clear_cargo_coo_entry.get())
    config.set_mining_hold(mining_hold_entry.get())
    config.set_mining_yield(mining_yield_entry.get())
    config.set_target_one_coo(target_one_coo_entry.get())
    config.set_target_two_coo(target_two_coo_entry.get())
    config.set_mouse_reset_coo(mouse_reset_coo_entry.get())
    config.set_home_coo(home_coo_entry.get())
    config.set_mining_coo(mining_coo_entry.get(1.0, tk.END).strip())
    config.save()
    logger.info("Configuration updated")


def repeat_function(cargo_loading_time: float, start_from_step: str = "undock") -> None:
    disable_fields()
    actual_mining_runs = 0
    mining_runs = config.get_mining_runs()
    update_mining_runs(actual_mining_runs, mining_runs)
    
    step_order = ["undock", "warp", "mining", "dock", "clear_cargo"]
    start_index = step_order.index(start_from_step) if start_from_step in step_order else 0
    
    logger.info(f"Начинаем цикл с этапа: {start_from_step}")
    
    is_first_run = True
    
    while not stop_flag and actual_mining_runs < mining_runs:
        fe.set_next_reset(cargo_loading_time, fe.CARGO_LOAD_TIME)
        loaded_in_str = fe.get_remaining_time(cargo_loading_time)
        logger.info(f"The mining cargo is filled in about {loaded_in_str}")
        time.sleep(1)
        
        if stop_flag:
            break
        
        current_start_index = start_index if is_first_run else 0
        
        # Undock step
        if current_start_index <= step_order.index("undock"):
            activate_eve_window()
            undock_x, undock_y = get_coo_or_error(config.get_undock_coo(), "undock_coo")
            fe.undock(x=undock_x, y=undock_y)
            fe.sleep_and_log(SMALL_SLEEP)
            fe.set_hardener_online(config.get_hardener_keys())
        
        if stop_flag:
            break
        
        rm_x, rm_y = get_coo_or_error(config.get_mouse_reset_coo(), "mouse_reset_coo")
        
        # Warp to belt step
        if current_start_index <= step_order.index("warp"):
            warp_complete_event.clear()
            activate_eve_window()
            item = fe.get_random_coord(config.get_mining_coo())
            fe.click_top_left_circle_menu(item[0], item[1])
            
            logger.info(f"Ожидание завершения варпа на пояс астероидов (таймаут: {warping_time + 10} секунд)...")
            warp_timeout = warping_time + 10
            warp_complete_event.wait(timeout=warp_timeout)
            
            if warp_complete_event.is_set():
                logger.info("Варп завершен по событию - выпускаем дронов для защиты")
            else:
                logger.warning("Событие варпа не получено, используем таймаут")
            
            activate_eve_window()
            fe.drone_out(x=rm_x, y=rm_y)
        
        if stop_flag:
            break
        
        # Mining step
        if current_start_index <= step_order.index("mining"):
            cargo_full_event.clear()
            under_attack_event.clear()
            asteroid_depleted_event.clear()
            tx1, ty1 = get_coo_or_error(config.get_target_one_coo(), "target_one_coo")
            tx2, ty2 = get_coo_or_error(config.get_target_two_coo(), "target_two_coo")
            
            def check_stop_conditions() -> bool:
                if stop_flag:
                    return True
                if cargo_full_event.is_set():
                    logger.warning("Карго заполнено - завершаем майнинг")
                    return True
                if under_attack_event.is_set():
                    logger.warning("Обнаружена атака - завершаем майнинг")
                    return True
                return False
            
            def check_asteroid_depleted() -> bool:
                return asteroid_depleted_event.is_set()
            
            fe.mining_behaviour(
                tx1=tx1,
                ty1=ty1,
                tx2=tx2,
                ty2=ty2,
                mining_reset=config.get_mining_reset_timer(),
                mining_loop=cargo_loading_time,
                rm_x=rm_x,
                rm_y=rm_y,
                unlock_all_targets_keys=config.get_unlock_all_targets_key(),
                activate_eve_window=activate_eve_window,
                is_stopped=check_stop_conditions,
                auto_reset_miners=auto_reset_miners,
                asteroid_depleted=check_asteroid_depleted,
            )
            if not stop_flag:
                activate_eve_window()
                fe.drone_in()
                fe.sleep_and_log(SMALL_SLEEP)
        
        if stop_flag:
            break
        
        # Dock step
        if current_start_index <= step_order.index("dock"):
            logger.info("Собираем дронов перед возвращением на станцию")
            activate_eve_window()
            fe.drone_in()
            fe.sleep_and_log(SMALL_SLEEP)
            activate_eve_window()
            fe.auto_dock_to_station(config.get_home_coo())
            fe.sleep_and_log(LONG_SLEEP)
        
        if stop_flag:
            break
        
        # Clear cargo step
        if current_start_index <= step_order.index("clear_cargo"):
            activate_eve_window()
            cg_x, cg_y = get_coo_or_error(config.get_clear_cargo_coo(), "clear_cargo_coo")
            fe.clear_cargo(x=cg_x, y=cg_y)
        
        actual_mining_runs += 1
        update_mining_runs(actual_mining_runs, mining_runs)
        if take_screenshots:
            img = pyautogui.screenshot()
            now_str = datetime.now().strftime("%d-%m-%Y-%H-%M-%S")
            img.save(f"eve_screenshot_{now_str}.png")
        
        is_first_run = False
    
    total_runs_str = f"{actual_mining_runs}/{mining_runs}"
    logger.info(f"Completed {total_runs_str} mining sessions")
    enable_fields()


def start_function() -> None:
    global stop_flag
    stop_flag = False
    save_properties()
    mining_runs = config.get_mining_runs()
    mining_hold_value = config.get_mining_hold()
    mining_yield_value = config.get_mining_yield()
    mining_reset_timer = config.get_mining_reset_timer()
    start_from = start_from_var.get()
    logger.info("The mining script will run {} mining runs!", mining_runs)
    logger.info("Using miner reset timer of {} seconds.", mining_reset_timer)
    logger.info("Starting from step: {}", start_from)
    cargo_loading_time = get_cargo_loading_time(mining_hold_value, mining_yield_value)
    estimated_run_time = get_estimated_run_time(
        mining_runs=mining_runs,
        cargo_loading_time=cargo_loading_time,
        cargo_loading_time_adjustment=cargo_loading_time_adjustment,
    )
    estimated_run_time_str = fe.get_remaining_time(estimated_run_time)
    logger.info(f"Estimate for completion is {estimated_run_time_str}")
    thread = threading.Thread(
        target=lambda: repeat_function(cargo_loading_time=cargo_loading_time, start_from_step=start_from),
        daemon=True
    )
    thread.start()


start_button.config(command=start_function)
stop_button.config(command=stop_function)
panic_button.config(command=panic_function)
save_button.config(command=save_properties)


def start() -> None:
    logger.info("Starting bot")
    logger.trace("Hi")
    
    init_event_listener()
    
    root.protocol("WM_DELETE_WINDOW", on_closing)
    
    root.mainloop()


def on_closing() -> None:
    logger.info("Закрытие окна бота - остановка всех процессов...")
    global stop_flag
    
    stop_flag = True
    stop_event_listener()
    
    import sys
    import os
    
    try:
        root.quit()
        root.destroy()
    except Exception as e:
        logger.error(f"Ошибка при закрытии окна: {e}")
    
    logger.info("Завершение работы программы...")
    os._exit(0)
