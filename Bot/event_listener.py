import os
import re
import threading
import time
from pathlib import Path
from typing import Callable, Dict, List, Optional

from loguru import logger


class EveLogHandler:
    def __init__(self, event_callbacks: Dict[str, List[Callable]]):
        self.event_callbacks = event_callbacks
        self.processed_lines = set()
        self.file_positions: Dict[str, int] = {}
        
    def _process_log_file(self, file_path: str):
        try:
            file_name = Path(file_path).name.lower()
            
            if 'chatlog' in file_name and 'gamelog' not in file_name:
                return
            
            current_position = self.file_positions.get(file_path, 0)
            
            with open(file_path, 'r', encoding='utf-8', errors='ignore') as f:
                f.seek(current_position)
                new_lines = f.readlines()
                
                if new_lines:
                    self.file_positions[file_path] = f.tell()
                    
                    for line in new_lines:
                        line_stripped = line.strip()
                        if not line_stripped:
                            continue
                        
                        line_hash = hash(line_stripped)
                        if line_hash in self.processed_lines:
                            continue
                        self.processed_lines.add(line_hash)
                        
                        if '(mining)' in line or '(notify)' in line:
                            self._check_events(line_stripped)
        except Exception as e:
            logger.debug(f"Ошибка при чтении лога {file_path}: {e}")
    
    def _check_events(self, line: str):
        line_lower = line.lower()
        line_clean = re.sub(r'<[^>]+>', '', line_lower)
        line_clean = re.sub(r'\*', '', line_clean)
        line_clean = re.sub(r'\s+', ' ', line_clean).strip()
        
        cargo_full_patterns = [
            'your cargo hold is full',
            'cargo hold is full',
            'cargo bay is full',
            'not enough space',
            'ваш грузовой отсек полон',
            'грузовой отсек полон',
            'недостаточно места'
        ]
        
        if any(pattern in line_clean for pattern in cargo_full_patterns):
            logger.debug(f"Обнаружен паттерн заполнения карго в строке: {line_clean[:100]}")
            self._trigger_event('cargo_full', line)
            return
        
        if 'завершил функционирование' in line_clean and ('грузовой отсек полон' in line_clean or 'cargo' in line_clean):
            logger.debug(f"Обнаружена комбинация паттернов заполнения карго в строке: {line_clean[:100]}")
            self._trigger_event('cargo_full', line)
            return
        
        event_patterns = {
            'cargo_full': [],
            'under_attack': [
                'you are being attacked',
                'you are taking damage',
                'incoming damage',
                'shield hit',
                'armor hit',
                'hull hit',
                'вы под действием',
                'вы получили урон',
                'входящий урон',
                'щит поврежден',
                'броня повреждена',
                'корпус поврежден',
                'из.*попал',
                'из.*пробил',
                'из.*раздробил'
            ],
            'warp_complete': [
                'warp drive active',
                'warp complete',
                'arrived at',
                'варп активен',
                'варп завершен',
                'прибыл в',
                'корабль прибыл в место назначения'
            ],
            'docking_accepted': [
                'docking request accepted',
                'docking request granted',
                'docking accepted',
                'запрос на стыковку принят',
                'стыковка принята',
                'разрешена стыковка'
            ],
            'undocking': [
                'undocking',
                'undock complete',
                'leaving station',
                'отстыковка',
                'отстыковка завершена',
                'покидание станции'
            ],
            'mining_complete': [
                'mining complete',
                'finished mining',
                'asteroid depleted',
                'майнинг завершен',
                'закончен майнинг',
                'астероид истощен',
                'деактивируется, так как добываемый им ресурс обращен в пыль',
                'деактивируется',
                'ресурс обращен в пыль',
                'обращен в пыль'
            ],
            'low_shield': [
                'shield at',
                'shield critical',
                'shield low',
                'щит на',
                'щит критический',
                'щит низкий'
            ],
            'low_armor': [
                'armor at',
                'armor critical',
                'armor low',
                'броня на',
                'броня критическая',
                'броня низкая'
            ]
        }
        
        for event_type, patterns in event_patterns.items():
            for pattern in patterns:
                if '*' in pattern:
                    regex_pattern = pattern.replace('*', '.*')
                    if re.search(regex_pattern, line_clean, re.IGNORECASE):
                        self._trigger_event(event_type, line)
                        break
                elif pattern in line_clean:
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
        self.log_paths: List[Path] = []
        self.is_running = False
        self.handler: Optional[EveLogHandler] = None
        self.monitor_thread: Optional[threading.Thread] = None
        self.stop_monitoring = False
        
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
    
    def _monitor_logs(self, log_directory: Path):
        processed_files = set()
        
        while not self.stop_monitoring:
            try:
                log_files = []
                
                gamelog_dir = log_directory / 'Gamelog'
                if gamelog_dir.exists():
                    log_files.extend(gamelog_dir.glob('*.txt'))
                
                log_files.extend(log_directory.glob('*.txt'))
                
                for log_file in log_files:
                    if log_file.is_file() and self.handler:
                        file_path_str = str(log_file)
                        if file_path_str not in processed_files:
                            logger.debug(f"Мониторинг файла лога: {log_file.name}")
                            processed_files.add(file_path_str)
                        self.handler._process_log_file(file_path_str)
            except Exception as e:
                logger.debug(f"Ошибка при мониторинге логов: {e}")
            
            time.sleep(1)
    
    def start(self, log_directory: Optional[Path] = None):
        if self.is_running:
            logger.warning("Слушатель событий уже запущен")
            return False
        
        if log_directory is None:
            log_directory = self.find_eve_log_directory()
        
        if log_directory is None:
            logger.error("Не удалось найти папку логов Eve Online")
            return False
        
        self.handler = EveLogHandler(self.event_callbacks)
        self.stop_monitoring = False
        self.is_running = True
        
        self.monitor_thread = threading.Thread(
            target=self._monitor_logs,
            args=(log_directory,),
            daemon=True
        )
        self.monitor_thread.start()
        
        gamelog_path = log_directory / 'Gamelog'
        if gamelog_path.exists():
            logger.info(f"Слушатель событий Eve Online запущен. Мониторинг: {gamelog_path}")
        else:
            logger.info(f"Слушатель событий Eve Online запущен. Мониторинг: {log_directory}")
            logger.warning("Папка Gamelog не найдена, будут читаться все .txt файлы из корня папки логов")
        
        return True
    
    def stop(self):
        if not self.is_running:
            return
        
        self.stop_monitoring = True
        self.is_running = False
        
        if self.monitor_thread and self.monitor_thread.is_alive():
            self.monitor_thread.join(timeout=2)
        
        logger.info("Слушатель событий Eve Online остановлен")
    
    def is_active(self) -> bool:
        return self.is_running and not self.stop_monitoring
