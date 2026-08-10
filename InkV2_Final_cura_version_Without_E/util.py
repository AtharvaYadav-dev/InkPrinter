import os
import sys
import collections
import logging
import traceback
from pathlib import Path
from configparser import ConfigParser
from datetime import datetime
from typing import Optional

class CallbackHandler(object):
    handlers = None

    def __init__(self):
        self.handlers = collections.defaultdict(set)

    def register(self, event, callback):
        self.handlers[event].add(callback)

    def fire(self, event, **kwargs):
        for handler in self.handlers.get(event, []):
            handler(**kwargs)


class FileHandler():
    def __init__(self):
        self.cwd = Path.cwd()
            
    def getCWD(self):
        return self.cwd

    def getPath(self, dir=None, file=None):
        path = ""
        if dir and file:
            path = Path(dir, file)
        
        else:
            if dir:
                path = Path(self.cwd, dir)

            if file:
                path = Path(self.cwd, file)
        
        return path
    
    def makeDir(self, directory):
        if directory:
            dir_path = Path(self.cwd, directory)
            os.mkdir(dir_path)

    def checkDir(self, directory):
        if directory:
            dir_path = Path(self.cwd, directory)
            if not os.path.isdir(dir_path):
                    os.mkdir(dir_path)      


class ConfigHandler():
    def __init__(self):
        self.ini_parser = ConfigParser()

    def updateFile(self, config_path):
        with open(config_path, 'w') as configfile:
            self.ini_parser.write(configfile)

    def addParameter(self, section, key, value):
        if self.ini_parser.has_section(section):
            self.ini_parser.set(section, key, value)
        
        else:
            self.ini_parser[section] = {key : value}

    def getSection(self, section):
        if self.ini_parser.has_section(section):
            return dict(self.ini_parser.items(section))

    def getValues(self, section, key):
        if self.ini_parser.has_section(section):
            if self.ini_parser.has_option(section, key):
                return self.ini_parser.get(section, key)


class AppLogger():
    def __init__(self, 
                 logger_name = __name__,
                 log_file = "app.log",
                 log_level = "DEBUG",
                 log_format = "{asctime} - {levelname} - {message}",
                 date_format = "%Y-%m-%d %H:%M",
                 file_mode = "a",
                 encoding = "utf-8",
                 max_file_size = None,
                 backup_count = 5):
        
        self.logger_name = logger_name
        self.log_file = log_file
        self.log_level = log_level
        self.log_format = log_format
        self.date_format = date_format
        self.file_mode = file_mode
        self.encoding = encoding
        self.max_file_size = max_file_size
        self.backup_count = backup_count
        
        # Create the logger instance
        self.logger = self._setup_logger()

    def _setup_logger(self):

        # Create logger
        logger = logging.getLogger(self.logger_name)
        logger.setLevel(self.log_level)
        
        # Avoid adding multiple handlers if logger already exists
        if logger.handlers:
            return logger
        
        # Create formatter
        formatter = logging.Formatter(
            self.log_format,
            style="{",
            datefmt=self.date_format
        )
        
        # Create file handler (with rotation if specified)
        if self.max_file_size:
            from logging.handlers import RotatingFileHandler
            file_handler = RotatingFileHandler(
                self.log_file,
                mode=self.file_mode,
                maxBytes=self.max_file_size,
                backupCount=self.backup_count,
                encoding=self.encoding
            )
        else:
            file_handler = logging.FileHandler(
                self.log_file,
                mode=self.file_mode,
                encoding=self.encoding
            )
        
        # Set formatter and add handler
        file_handler.setFormatter(formatter)
        logger.addHandler(file_handler)
        
        # --- Error Logs Setup ---
        # Create 'error_logs' folder in the same directory as log_file
        log_dir = os.path.dirname(os.path.abspath(self.log_file))
        error_log_dir = os.path.join(log_dir, "error_logs")
        os.makedirs(error_log_dir, exist_ok=True)
        
        # Create a timestamped error log filename
        timestamp = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
        base_name = os.path.basename(self.log_file)
        name, ext = os.path.splitext(base_name)
        error_log_file = os.path.join(error_log_dir, f"{name}_error_{timestamp}{ext}")
        
        # Add error handler
        error_file_handler = logging.FileHandler(
            error_log_file,
            mode=self.file_mode,
            encoding=self.encoding
        )
        error_file_handler.setLevel(logging.ERROR)
        
        # Detailed formatter for errors, including proper timestamp
        error_formatter = logging.Formatter(
            "{asctime} - {levelname} - {filename}:{lineno} - {message}",
            style="{",
            datefmt="%Y-%m-%d %H:%M:%S"
        )
        error_file_handler.setFormatter(error_formatter)
        logger.addHandler(error_file_handler)
        
        # Catch unhandled exceptions and log them
        def handle_exception(exc_type, exc_value, exc_traceback):
            if issubclass(exc_type, KeyboardInterrupt):
                sys.__excepthook__(exc_type, exc_value, exc_traceback)
                return
            logger.error("Uncaught exception", exc_info=(exc_type, exc_value, exc_traceback))
        
        sys.excepthook = handle_exception
        # ------------------------
        
        return logger
    
    def get_logger(self):
        return self.logger
    
    def debug(self, message):
        self.logger.debug(message)
    
    def info(self, message):
        self.logger.info(message)
    
    def warning(self, message):
        self.logger.warning(message)
    
    def error(self, message):
        self.logger.error(message)
    
    def critical(self, message):
        self.logger.critical(message)
    
    def logUiAction(self, action, widget_name = "", details = ""):

        message = f"UI Action: {action}"
        if widget_name:
            message += f" | Widget: {widget_name}"
        if details:
            message += f" | Details: {details}"
        
        self.logger.info(message)
    
    def logErrorTraceback(self, error, context = ""):
        message = f"Error occurred"
        if context:
            message += f" in {context}"
        message += f": {str(error)}"
        
        self.logger.error(message)
        self.logger.error(f"Traceback: {traceback.format_exc()}")
    
    def sessionSeparator(self, position):
        """Add a separator to mark the start of a new session."""
        separator = "=" * 50
        timestamp = datetime.now().strftime(self.date_format)
        self.logger.info(f"{separator}")
        self.logger.info(f"New session {position} at {timestamp}")
        self.logger.info(f"{separator}")


class Utils():
    def __init__(self):
        self.debugFlag = False
        self.debugflag = [False]    # flag to print debug info
        self.msg_list = []

    def setDebugMsgFlag(self, setFlag):
        self.debugflag[0] = setFlag

    def debugMsg(self, text):
        if self.debugflag[0]:
            print(text)
            
    def debugPrint(self, msg):
        if self.debugFlag:
            print(msg)            

    def putMessage(self, *args):
        for msg in args:
            self.msg_list.append(msg)

    def getMessage(self):
        return self.msg_list

    def clearMessage(self):
        self.msg_list = []

    def argIsNotNone(*args):
        return all(arg is not None for arg in args)
    
    def checkSubString(self, string, *substrings):
        sub_list = []
        
        for sub in substrings:
            sub_list.append(sub)
            
        return any(sub in string for sub in sub_list)

def fileRead(path):
    """Write content to a file at the specified path."""
    with open(path, "r", encoding="utf-8") as f:
        content = f.read()
        print(content)

def fileWrite(path, content, mode="a"):
    """Write content to a file at the specified path."""
    with open(path, mode, encoding="utf-8") as f:
        f.write(content + "\n")


def writeLog(logfile, message):
    """Write log messages to file with timestamps and print to console."""
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    full_msg = f"[{timestamp}] {message}"
    print(full_msg)
    fileWrite(logfile, full_msg, mode="a")

if __name__ == "__main__":
    pos_list = ['X:1.00', 'Y:20.00', 'Z:12.00', 'E:0.00']

    pos = [pos.split(':') for pos in pos_list]
    print(f"pos : {pos}")

