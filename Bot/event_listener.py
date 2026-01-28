import os
import threading
import time
from pathlib import Path
from typing import Callable, Dict, List, Optional
from watchdog.observers import Observer
from watchdog.events import FileSystemEventHandler

from loguru import logger


class EveLogHandler(FileSystemEventHandler):
    def __init__(self, event_callbacks: Dict[str, List[Callable]]):
        self.event_callbacks = event_callbacks
        self.processed_lines = set()
        
    def on_modified(self, event):
        if event.is_directory:
            return
        
        if event.src_path.endswith('.txt'):
            self._process_log_file(event.src_path)
    
    def _process_log_file(self, file_path: str):
        try:
            with open(file_path, 'r', encoding='utf-8', errors='ignore') as f:
                lines = f.readlines()
                for line in lines[-50:]:
                    line_hash = hash(line.strip())
                    if line_hash in self.processed_lines:
                        continue
                    self.processed_lines.add(line_hash)
                    self._check_events(line)
        except Exception as e:
            logger.debug(f"Ошибка при чтении лога {file_path}: {e}")
    
    def _check_events(self, line: str):
        line_lower = line.lower()
        
        event_patterns = {
            'cargo_full': [
                'your cargo hold is full',
                'cargo hold is full',
                'cargo bay is full',
                'not enough space'
            ],
            'under_attack': [
                'you are being attacked',
                'you are taking damage',
                'incoming damage',
                'shield hit',
                'armor hit',
                'hull hit'
            ],
            'warp_complete': [
                'warp drive active',
                'warp complete',
                'arrived at'
            ],
            'docking_accepted': [
                'docking request accepted',
                'docking request granted',
                'docking accepted'
            ],
            'undocking': [
                'undocking',
                'undock complete',
                'leaving station'
            ],
            'mining_complete': [
                'mining complete',
                'finished mining',
                'asteroid depleted'
            ],
            'low_shield': [
                'shield at',
                'shield critical',
                'shield low'
            ],
            'low_armor': [
                'armor at',
                'armor critical',
                'armor low'
            ]
        }
        
        for event_type, patterns in event_patterns.items():
            for pattern in patterns:
                if pattern in line_lower:
                    self._trigger_event(event_type, line)
                    break
    
    def _trigger_event(self, event_type: str, line: str):
        if event_type in self.event_callbacks:
            logger.info(f"Событие обнаружено: {event_type} - {line.strip()[:100]}")
            for callback in self.event_callbacks[event_type]:
                try:
                    callback(event_type, line)
                except Exception as e:
                    logger.error(f"Ошибка в callback для события {event_type}: {e}")


class EveEventListener:
    def __init__(self):
        self.event_callbacks: Dict[str, List[Callable]] = {}
        self.observer: Optional[Observer] = None
        self.log_paths: List[Path] = []
        self.is_running = False
        self.handler: Optional[EveLogHandler] = None
        
    def find_eve_log_directory(self) -> Optional[Path]:
        possible_paths = []
        
        if os.name == 'nt':
            user_profile = os.environ.get('USERPROFILE', '')
            if user_profile:
                possible_paths.extend([
                    Path(user_profile) / 'Documents' / 'EVE' / 'logs',
                    Path(user_profile) / 'Documents' / 'EVE' / 'logs' / 'ChatLog',
                    Path(user_profile) / 'Documents' / 'EVE' / 'logs' / 'Gamelog',
                ])
        
        home = os.path.expanduser('~')
        possible_paths.extend([
            Path(home) / 'Documents' / 'EVE' / 'logs',
            Path(home) / '.local' / 'share' / 'EVE' / 'logs',
        ])
        
        for path in possible_paths:
            if path.exists() and path.is_dir():
                logger.info(f"Найдена папка логов Eve: {path}")
                return path
        
        logger.warning("Папка логов Eve не найдена. Проверьте путь вручную.")
        return None
    
    def register_event(self, event_type: str, callback: Callable):
        if event_type not in self.event_callbacks:
            self.event_callbacks[event_type] = []
        self.event_callbacks[event_type].append(callback)
        logger.info(f"Зарегистрирован callback для события: {event_type}")
    
    def unregister_event(self, event_type: str, callback: Callable):
        if event_type in self.event_callbacks:
            if callback in self.event_callbacks[event_type]:
                self.event_callbacks[event_type].remove(callback)
    
    def start(self, log_directory: Optional[Path] = None):
        if self.is_running:
            logger.warning("Слушатель событий уже запущен")
            return
        
        if log_directory is None:
            log_directory = self.find_eve_log_directory()
        
        if log_directory is None:
            logger.error("Не удалось найти папку логов Eve Online")
            return False
        
        self.handler = EveLogHandler(self.event_callbacks)
        self.observer = Observer()
        self.observer.schedule(self.handler, str(log_directory), recursive=True)
        self.observer.start()
        self.is_running = True
        
        logger.info(f"Слушатель событий Eve Online запущен. Мониторинг: {log_directory}")
        
        self._process_existing_logs(log_directory)
        
        return True
    
    def _process_existing_logs(self, log_directory: Path):
        try:
            for log_file in log_directory.rglob('*.txt'):
                if log_file.is_file():
                    self.handler._process_log_file(str(log_file))
        except Exception as e:
            logger.debug(f"Ошибка при обработке существующих логов: {e}")
    
    def stop(self):
        if not self.is_running:
            return
        
        if self.observer:
            self.observer.stop()
            self.observer.join()
        
        self.is_running = False
        logger.info("Слушатель событий Eve Online остановлен")
    
    def is_active(self) -> bool:
        return self.is_running and self.observer and self.observer.is_alive()
