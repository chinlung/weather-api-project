import os
import sys
import logging
from typing import Optional

# 設定日誌目錄
LOGS_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "logs")
os.makedirs(LOGS_DIR, exist_ok=True)

# 日誌檔案路徑
WEATHER_API_LOG = os.path.join(LOGS_DIR, "weather_api.log")
API_REQUESTS_LOG = os.path.join(LOGS_DIR, "api_requests.log")
SERVER_LOG = os.path.join(LOGS_DIR, "server.log")
WARNINGS_LOG = os.path.join(LOGS_DIR, "warnings.log")
FORECAST_LOG = os.path.join(LOGS_DIR, "forecast.log")
OBSERVATION_LOG = os.path.join(LOGS_DIR, "observation.log")

# 日誌格式
DEFAULT_FORMAT = '%(asctime)s - %(name)s - %(levelname)s - %(message)s'
CONSOLE_FORMAT = '[%(asctime)s] %(levelname)-8s %(message)s'
CONSOLE_DATE_FORMAT = '%m/%d/%y %H:%M:%S'

def setup_logger(name: str, log_file: Optional[str] = None, level: int = logging.INFO, 
                 console_level: int = logging.INFO, file_level: int = logging.DEBUG) -> logging.Logger:
    """設定並返回一個配置好的日誌記錄器

    Args:
        name: 日誌記錄器名稱
        log_file: 日誌檔案路徑，如果為 None 則不記錄到檔案
        level: 日誌記錄器的整體日誌級別
        console_level: 控制台處理器的日誌級別
        file_level: 檔案處理器的日誌級別

    Returns:
        配置好的日誌記錄器
    """
    logger = logging.getLogger(name)
    logger.setLevel(level)
    
    # 清除現有處理器
    if logger.handlers:
        logger.handlers.clear()
    
    # 添加控制台處理器
    console_handler = logging.StreamHandler(sys.stderr)
    console_handler.setLevel(console_level)
    console_formatter = logging.Formatter(CONSOLE_FORMAT, CONSOLE_DATE_FORMAT)
    console_handler.setFormatter(console_formatter)
    logger.addHandler(console_handler)
    
    # 如果指定了日誌檔案，添加檔案處理器
    if log_file:
        file_handler = logging.FileHandler(log_file, encoding="utf-8")
        file_handler.setLevel(file_level)
        file_formatter = logging.Formatter(DEFAULT_FORMAT)
        file_handler.setFormatter(file_formatter)
        logger.addHandler(file_handler)
    
    return logger

# 預設日誌記錄器
weather_api_logger = setup_logger("weather_api", WEATHER_API_LOG, level=logging.DEBUG)
api_requests_logger = setup_logger("weather_api_requests", API_REQUESTS_LOG, level=logging.DEBUG)
server_logger = setup_logger("taiwan-weather-mcp", SERVER_LOG, level=logging.INFO)
warnings_logger = setup_logger("weather_warnings", WARNINGS_LOG, level=logging.DEBUG)
forecast_logger = setup_logger("weather_forecast", FORECAST_LOG, level=logging.DEBUG)
observations_logger = setup_logger("weather_observation", OBSERVATION_LOG, level=logging.DEBUG)
