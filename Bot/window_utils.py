import pyautogui
from typing import Optional, Tuple, List
from loguru import logger
import pygetwindow as gw


def get_eve_window_position(window_title: str = "EVE -") -> Optional[Tuple[int, int, int, int]]:
    """
    Получает позицию и размер окна EVE Online.
    
    Returns:
        Tuple[left, top, width, height] или None если окно не найдено
    """
    try:
        windows = gw.getWindowsWithTitle(window_title)
        if windows:
            window = windows[0]
            return (window.left, window.top, window.width, window.height)
        return None
    except Exception as e:
        logger.error(f"Ошибка при получении позиции окна: {e}")
        return None


def get_eve_window_rect(window_title: str = "EVE -") -> Optional[dict]:
    """
    Получает полную информацию об окне EVE Online.
    
    Returns:
        Dict с ключами: left, top, right, bottom, width, height, center_x, center_y
    """
    try:
        windows = gw.getWindowsWithTitle(window_title)
        if windows:
            window = windows[0]
            return {
                'left': window.left,
                'top': window.top,
                'right': window.left + window.width,
                'bottom': window.top + window.height,
                'width': window.width,
                'height': window.height,
                'center_x': window.left + window.width // 2,
                'center_y': window.top + window.height // 2
            }
        return None
    except Exception as e:
        logger.error(f"Ошибка при получении информации об окне: {e}")
        return None


def screenshot_eve_window(window_title: str = "EVE -") -> Optional[pyautogui.Image]:
    """
    Делает скриншот окна EVE Online.
    
    Returns:
        PIL Image или None если окно не найдено
    """
    try:
        rect = get_eve_window_rect(window_title)
        if rect:
            screenshot = pyautogui.screenshot(region=(
                rect['left'],
                rect['top'],
                rect['width'],
                rect['height']
            ))
            return screenshot
        return None
    except Exception as e:
        logger.error(f"Ошибка при создании скриншота окна: {e}")
        return None


def convert_screen_to_window_coords(screen_x: int, screen_y: int, window_title: str = "EVE -") -> Optional[Tuple[int, int]]:
    """
    Конвертирует экранные координаты в координаты относительно окна EVE.
    
    Returns:
        Tuple[window_x, window_y] или None
    """
    try:
        rect = get_eve_window_rect(window_title)
        if rect:
            window_x = screen_x - rect['left']
            window_y = screen_y - rect['top']
            return (window_x, window_y)
        return None
    except Exception as e:
        logger.error(f"Ошибка при конвертации координат: {e}")
        return None


def convert_window_to_screen_coords(window_x: int, window_y: int, window_title: str = "EVE -") -> Optional[Tuple[int, int]]:
    """
    Конвертирует координаты относительно окна EVE в экранные координаты.
    
    Returns:
        Tuple[screen_x, screen_y] или None
    """
    try:
        rect = get_eve_window_rect(window_title)
        if rect:
            screen_x = rect['left'] + window_x
            screen_y = rect['top'] + window_y
            return (screen_x, screen_y)
        return None
    except Exception as e:
        logger.error(f"Ошибка при конвертации координат: {e}")
        return None


def find_image_in_eve_window(image_path: str, window_title: str = "EVE -", confidence: float = 0.8) -> Optional[Tuple[int, int]]:
    """
    Ищет изображение внутри окна EVE Online.
    
    Args:
        image_path: Путь к изображению для поиска
        window_title: Заголовок окна EVE
        confidence: Уровень уверенности (0.0-1.0)
    
    Returns:
        Tuple[screen_x, screen_y] центра найденного изображения или None
    """
    try:
        screenshot = screenshot_eve_window(window_title)
        if screenshot:
            location = pyautogui.locateOnScreen(image_path, confidence=confidence, region=(
                get_eve_window_rect(window_title)['left'],
                get_eve_window_rect(window_title)['top'],
                get_eve_window_rect(window_title)['width'],
                get_eve_window_rect(window_title)['height']
            ))
            if location:
                center = pyautogui.center(location)
                return (center.x, center.y)
        return None
    except Exception as e:
        logger.debug(f"Изображение не найдено в окне: {e}")
        return None


def get_all_eve_windows() -> List[gw.Window]:
    """
    Получает список всех окон EVE Online.
    
    Returns:
        Список объектов Window
    """
    try:
        return gw.getWindowsWithTitle("EVE -")
    except Exception as e:
        logger.error(f"Ошибка при получении списка окон: {e}")
        return []


def is_eve_window_active(window_title: str = "EVE -") -> bool:
    """
    Проверяет, активно ли окно EVE Online.
    
    Returns:
        True если окно активно
    """
    try:
        windows = gw.getWindowsWithTitle(window_title)
        if windows:
            return windows[0].isActive
        return False
    except Exception as e:
        logger.error(f"Ошибка при проверке активности окна: {e}")
        return False
