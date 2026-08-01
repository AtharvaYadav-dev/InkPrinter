import os
import sys
import math
import re
import webbrowser
import json


from ui_interface import *
from Custom_Widgets.Widgets import *
from PySide6.QtCore import QTimer, QRegularExpression, Signal, Slot, Qt, QThread, QEvent, QEventLoop
from PySide6.QtGui import QIcon, QCloseEvent, QIntValidator, QDoubleValidator, QRegularExpressionValidator
from PySide6.QtWidgets import (
    QFileDialog, QMessageBox, QComboBox, QPushButton, 
    QLineEdit, QLabel, QTextEdit, QWidget,
    QHBoxLayout
)

from com import SerialCom
from util import CallbackHandler, FileHandler, ConfigHandler, AppLogger, Utils
from gcode import GcodeHandler
from custom import CustomMessageBox
from gcode_parser import GcodeParser
from preview3d import GCode3DPreview
from uihandler import AxisHandler, LaserHandler, WidgetHandler, WidgetManger, DictAsClass
from pathlib import Path
from svg_to_gcode import convert as convert_svg_to_gcode_module
from dxf_to_gcode import convert as convert_dxf_to_gcode_module
from bmp_to_gcode import convert as convert_bmp_to_gcode_module
from cura_finder_log1 import checkCuraStatus, copyDefFiles, isCuraSupported
from config_manager import load_profile, ensure_profile_exists, PROFILE_PATH
                    
                    
class MainWindow(QMainWindow):
    sigPrintProgress = Signal(float)
    exceptionOccurred = Signal(str)

    def __init__(self, parent=None):
        QMainWindow.__init__(self)
        self.ui = Ui_MainWindow()
        self.ui.setupUi(self)

        # Add placeholder text to specific QComboBoxes
        if hasattr(self.ui, 'userComboBox'):
            self.ui.userComboBox.setPlaceholderText("Select User")
            self.ui.userComboBox.setCurrentIndex(-1)
        if hasattr(self.ui, 'portComboBox'):
            self.ui.portComboBox.setPlaceholderText("Select COM Port")
            self.ui.portComboBox.setCurrentIndex(-1)
        if hasattr(self.ui, 'baudComboBox'):
            self.ui.baudComboBox.setPlaceholderText("Select Baudrate")
            self.ui.baudComboBox.setCurrentIndex(-1)
        if hasattr(self.ui, 'exposureComboBox'):
            self.ui.exposureComboBox.setPlaceholderText("Select Exposure")
            self.ui.exposureComboBox.setCurrentIndex(-1)
        if hasattr(self.ui, 'expdurationComboBox'):
            self.ui.expdurationComboBox.setPlaceholderText("Select Duration")
            self.ui.expdurationComboBox.setCurrentIndex(-1)
        
        loadJsonStyle(self, self.ui)

        self.msgbox = CustomMessageBox(self)

        # notify menu widgets
        self.notifyMenu = self.findChild(QCustomSlideMenu, "notifyContainer")
        self.notifyMenuBtn1 = self.findChild(QPushButton, "closeNotifyPushButton")
        self.notifyLabel = self.findChild(QLabel, "notifyLabel")
        self.notifyTextEdit = self.findChild(QTextEdit, "notifyTextEdit")
        self.notifySubContainer = self.findChild(QWidget, "notifySubContainer")

        if self.notifyTextEdit:
            self.notifyTextEdit.setReadOnly(True)

        # Apply Premium CSS for the notification container
        if self.notifySubContainer:
            self.notifySubContainer.layout().setContentsMargins(0, 0, 0, 0)
            self.notifySubContainer.setStyleSheet("""
                QWidget#notifySubContainer {
                    background-color: rgb(167, 198, 229); 
                    color: rgb(16, 42, 83); 
                    border-radius: 15px;
                    border: 2px solid rgb(16, 42, 131);
                }
            """)
        if self.notifyLabel:
            self.notifyLabel.setMinimumHeight(35)
            self.notifyLabel.setStyleSheet("""
                QLabel {
                    background-color: rgb(16, 42, 131); 
                    color: white; 
                    font-weight: bold; 
                    font-size: 14px; 
                    padding-left: 15px; 
                    border-top-left-radius: 13px; 
                    border-top-right-radius: 13px;
                    border-bottom-left-radius: 0px;
                    border-bottom-right-radius: 0px;
                }
            """)
        if self.notifyTextEdit:
             self.notifyTextEdit.setStyleSheet("""
                QTextEdit {
                    background-color: transparent; 
                    color: rgb(16, 42, 83); 
                    border: none; 
                    font-size: 13px; 
                    padding: 10px 15px;
                }
             """)

        # Increase size limits to accommodate buttons
        if self.notifyMenu:
            self.notifyMenu.setMaximumHeight(180)
        if self.notifySubContainer:
            self.notifySubContainer.setMaximumHeight(180)

        # --- Notification System Setup ---
        self.popupLoop = QEventLoop(self)
        self.popupResult = QMessageBox.Ok

        # Container for buttons
        if self.notifySubContainer:
            self.notifyBtnContainer = QWidget(self.notifySubContainer)
            self.notifyBtnContainer.setStyleSheet("background-color: transparent;")
            self.notifyBtnLayout = QHBoxLayout(self.notifyBtnContainer)
            self.notifyBtnLayout.setContentsMargins(0, 0, 0, 5)
            self.notifyBtnLayout.setSpacing(10)
            self.notifyBtnLayout.setAlignment(Qt.AlignCenter)

            self.notifySubContainer.layout().addWidget(self.notifyBtnContainer)

            self.btnOk = QPushButton("OK")
            self.btnYes = QPushButton("Yes")
            self.btnNo = QPushButton("No")
            self.btnCancel = QPushButton("Cancel")

            btn_style = """
                QPushButton {
                    background-color: rgb(16, 42, 131);
                    color: white;
                    border: 1px solid rgb(16, 42, 131);
                    border-radius: 8px;
                    padding: 6px 20px;
                    font-weight: bold;
                    font-size: 12px;
                }
                QPushButton:hover {
                    background-color: rgb(40, 70, 160);
                    color: white;
                }
                QPushButton:pressed {
                    background-color: rgb(10, 30, 100);
                }
            """

            for btn in [self.btnOk, self.btnYes, self.btnNo, self.btnCancel]:
                btn.setStyleSheet(btn_style)
                btn.hide()
                self.notifyBtnLayout.addWidget(btn)

            self.btnOk.clicked.connect(lambda: self.onPopupBtnClicked(QMessageBox.Ok))
            self.btnYes.clicked.connect(lambda: self.onPopupBtnClicked(QMessageBox.Yes))
            self.btnNo.clicked.connect(lambda: self.onPopupBtnClicked(QMessageBox.No))
            self.btnCancel.clicked.connect(lambda: self.onPopupBtnClicked(QMessageBox.Cancel))

        missing_files = checkCuraStatus()

        if missing_files:
            self.showCustomPopup(
                "Cura Setup Required",
                "Required Cura configuration files are missing.\n"
                "Click OK to run the Cura Fixer tool with Administrator privileges."
            )

            import subprocess
            # --------------------------
            # Detect packaged .EXE or .PY
            # --------------------------
            if getattr(sys, 'frozen', False):
                # Running as EXE -> use bundled fixer EXE
                fixer_exe = os.path.join(os.path.dirname(sys.executable), "cura_finder_log1.exe")

                if not os.path.exists(fixer_exe):   
                    self.showCustomPopup("Error", f"Cura Fixer EXE not found:\n{fixer_exe}")
                else:
                    # Run EXE normally
                    subprocess.Popen([fixer_exe], shell=True)

            else:
                # Running from Python source
                subprocess.Popen([sys.executable, "cura_finder_log1.py"], shell=True)

     
        selected_version, bad_versions = isCuraSupported()

        if not selected_version:
            self.showCustomPopup(
                "Unsupported Cura Version",
                "No compatible Cura version was found.\n\n"
                "Installed Cura versions:\n"
                + ("\n".join(bad_versions) if bad_versions else "None") +
                "\n\nVersion required: Ultimaker Cura 5.9.1\n\n"
                "Click OK to download."
            )

            # Open download page after popup
            webbrowser.open("https://github.com/Ultimaker/Cura/releases/tag/5.9.1")

            sys.exit(0)

        # Approved version
        print(f"Cura version selected for Slicing: {selected_version}")
        
        # Module and Class instances
        self.sercom = SerialCom()
        self.blackpill_sercom = SerialCom()
        self.fh = FileHandler()
        self.conf = ConfigHandler()
        self.cb = CallbackHandler()
        self.gcode = GcodeHandler()
        self.gcode_parser = GcodeParser()
        self.util = Utils()
        self.msgbox = CustomMessageBox(self)
        self.logger = AppLogger(logger_name="UILogger", log_file="app.log", log_level="DEBUG")
        self.wm = WidgetManger()

        self.util.debugFlag = True

        self.exceptionOccurred.connect(self.showExceptionPopup)

        # variables
        self.jogfeed = 1000
        self.xcenter = 60
        self.ycenter = 65
        self.zcenter = 35
        self.travel = 10
        self.jogcmd = None
        
        self.pgm_file = None
        self.pgm_height = None
        self.pgm_laser = None
        self.pgm_glist = []
        self.pgm_mlist = []
        self.pgm_index = 0
        self.seg_index  = 0
        self.mark_flag = False
        
        self.gcode_ack = None
        
        self.pause_flag = False
        self.pgm_run_flag = False
        self.pgm_pause_flag = False
        self.pgm_abort_flag = False
        self.progress = 0
        self.prev_segment = 0
        
        self.laserhandler = LaserHandler()
        self.laser_name = None
        self.zero_laser = None
        self.offset_laser = None
        self.focus = 0

        self.xindex = 0
        self.yindex = 0
        self.offset = 0
        self.zero_flag = False
        self.xtemp = 0
        self.ytemp = 0
        self.travel_index = 0

        self.step_list = [1, 5, 10, 50]
        self.step_index = 0      
        self.current_step = 1

        self.release_flag = False           # machine free

        self.offset_user_set = False  # track if user actually set offsets
        self.x_offset = 0.0
        self.y_offset = 0.0
        

        self.temp_report_hide_flag = False
        
        self.axishandler = AxisHandler()
        self.preview = GCode3DPreview()
        self.preview.sigGlError.connect(lambda msg: print("⚠️", msg))

        # log file session separator
        self.logger.sessionSeparator("START")

        # initialize the ini file
        self.initConfig()
        self.logger.info("INI file initialized")
        
        # UI related variables
        self.centerMenuActiveBtn = None
        
        # com widget
        self.comCombo1 = self.findChild(QComboBox, "portComboBox")
        self.comCombo2 = self.findChild(QComboBox, "baudComboBox")
        self.comBtn1 = self.findChild(QPushButton, "connectPushButton")
        self.comBtn2 = self.findChild(QPushButton, "refreshPushButton")
        
        self.com_dict = {self.comCombo1.objectName() : "port",
                         self.comCombo2.objectName() : "baud",
                         self.comBtn1.objectName() : "connect",
                         self.comBtn2.objectName() : "refresh",
                         "port" : self.comCombo1,
                         "baud" : self.comCombo2,
                         "connect" : self.comBtn1,
                         "refresh" : self.comBtn2,
                         "conf" : "com",
                         "object" : "sercom"
                         }
        
        self.com = DictAsClass(self.com_dict)

        # black com widget
        self.blackComCombo1 = self.findChild(QComboBox, "blackportComboBox")
        self.blackComCombo2 = self.findChild(QComboBox, "blackbaudComboBox")
        self.blackComBtn1 = self.findChild(QPushButton, "blackconnectPushButton")
        self.blackComBtn2 = self.findChild(QPushButton, "blackrefreshPushButton")
        
        self.black_com_dict = {self.blackComCombo1.objectName() : "port",
                               self.blackComCombo2.objectName() : "baud",
                               self.blackComBtn1.objectName() : "connect",
                               self.blackComBtn2.objectName() : "refresh",
                               "port" : self.blackComCombo1,
                               "baud" : self.blackComCombo2,
                               "connect" : self.blackComBtn1,
                               "refresh" : self.blackComBtn2,
                               "conf" : "black_com",
                               "object" : "blackpill_sercom"
                               }
        
        self.black_com = DictAsClass(self.black_com_dict)

        # left menu widgets
        self.leftMenuBtn1 = self.findChild(QPushButton, "homePushButton")
        self.leftMenuBtn2 = self.findChild(QPushButton, "laserPushButton")
        self.leftMenuBtn3 = self.findChild(QPushButton, "programsPushButton")
        self.leftMenuBtn4 = self.findChild(QPushButton, "printPushButton")
        self.leftMenuBtn5 = self.findChild(QPushButton, "terminalPushButton")
        
        self.leftMenuWidget_dict = {self.leftMenuBtn1.objectName() : "home",
                                    self.leftMenuBtn2.objectName() : "laser",
                                    self.leftMenuBtn3.objectName() : "programs",
                                    self.leftMenuBtn4.objectName() : "print",
                                    self.leftMenuBtn5.objectName() : "terminal",
                                    "home" : self.leftMenuBtn1,
                                    "laser" : self.leftMenuBtn2,
                                    "programs" : self.leftMenuBtn3,
                                    "print" : self.leftMenuBtn4,
                                    "terminal" : self.leftMenuBtn5
                                    }
        
        self.leftMenuWidget = DictAsClass(self.leftMenuWidget_dict)
        
        # center menu widgets
        self.centerMenu = self.findChild(QCustomSlideMenu, "centerMenuContainer")
        self.centerMenuBtn1 = self.findChild(QPushButton, "comPushButton")
        self.centerMenuBtn2 = self.findChild(QPushButton, "settingsPushButton")
        self.centerMenuBtn3 = self.findChild(QPushButton, "infoPushButton")
        self.centerMenuBtn4 = self.findChild(QPushButton, "closeCenterMenuPushButton")
        self.centerMenuBtn5 = self.findChild(QPushButton, "profilePushButton")
        self.centerMenuBtn6 = self.findChild(QPushButton, "blackcomPushButton")
        
        self.centerMenuWidget_dict = {self.centerMenuBtn1.objectName() : "com",
                                      self.centerMenuBtn2.objectName() : "settings",
                                      self.centerMenuBtn3.objectName() : "info",
                                      self.centerMenuBtn4.objectName() : "close",
                                      self.centerMenuBtn5.objectName() : "profile",
                                      self.centerMenuBtn6.objectName() : "blackcom",
                                      "com" : self.centerMenuBtn1,
                                      "settings" : self.centerMenuBtn2,
                                      "info" : self.centerMenuBtn3,
                                      "close" : self.centerMenuBtn4,
                                      "profile" : self.centerMenuBtn5,
                                      "blackcom" : self.centerMenuBtn6
                                      }
        
        self.centerMenuWidget = DictAsClass(self.centerMenuWidget_dict)
        

        # operator profile widgets
        self.profileComboBox = self.findChild(QComboBox, "userComboBox")
        self.profileLineEdit = self.findChild(QLineEdit, "passwordLineEdit")
        self.profileBtn = self.findChild(QPushButton, "profilesetPushButton")
        
        self.profileWidget_dict = {self.profileComboBox.objectName() : "user",
                                   self.profileLineEdit.objectName() : "password",
                                   self.profileBtn.objectName() : "set",
                                   "user" : self.profileComboBox,
                                   "password" : self.profileLineEdit,
                                   "set" : self.profileBtn
                                   }
        
        self.profileWidget = DictAsClass(self.profileWidget_dict)
        
        # main body pages
        self.mainStack = self.findChild(QCustomStackedWidget, "mainPages")
        self.mainPage_dict = {"page1" : 0,
                              "page2" : 1,
                              "page3" : 2,
                              "page4" : 3,
                              "page5" : 4
                              }

        self.mainPageMenu_dict = {0 : self.leftMenuBtn1,
                                  1 : self.leftMenuBtn2,
                                  2 : self.leftMenuBtn3,
                                  3 : self.leftMenuBtn4,
                                  4 : self.leftMenuBtn5
                                  }
        
        # info sub pages
        self.infoStack = self.findChild(QStackedWidget, "infoSubPages")
        self.infoPage_dict = {"page1" : 0,
                              "page2" : 1,
                              "page3" : 2
                              }
        
        # jog widgets
        self.jogLCD1 = self.findChild(QLCDNumber, "xposLCDNumber")
        self.jogLCD2 = self.findChild(QLCDNumber, "yposLCDNumber")
        self.jogLCD3 = self.findChild(QLCDNumber, "zposLCDNumber")
        self.jogBtn1 = self.findChild(QPushButton, "xhomePushButton")
        self.jogBtn2 = self.findChild(QPushButton, "yhomePushButton")
        self.jogBtn3 = self.findChild(QPushButton, "zhomePushButton")
        self.jogBtn4 = self.findChild(QPushButton, "allhomePushButton")
        self.jogBtn5 = self.findChild(QPushButton, "xminusPushButton")
        self.jogBtn6 = self.findChild(QPushButton, "xplusPushButton")
        self.jogBtn7 = self.findChild(QPushButton, "yminusPushButton")
        self.jogBtn8 = self.findChild(QPushButton, "yplusPushButton")
        self.jogBtn9 = self.findChild(QPushButton, "zminusPushButton")
        self.jogBtn10 = self.findChild(QPushButton, "zplusPushButton")
        self.jogBtn11 = self.findChild(QPushButton, "xycenterPushButton")
        self.jogBtn12 = self.findChild(QPushButton, "zcenterPushButton")
        
        self.jogRadioBtn1 = self.findChild(QRadioButton, "travel100_RadioButton")
        self.jogRadioBtn2 = self.findChild(QRadioButton, "travel50_RadioButton")
        self.jogRadioBtn3 = self.findChild(QRadioButton, "travel10_RadioButton")
        self.jogRadioBtn4 = self.findChild(QRadioButton, "travel1_RadioButton")
        
        self.jogWidget_dict = {self.jogBtn1.objectName() : "home x",
                               self.jogBtn2.objectName() : "home y",
                               self.jogBtn3.objectName() : "home z",
                               self.jogBtn4.objectName() : "home",
                               self.jogBtn5.objectName() : "relative xm",
                               self.jogBtn6.objectName() : "relative xp",
                               self.jogBtn7.objectName() : "relative ym",
                               self.jogBtn8.objectName() : "relative yp",
                               self.jogBtn9.objectName() : "relative zm",
                               self.jogBtn10.objectName() : "relative zp",
                               self.jogBtn11.objectName() : "absolute xyc",
                               self.jogBtn12.objectName() : "absolute zc",
                               self.jogRadioBtn1.objectName() : 10,
                               self.jogRadioBtn2.objectName() : 5,
                               self.jogRadioBtn3.objectName() : 1,
                               self.jogRadioBtn4.objectName() : 0.1,
                               "xpos" : self.jogLCD1,
                               "ypos" : self.jogLCD2,
                               "zpos" : self.jogLCD3,
                               "xhome" : self.jogBtn1,
                               "yhome" : self.jogBtn2,
                               "zhome" : self.jogBtn3,
                               "allhome" : self.jogBtn4,
                               "xminus" : self.jogBtn5,
                               "xplus" : self.jogBtn6,
                               "yminus" : self.jogBtn7,
                               "yplus" : self.jogBtn8,
                               "zminus" : self.jogBtn9,
                               "zplus" : self.jogBtn10,
                               "xycenter" : self.jogBtn11,
                               "zcenter" : self.jogBtn12
                               }
        
        self.jogWidget = DictAsClass(self.jogWidget_dict)
        
        # laser set focus widgets
        self.focusLCD = self.findChild(QLCDNumber, "focusLCDNumber")
        self.focusBtn1 = self.findChild(QPushButton, "flaserPushButton")
        self.focusBtn2 = self.findChild(QPushButton, "fplusPushButton")
        self.focusBtn3 = self.findChild(QPushButton, "fminusPushButton")
        self.focusBtn4 = self.findChild(QPushButton, "fsetPushButton")
        
        # laser offset widgets
        self.offsetLCD1 = self.findChild(QLCDNumber, "xoffsetLCDNumber")
        self.offsetLCD2 = self.findChild(QLCDNumber, "yoffsetLCDNumber")
        self.offsetBtn1 = self.findChild(QPushButton, "offyplusPushButton")
        self.offsetBtn2 = self.findChild(QPushButton, "offyminusPushButton")
        self.offsetBtn3 = self.findChild(QPushButton, "offxplusPushButton")
        self.offsetBtn4 = self.findChild(QPushButton, "offxminusPushButton")
        self.offsetBtn5 = self.findChild(QPushButton, "offsetPushButton")
        self.offsetBtn6 = self.findChild(QPushButton, "travelPushButton")
        
        self.laserWidget_dict = {self.focusBtn1.objectName() : "flaser",
                                 self.focusBtn2.objectName() : "relative zp",
                                 self.focusBtn3.objectName() : "relative zm",
                                 self.focusBtn4.objectName() : "focus",
                                 self.offsetBtn1.objectName() : "relative yp",
                                 self.offsetBtn2.objectName() : "relative ym",
                                 self.offsetBtn3.objectName() : "relative xp",
                                 self.offsetBtn4.objectName() : "relative xm",
                                 self.offsetBtn5.objectName() : "offset",
                                 self.offsetBtn6.objectName() : "travel",
                                 "flaser" : self.focusBtn1,
                                 "fplus" : self.focusBtn2,
                                 "fminus" : self.focusBtn3,
                                 "focus" : self.focusBtn4,                                 
                                 "yplus" : self.offsetBtn1,
                                 "yminus" : self.offsetBtn2,
                                 "xplus" : self.offsetBtn3,
                                 "xminus" : self.offsetBtn4,
                                 "offset" : self.offsetBtn5,
                                 "travel" : self.offsetBtn6,
                                 "zfocus" : self.focusLCD,
                                 "xoffset" : self.offsetLCD1,
                                 "yoffset" : self.offsetLCD2
                                }
        
        self.laserWidget = DictAsClass(self.laserWidget_dict)
        
        # program widgets        
        self.pgmText = self.findChild(QTextEdit, "pgmfileTextEdit")
        self.pgmLine2 = self.findChild(QLineEdit, "pgmfeedLineEdit")
        self.pgmComboBox = self.findChild(QComboBox, "pgmlaserComboBox")
        self.pgmBtn1 = self.findChild(QPushButton, "pgmfilePushButton")
        self.pgmBtn3 = self.findChild(QPushButton, "pgmfeedPushButton")
        self.pgmBtn4 = self.findChild(QPushButton, "pgmsavePushButton")
        self.pgmBtn5 = self.findChild(QPushButton, "pgmfillPushButton")
        self.pgmBtn6 = self.findChild(QPushButton, "pgmpurgePushButton")
        self.travel01_RadioButton = self.findChild(QRadioButton, "travel01_RadioButton")
        self.travel1_RadioButton_3 = self.findChild(QRadioButton, "travel1_RadioButton_3")
        self.travel5_RadioButton = self.findChild(QRadioButton, "travel5_RadioButton")
        self.travel10_RadioButton_3 = self.findChild(QRadioButton, "travel10_RadioButton_3")
        
        
        self.programWidget_dict = {self.pgmBtn1.objectName() : "file",
                                   self.pgmBtn3.objectName() : "feed",
                                   self.pgmBtn4.objectName() : "save",
                                   self.pgmBtn5.objectName(): "fill",   
                                   self.pgmBtn6.objectName(): "purge",


                                   "file" : self.pgmBtn1,
                                   "feed" : self.pgmBtn3,
                                   "save" : self.pgmBtn4,
                                   "fill" : self.pgmBtn5,
                                   "purge" : self.pgmBtn6,
                                   "infile" : self.pgmText,
                                   "infeed" : self.pgmLine2,
                                   "inlaser" : self.pgmComboBox
                                   }
        
        self.programWidget = DictAsClass(self.programWidget_dict)
        
        # print widgets
        self.printLabel = self.findChild(QLabel, "progressLabel")
        self.printProgress = self.findChild(QProgressBar, "printProgressBar")
        self.printProgress.setMinimum(0)
        self.printProgress.setMaximum(100)
        
        self.printFrame = self.findChild(QFrame, "printplotFrame")
        self.printBtn1 = self.findChild(QPushButton, "printrunPushButton")
        self.printBtn2 = self.findChild(QPushButton, "printpausePushButton")
        self.printBtn3 = self.findChild(QPushButton, "printabortPushButton")
        self.printBtn4 = self.findChild(QPushButton, "printparaPushButton")
        
        plot = QVBoxLayout()
        self.printFrame.setLayout(plot)
        plot.addWidget(self.preview)
        
        self.printWidget_dict = {self.printBtn1.objectName() : "run",
                                 self.printBtn2.objectName() : "pause",
                                 self.printBtn3.objectName() : "abort",
                                 self.printBtn4.objectName() : "para",
                                 "run" : self.printBtn1,
                                 "pause" : self.printBtn2,
                                 "abort" : self.printBtn3,
                                 "para" : self.printBtn4,
                                 "plot" : self.printLabel,
                                 "progress" : self.printProgress,                                                                                                  
                                 "print" : self.printLabel,
                                 "progress_signal" : self.sigPrintProgress
                                 }
        
        self.printWidget = DictAsClass(self.printWidget_dict)
        
        # terminal widgets
        self.terminalText = self.findChild(QTextEdit, "terimalTextEdit")
        self.terminalLine = self.findChild(QLineEdit, "terminalLineEdit")
        self.terminalBtn = self.findChild(QPushButton, "terminalsendPushButton")
        
        self.terminalWidget_dict = {self.terminalBtn.objectName() : "send",
                                    "input" : self.terminalLine,
                                    "output" : self.terminalText
                                    }
        
        self.terminalWidget = DictAsClass(self.terminalWidget_dict)

        # parameter widgets
        self.paraBtn1 = self.findChild(QPushButton, "bedPushButton")
        self.paraBtn2 = self.findChild(QPushButton, "pressurePushButton")
        self.paraBtn3 = self.findChild(QPushButton, "uvPushButton")
        
        # parabed widgets
        self.bedcurLine = self.findChild(QLineEdit, "bedcurLineEdit")
        self.bedsetLine = self.findChild(QLineEdit, "bedsetLineEdit")
        self.bedSlider = self.findChild(QSlider, "bedHorizontalSlider")
        if self.bedSlider:
            self.bedSlider.setRange(0, 100)
        self.bedBtn = self.findChild(QPushButton, "bedsetPushButton")
        self.parabkbedBtn = self.findChild(QPushButton, "parabkbedPushButton")
        
        self.parabedWidget_dict = {
            self.bedBtn.objectName(): "set",
            self.parabkbedBtn.objectName(): "bedback",
            "set": self.bedBtn,
            "bedback": self.parabkbedBtn,
            "cur": self.bedcurLine,
            "set_line": self.bedsetLine,
            "slider": self.bedSlider
        }
        self.parabedWidget = DictAsClass(self.parabedWidget_dict)

        # paraextrusion widgets
        self.prcurLine = self.findChild(QLineEdit, "prcurLineEdit")
        self.prsetLine = self.findChild(QLineEdit, "prsetLineEdit")
        self.prSlider = self.findChild(QSlider, "preHorizontalSlider")
        if self.prSlider:
            self.prSlider.setRange(0, 100)
        self.prBtn = self.findChild(QPushButton, "prsetPushButton")
        self.parabkprBtn = self.findChild(QPushButton, "parabkprPushButton")
        
        self.paraextrusionWidget_dict = {
            self.prBtn.objectName(): "set",
            self.parabkprBtn.objectName(): "extrusionback",
            "set": self.prBtn,
            "extrusionback": self.parabkprBtn,
            "cur": self.prcurLine,
            "set_line": self.prsetLine,
            "slider": self.prSlider
        }
        self.paraextrusionWidget = DictAsClass(self.paraextrusionWidget_dict)

        # parauv widgets
        self.uvCheck = self.findChild(QCheckBox, "pgmuvCheckBox")
        self.uvExposureCombo = self.findChild(QComboBox, "exposureComboBox")
        self.uvDurationCombo = self.findChild(QComboBox, "expdurationComboBox")
        self.uvMinLCD = self.findChild(QLCDNumber, "uvminLCDNumber")
        self.uvSecLCD = self.findChild(QLCDNumber, "uvsecLCDNumber")
        self.uvOnBtn = self.findChild(QPushButton, "uvonPushButton")
        self.uvOffBtn = self.findChild(QPushButton, "uvoffPushButton")
        self.parabkuvBtn = self.findChild(QPushButton, "parabkuvPushButton")

        self.parauvWidget_dict = {
            "uvon": self.uvOnBtn,
            "uvoff": self.uvOffBtn,
            "uvback": self.parabkuvBtn,
            "check": self.uvCheck,
            "exposure": self.uvExposureCombo,
            "duration": self.uvDurationCombo,
            "min_lcd": self.uvMinLCD,
            "sec_lcd": self.uvSecLCD
        }
        if self.uvOnBtn: self.parauvWidget_dict[self.uvOnBtn.objectName()] = "uvon"
        if self.uvOffBtn: self.parauvWidget_dict[self.uvOffBtn.objectName()] = "uvoff"
        if self.parabkuvBtn: self.parauvWidget_dict[self.parabkuvBtn.objectName()] = "uvback"
        self.parauvWidget = DictAsClass(self.parauvWidget_dict)

        # initialize callbacks used in the UI
        self.sercom.configCallbacks(responseCallback = self.updateData, exceptionCallback = self.updateException)
        self.blackpill_sercom.configCallbacks(exceptionCallback = self.updateException)
        self.gcode.attachCallback(self.cb)
        self.cb.register(self.gcode.gcode_dict.get("home"), self.goHome)
        self.cb.register(self.gcode.gcode_dict.get("get-pos"), self.updateAxisPos)
        self.cb.register(self.gcode.gcode_dict.get("finish-move"), self.moveFinish)
        self.cb.register("FullTempUpdate", self.updateTemperatureUI)

        # widget function binding
        self.bindWidgetSignals()
        
        # schedule UI loaded notification
        QTimer.singleShot(200, self.onLoad)
        self.logger.info("UI load successful")
        
        # profile combobox update
        self.profile_list = ["Operator", "Supervisor", "Technician"]
        self.wm.operate(self.profileComboBox, "add", self.profile_list)
        
        # self.showStackPage(self.mainStack, self.mainPage_dict, 0)
        self.showMainPage(0)
        self.showStackPage(self.infoStack, self.infoPage_dict, 0)            

    def bindWidgetSignals(self):
        # expand centerMenuContainer
        self.centerMenuBtn1.clicked.connect(lambda: self.centerMenuAction(self.centerMenuBtn1))
        self.centerMenuBtn2.clicked.connect(lambda: self.centerMenuAction(self.centerMenuBtn2))
        self.centerMenuBtn3.clicked.connect(lambda: self.centerMenuAction(self.centerMenuBtn3))
        self.centerMenuBtn5.clicked.connect(lambda: self.centerMenuAction(self.centerMenuBtn5))
        self.centerMenuBtn6.clicked.connect(lambda: self.centerMenuAction(self.centerMenuBtn6))
        
        # close centerMenuContainer
        self.centerMenuBtn4.clicked.connect(lambda: self.centerMenuAction(self.centerMenuBtn4))
        
        # close notifyContainer
        self.notifyMenuBtn1.clicked.connect(lambda: self.notifyMenuAction(self.notifyMenuBtn1))
        
        # UV Exposure buttons
        self.ui.uvonPushButton.clicked.connect(lambda: self.sendGcode("M118 A1 P2 UR\n"))
        self.ui.uvoffPushButton.clicked.connect(lambda: self.sendGcode("M118 A1 P2 UO\n"))
        
        # profile
        self.profileBtn.clicked.connect(lambda: self.profileAction(self.profileBtn))
        
        # serial COM
        self.comBtn1.clicked.connect(lambda: self.comAction(self.com, widget=self.comBtn1))
        self.comBtn2.clicked.connect(lambda: self.comAction(self.com, widget=self.comBtn2))
        self.blackComBtn1.clicked.connect(lambda: self.comAction(self.black_com, widget=self.blackComBtn1))
        self.blackComBtn2.clicked.connect(lambda: self.comAction(self.black_com, widget=self.blackComBtn2))

        # jog travel radio buttons
        self.jogRadioBtn1.clicked.connect(lambda : self.jogAction(self.jogRadioBtn1))
        self.jogRadioBtn2.clicked.connect(lambda : self.jogAction(self.jogRadioBtn2))
        self.jogRadioBtn3.clicked.connect(lambda : self.jogAction(self.jogRadioBtn3))
        self.jogRadioBtn4.clicked.connect(lambda : self.jogAction(self.jogRadioBtn4))

        # jog home buttons
        self.jogBtn1.clicked.connect(lambda: self.jogAction(self.jogBtn1))
        self.jogBtn2.clicked.connect(lambda: self.jogAction(self.jogBtn2))
        self.jogBtn3.clicked.connect(lambda: self.jogAction(self.jogBtn3))
        self.jogBtn4.clicked.connect(lambda: self.jogAction(self.jogBtn4))

        # jog XY axis buttons
        self.jogBtn5.clicked.connect(lambda: self.jogAction(self.jogBtn5))
        self.jogBtn6.clicked.connect(lambda: self.jogAction(self.jogBtn6))
        self.jogBtn7.clicked.connect(lambda: self.jogAction(self.jogBtn7))
        self.jogBtn8.clicked.connect(lambda: self.jogAction(self.jogBtn8))
        self.jogBtn11.clicked.connect(lambda: self.jogAction(self.jogBtn11))

        # jog Z axis buttons
        self.jogBtn9.clicked.connect(lambda: self.jogAction(self.jogBtn9))
        self.jogBtn10.clicked.connect(lambda: self.jogAction(self.jogBtn10))
        self.jogBtn12.clicked.connect(lambda: self.jogAction(self.jogBtn12))
        
        # laser Set Focus widgets
        
        # laser focus options
        self.focusBtn1.clicked.connect(lambda: self.laserAction(self.focusBtn1))
        self.focusBtn2.clicked.connect(lambda: self.laserAction(self.focusBtn2))
        self.focusBtn3.clicked.connect(lambda: self.laserAction(self.focusBtn3))
        self.focusBtn4.clicked.connect(lambda: self.laserAction(self.focusBtn4))
        
        # laser offset widgets
        self.offsetBtn1.clicked.connect(lambda: self.laserAction(self.offsetBtn1))
        self.offsetBtn2.clicked.connect(lambda: self.laserAction(self.offsetBtn2))
        self.offsetBtn3.clicked.connect(lambda: self.laserAction(self.offsetBtn3))
        self.offsetBtn4.clicked.connect(lambda: self.laserAction(self.offsetBtn4))
        self.offsetBtn5.clicked.connect(lambda: self.laserAction(self.offsetBtn5))
        self.offsetBtn6.clicked.connect(lambda: self.laserAction(self.offsetBtn6))
                
        # program widgets
        self.pgmBtn1.clicked.connect(lambda: self.programAction(self.pgmBtn1))
        self.pgmBtn3.clicked.connect(lambda: self.programAction(self.pgmBtn3))
        self.pgmBtn4.clicked.connect(lambda: self.programAction(self.pgmBtn4))
        self.pgmBtn5.clicked.connect(lambda: self.programAction(self.pgmBtn5))
        self.pgmBtn6.clicked.connect(lambda: self.programAction(self.pgmBtn6))
        
        # print widgets
        self.printBtn1.clicked.connect(lambda: self.printAction(self.printBtn1))
        self.printBtn2.clicked.connect(lambda: self.printAction(self.printBtn2))
        self.printBtn3.clicked.connect(lambda: self.printAction(self.printBtn3))
        self.printBtn4.clicked.connect(lambda: self.printAction(self.printBtn4))
        
        # terminal widgets
        self.terminalBtn.clicked.connect(lambda: self.terminalAction(self.terminalBtn))
        self.terminalLine.returnPressed.connect(lambda: self.terminalAction(self.terminalBtn))

        # parameter widgets
        self.paraBtn1.clicked.connect(lambda: self.parameterAction(self.paraBtn1))
        self.paraBtn2.clicked.connect(lambda: self.parameterAction(self.paraBtn2))
        self.paraBtn3.clicked.connect(lambda: self.parameterAction(self.paraBtn3))
        
        self.bedBtn.clicked.connect(lambda: self.parabedAction(self.bedBtn))
        self.parabkbedBtn.clicked.connect(lambda: self.parabedAction(self.parabkbedBtn))
        
        self.bedSlider.valueChanged.connect(lambda val: self.wm.operate(self.parabedWidget.set_line, "set", str(val)))
        self.bedsetLine.textChanged.connect(lambda text: self.bedSlider.setValue(int(text)) if text.isdigit() else None)
        
        self.prBtn.clicked.connect(lambda: self.paraextrusionAction(self.prBtn))
        self.parabkprBtn.clicked.connect(lambda: self.paraextrusionAction(self.parabkprBtn))
        
        self.prSlider.valueChanged.connect(lambda val: self.wm.operate(self.paraextrusionWidget.set_line, "set", str(val)))
        self.prsetLine.textChanged.connect(lambda text: self.prSlider.setValue(int(text)) if text.isdigit() else None)

        if self.uvOnBtn: self.uvOnBtn.clicked.connect(lambda: self.parauvAction(self.uvOnBtn))
        if self.uvOffBtn: self.uvOffBtn.clicked.connect(lambda: self.parauvAction(self.uvOffBtn))
        if self.parabkuvBtn: self.parabkuvBtn.clicked.connect(lambda: self.parauvAction(self.parabkuvBtn))

        # print progress bar
        self.sigPrintProgress.connect(self._updatePrintProgress, Qt.QueuedConnection)

        # main stack page change signal
        self.mainStack.currentChanged.connect(self.showMainPage)

    @Slot(float)
    def _updatePrintProgress(self, value: float):
        self.printProgress.setValue(value)

    def setProgress(self, value: float):        
        self.sigPrintProgress.emit(value)

    def updateProgress(self, signal: Signal, value: float):
        if signal and value is not None:
            signal.emit(value)
        
    def setWidgetPara(self, widget, method_name, value=None):
        method = getattr(widget, method_name)
        
        if value is not None:
            method(value)
        else:
            method()
            
    def getWidgetPara(self, widget, method_name):
        method = getattr(widget, method_name)
        return method()

    def getPageIndex(self, page_dict, arg):
        index = 0

        if isinstance(arg, int):
            index = arg

        if isinstance(arg, str):
            index = page_dict.get(arg)

        return index                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                     
        
    def showStackPage(self, widget, page_dict, arg):
        method_name = "setCurrentIndex"
        self.util.debugPrint(f"arg : {arg}")

        index = self.getPageIndex(page_dict, arg)
        self.setWidgetPara(widget, method_name, value=index)

    def moveFinish(self, *args, **kwargs):
        self.logger.info("Movement finished (M400).")
        self.release_flag = False    # allow new commands again
        self.pgmGcode("M114")


        
    def initConfig(self, config_dir="config", config_file="config.ini"):
        self.config_dir_path = self.fh.getPath(dir=config_dir)
        self.config_file_path = self.fh.getPath(dir=self.config_dir_path, file=config_file)

        self.fh.checkDir(self.config_dir_path)
        self.conf.ini_parser.read(self.config_file_path)
        parser = self.conf.ini_parser

        # ----------------------------
        # Bed size
        # ----------------------------
        try:
            self.bed_xmin = float(parser.get("bed", "xmin", fallback="0"))
            self.bed_ymin = float(parser.get("bed", "ymin", fallback="0"))
            self.bed_xmax = float(parser.get("bed", "xmax", fallback="50"))
            self.bed_ymax = float(parser.get("bed", "ymax", fallback="50"))
            self.bed_size = (self.bed_xmin, self.bed_ymin, self.bed_xmax, self.bed_ymax)
            self.logger.info(
                f"Loaded bed bounds: X=({self.bed_xmin}, {self.bed_xmax}), "
                f"Y=({self.bed_ymin}, {self.bed_ymax})"
            )
        except Exception as e:
            self.logger.warning(f"Failed to read bed bounds from config: {e}")
            self.bed_size = (0, 0, 50, 50)

        # ----------------------------
        # OFFSETS + draw_z from config.ini
        # ----------------------------
        raw_x = parser.get("offset", "xoffset", fallback="").strip()
        raw_y = parser.get("offset", "yoffset", fallback="").strip()

        if raw_x != "" and raw_y != "":
            self.offset_x = float(raw_x)
            self.offset_y = float(raw_y)
            self.offset_user_set = True
            self.logger.info(f"Loaded offsets from config: X={self.offset_x}, Y={self.offset_y}")
        else:
            self.offset_x = None
            self.offset_y = None
            self.offset_user_set = False

        raw_z = parser.get("bed", "draw_z", fallback="").strip()
        raw_z_up = parser.get("bed", "draw_z_UP", fallback="").strip()
        if raw_z != "":
            self.draw_z_value = float(raw_z)
            if raw_z_up != "":
                self.draw_z_UP = float(raw_z_up)
            else:
                self.draw_z_UP = self.draw_z_value / 2.0
            self.draw_z_user = True
            self.logger.info(f"Loaded draw_z from config: Z={self.draw_z_value}, draw_z_UP={self.draw_z_UP}")
        else:
            self.draw_z_value = None
            self.draw_z_UP = None
            self.draw_z_user = False

        # ----------------------------
        # SLICING → Read values from config.ini
        # ----------------------------
        raw_lh = parser.get("slicing", "layer_height", fallback="").strip()
        raw_lh0 = parser.get("slicing", "layer_height_0", fallback="").strip()

        # ---- Validate layer_height ----
        try:
            lh_value = float(raw_lh)
            if lh_value > 0:
                self.layer_height = lh_value
            else:
                self.layer_height = 0.4
        except:
            self.layer_height = 0.4

        # ---- Validate layer_height_0 ----
        try:
            lh0_value = float(raw_lh0)
            if lh0_value > 0:
                self.layer_height_0 = lh0_value
            else:
                self.layer_height_0 = self.layer_height   # fallback
        except:
            self.layer_height_0 = self.layer_height       # fallback
            
        raw_nz = parser.get("slicing", "nozzle_size", fallback="").strip()
        try:
            nz_value = float(raw_nz)
            if nz_value > 0:
                self.nozzle_size = nz_value
            else:
                self.nozzle_size = 0.4
        except:
            self.nozzle_size = 0.4

        self.logger.info(
            f"Loaded slicing layer_height={self.layer_height}, "
            f"layer_height_0={self.layer_height_0}, "
            f"nozzle_size={self.nozzle_size}"
        )

        # ----------------------------
        # Update profile.json → only layer_height + layer_height_0
        # ----------------------------
        try:
            profile_path = ensure_profile_exists()   # ensures file exists

            with open(profile_path, "r", encoding="utf-8") as f:
                data = json.load(f)

            # ---- Update the keys ----
            data["layer_height"] = float(self.layer_height)
            data["layer_height_0"] = float(self.layer_height_0)

            with open(profile_path, "w", encoding="utf-8") as f:
                json.dump(data, f, indent=4)

            self.logger.info(
                f"Updated profile.json: layer_height={self.layer_height}, "
                f"layer_height_0={self.layer_height_0}"
            )

        except Exception as e:
            self.logger.error(f"Failed to update profile.json: {e}")

        # ----------------------------
        # UV Exposure Feature Toggle
        # ----------------------------
        try:
            uv_exposure_str = parser.get("features", "uv_exposure", fallback="False").strip()
            self.uv_exposure = uv_exposure_str.lower() in ["true", "1", "yes"]
            if not self.uv_exposure:
                self.ui.widget_2.hide()
                self.ui.frame_18.hide()
                
            uv_time_str = parser.get("features", "uv_exposure_time", fallback="0 min,0 sec").strip()
            mins = 0
            secs = 0
            parts = uv_time_str.split(',')
            for p in parts:
                p = p.strip()
                if 'min' in p:
                    mins = int(re.sub(r'\D', '', p) or 0)
                elif 'sec' in p:
                    secs = int(re.sub(r'\D', '', p) or 0)
            self.uv_time_ms = (mins * 60 + secs) * 1000
            self.logger.info(f"UV Exposure Time loaded: {self.uv_time_ms} ms")
        except Exception as e:
            self.logger.error(f"Failed to read uv_exposure config: {e}")
            self.uv_time_ms = 0

    def initSetting(self):

        conf_name = "focus"
        focus_dict = self.conf.getSection(conf_name)

        for _, value in focus_dict.items():
            data = value.replace('{', '').replace('}', '')
            laser = data.split(':')[0].strip("'")
            focus = float(data.split(':')[1])
            self.laserhandler.focus(laser, focus)

        conf_name = "zero"
        self.zero_laser = self.conf.getValues(conf_name, "laser")

        conf_name = "offset"
        self.offset_laser = self.conf.getValues(conf_name, "laser")
        xoffset = float(self.conf.getValues(conf_name, "xoffset"))
        yoffset = float(self.conf.getValues(conf_name, "yoffset"))

        self.laserhandler.xpos(self.offset_laser, xoffset)
        self.laserhandler.ypos(self.offset_laser, yoffset)

        conf_name = "feed"
        self.jogfeed = int(self.conf.getValues(conf_name, "feed"))

        laser_handler_dict = self.laserhandler.getHandlerData()
        self.util.debugPrint(f"xindex : {self.xindex}")
        self.util.debugPrint(f"yindex : {self.yindex}")
        self.util.debugPrint(f"feed : {self.jogfeed}")
        self.util.debugPrint(f"laser handler : {laser_handler_dict}")

    def initCom(self, com, refresh=False):
        serial_obj = getattr(self, com.object)
        port_widget = com.port
        baud_widget = com.baud
        
        port_list = serial_obj.getPorts()
        baud_list = serial_obj.getBaudrates()
                
        msg = f"Com : {com.conf}, Port : {port_list}, Baud : {baud_list}"
        self.util.debugPrint(msg)
        self.logger.info(msg)

        if refresh:
            pass
            
        self.wm.operate(port_widget, "clear")
        self.wm.operate(baud_widget, "clear")
        
        self.wm.operate(port_widget, "add", port_list)
        self.wm.operate(baud_widget, "add", baud_list)
        
    def configCom(self, com, mode):
        
        error_dict = {1 : ("Invalid Input", "Kindly select both COM port and baud rate."),
                      2 : ("Invalid Input", "Kindly select a COM port."),
                      3 : ("Invalid Input", "Kindly select a baud rate.")
                      }
        
        error_rules = [(lambda port, baud : port is False and baud is False, 1),
                       (lambda port, baud : port is False and baud is True, 2),
                       (lambda port, baud : port is True and baud is False, 3)
                       ]
        
        serial_obj = getattr(self, com.object)
        
        conf_name = com.conf
        port_widget = com.port
        baud_widget = com.baud

        if mode in ["Connect", "Disconnect", "Auto"]:

            if mode == "Connect":
                port = self.wm.operate(port_widget, "get")
                baud = self.wm.operate(baud_widget, "get")

                self.util.debugPrint(f"port : {port}")
                self.util.debugPrint(f"baud : {baud}")

                for condition, code in error_rules:
                    if condition(serial_obj.validatePort(port), serial_obj.validateBaudrate(baud)):
                        error_title, error_text = error_dict.get(code)
                        msg = f"Error : {error_title} > {error_text}"
                        self.util.debugPrint(msg)
                        self.logger.error(msg)
                        self.showCustomPopup(error_title, error_text)
                        return False
                    
                serial_obj.port = port
                serial_obj.baudrate = baud
                
                self.conf.addParameter(conf_name, "port", port)
                self.conf.addParameter(conf_name, "baudrate", baud)                
                self.conf.updateFile(self.config_file_path)
                
                serial_obj.connect()
                msg = "Serial communication started"
                self.util.debugPrint(msg)
                self.logger.critical(msg)
        
                return True

            if mode == "Auto":
                port = self.conf.getValues(conf_name, "port")
                baud = self.conf.getValues(conf_name, "baudrate")

                msg_dict = {True : ("COM Port Connection",f"Do you want to auto connect to {port} @ {baud}"),
                            False : ("COM Port Auto-Connection failed","Kindly peform manual COM port configuration!!!")}
                
                condition = serial_obj.validatePort(port) and serial_obj.validateBaudrate(baud)
                msg_title, msg_text = msg_dict.get(condition)

                if condition:
                    retval = self.showCustomPopup(msg_title, msg_text, buttons=QMessageBox.Ok | QMessageBox.Cancel)
                    self.logger.info(msg_text)

                    if retval == QMessageBox.Ok:
                        self.util.debugPrint('OK clicked')
                        self.wm.operate(port_widget, "set", port)
                        self.wm.operate(baud_widget, "set", baud)
                        serial_obj.port = port
                        serial_obj.baudrate = baud
                        serial_obj.connect()
                        msg = "Serial communication autostarted"
                        self.util.debugPrint(msg)
                        self.logger.info("Auto Connect dialog button : Ok")
                        self.logger.info(msg)


                        return True

                    if retval == QMessageBox.Cancel:
                        self.util.debugPrint('Cancel clicked')
                        self.logger.info("Auto Connect dialog button : Cancel")
                        self.wm.operate(port_widget, "clear")
                        self.wm.operate(baud_widget, "clear")

                        return False
            
            if mode == "Disconnect":
                serial_obj.disconnect()
                msg = "Serial communication stopped"
                self.util.debugPrint(msg)
                self.logger.info(msg)
                return True
            
    def updateTemperatureUI(self, temps=None):
        if temps:
            # Update bed temperature in UI
            if "B" in temps:
                cur_b = temps["B"][0]
                if hasattr(self, "parabedWidget") and self.parabedWidget.cur:
                    self.wm.operate(self.parabedWidget.cur, "set", str(cur_b))
                    
            # Update extrusion temperature in UI
            if "T" in temps:
                cur_t = temps["T"][0]
                if hasattr(self, "paraextrusionWidget") and self.paraextrusionWidget.cur:
                    self.wm.operate(self.paraextrusionWidget.cur, "set", str(cur_t))

    def updateData(self, msg):
        if msg:
            data = msg.strip("\n")
            
        if data:
            self.gcode.decode(data)

            if data == "ok":
                data = f"{data}\n"

            if self.gcode.temp_report_flag and self.temp_report_hide_flag:
                self.gcode.temp_report_flag = False
            
            else:
                self.util.debugPrint(f"Received : {data}")
            
            self.receiveACK(self.terminalWidget.output, data)

    def updateException(self, args):
        self.util.debugPrint(f"error args : {args}")
        self.com_errorFlag = True
        self.util.debugPrint(f"error flag : {self.com_errorFlag}")
        self.comAction(self.com, action="Disconnect")

        self.exceptionOccurred.emit(str(args))

    def showExceptionPopup(self, args: str):
        self.showCustomPopup(
            "Machine Disconnected",
            "Disconnected from machine.\n\n"
            "Please connect again and reconnect the COM port or rerun the UI."
        )

        try:
            self.comAction(self.com, action="Auto")
        except Exception as e:
            self.util.debugPrint(f"Auto reconnect failed: {e}")

    def sendGcode(self, gstr: str):
        """Send one G-code line to printer, ignoring comments, blanks, and stripping inline notes."""
        gstr = gstr.strip()

        # Ignore full-line comments or empty lines
        if not gstr or gstr.startswith(";") or gstr.startswith("("):
            self.util.debugPrint(f"Skipping comment/non-executable: {gstr}")
            return

        # Remove inline comments safely
        gstr = re.split(r'[;()]', gstr, maxsplit=1)[0].strip()
        if not gstr:
            self.util.debugPrint(f"Skipping empty after stripping comment")
            return

        # Encode & checksum handling
        self.gcode.encode(gstr)
        if self.gcode.sd_write_flag:
            cs = self.gcode.checksum(gstr)
            gcode = f"{gstr}*{cs}\r\n"
        else:
            gcode = f"{gstr}\r\n"

        # Send and log
        self.sercom.send(gcode)
        self.util.debugPrint(f"Gcode - {gcode.strip()}")

    def pgmGcode(self, gstr: str):
        """Program-level G-code mapping (e.g., laser commands)."""
        cmd_dict = {
            "M3": "M106 P0 S255",  # Laser ON
            "M5": "M106 P0 S0"     # Laser OFF
        }

        gstr = gstr.strip()
        if not gstr or gstr.startswith(";") or gstr.startswith("("):
            self.util.debugPrint(f"Skipping comment/non-executable: {gstr}")
            return

        if gstr in cmd_dict:
            gcode = cmd_dict[gstr]
        else:
            gcode = gstr

        self.sendGcode(gcode)

        
    def goHome(self):
        self.updateAxisPos()
    
    def updateAxisPos(self):
        self.util.debugPrint(f"pos : {self.gcode.pos_list}")

        for item in self.gcode.pos_list:
            axis, value = item.split(':')            
            self.axishandler.pos(axis, float(value))
            
        self.jogPosDisplay()
        self.focusPosDisplay()
        self.offsetPosDisplay()
        
        self.indexProgram()
        
    def onLoad(self):
        msg = "UI is loaded"
        self.util.debugPrint(msg)        

        self.wm.operate(self.leftMenuWidget.terminal, "hide")
        self.wm.operate(self.centerMenuWidget.settings, "hide")

        self.updateProgress(self.printWidget.progress_signal, 0)
        
        self.initAxis()
        self.initSetting()
        self.initCom(self.com, refresh=True)
        self.comAction(self.com, action="Auto")

    def closeEvent(self, event):
        reply = self.showCustomPopup('Confirmation', "Are you sure you want to quit?", buttons=QMessageBox.Yes | QMessageBox.No)
        
        if reply == QMessageBox.Yes:
            self.util.debugPrint("Application is closing")

            self.comAction(self.com, action="Disconnect")
            self.logger.info("COM connection close successfully")

            # Log successful exit
            self.logger.info("Main window close successfully")
            self.logger.sessionSeparator("close")

            event.accept()

        else:
            self.util.debugPrint("Close event ignored.")
            self.logger.info("Close event ignored.")
            event.ignore()

    def showMainPage(self, page):
        index = self.getPageIndex(self.mainPage_dict, page)
        self.util.debugPrint(f"index : {index}")

        if index is not None:

            for menubtn in self.mainPageMenu_dict.values():
                menubtn.setStyleSheet("background-color: rgb(16, 42, 131);")

            btn = self.mainPageMenu_dict.get(index)
            if btn:
                btn.setStyleSheet("background-color: rgb(144, 170, 197);")

        # Update the stack if necessary (prevents redundant signals if called from currentChanged)
        if self.mainStack.currentIndex() != index:
            self.showStackPage(self.mainStack, self.mainPage_dict, page)
        
    def centerMenuAction(self, widget):
        # wtype = type(widget).__name__
        
        closeBtn = self.centerMenuBtn4
        profileBtn = self.centerMenuBtn5                
        
        if widget == self.centerMenuActiveBtn or widget == closeBtn:
            self.centerMenu.collapseMenu()
            if self.centerMenuActiveBtn:
                if self.centerMenuActiveBtn == profileBtn:
                    self.centerMenuActiveBtn.setStyleSheet("background-color: transparent;")
                else:
                    self.centerMenuActiveBtn.setStyleSheet("background-color: rgb(16, 42, 131);")
            self.centerMenuActiveBtn = None
            
        else:
            # Reset previous active button if any
            if self.centerMenuActiveBtn is not None:
                if self.centerMenuActiveBtn == profileBtn:
                    self.centerMenuActiveBtn.setStyleSheet("background-color: transparent;")
                else:
                    self.centerMenuActiveBtn.setStyleSheet("background-color: rgb(16, 42, 131);")
                
            self.centerMenuActiveBtn = widget
            # Highlight new active button, except for the profile button
            if widget == profileBtn:
                self.centerMenuActiveBtn.setStyleSheet("background-color: transparent;")
            else:
                self.centerMenuActiveBtn.setStyleSheet("background-color: rgb(167, 198, 229);")
            self.centerMenu.expandMenu()
                
    def notifyMenuAction(self, widget):
        closeBtn = self.notifyMenuBtn1
        
        if widget == closeBtn:
            if self.popupLoop.isRunning():
                self.popupResult = QMessageBox.Cancel
                self.popupLoop.quit()
            self.notifyMenu.collapseMenu()    
        
    def checkButtonGroup(self):
        """Required by Custom_Widgets library for QPushButtonGroup in style.json."""
        pass

    def onPopupBtnClicked(self, result):
        self.popupResult = result
        if self.popupLoop.isRunning():
            self.popupLoop.quit()
        self.notifyMenu.collapseMenu()

    def showCustomPopup(self, title, message, icon_type="info", buttons=QMessageBox.Ok, delay=0):
        """
        Displays a notification in the notifyContainer.
        Blocks until user interaction if buttons are provided, matching Bio4D style.
        """
        if self.notifyLabel:
            self.notifyLabel.setText(title)
        if self.notifyTextEdit:
            self.notifyTextEdit.setPlainText(message)
        
        # Reset buttons
        self.btnOk.hide()
        self.btnYes.hide()
        self.btnNo.hide()
        self.btnCancel.hide()
        
        # Show requested buttons
        if buttons & QMessageBox.Ok:
            self.btnOk.show()
        if buttons & QMessageBox.Yes:
            self.btnYes.show()
        if buttons & QMessageBox.No:
            self.btnNo.show()
        if buttons & QMessageBox.Cancel:
            self.btnCancel.show()

        # Slide in
        # FIX: Force the floating menu to recalculate its position relative to the window
        if hasattr(self.notifyMenu, 'floatReposition'):
            self.notifyMenu.floatReposition()
        elif hasattr(self.notifyMenu, 'reposition'):
            self.notifyMenu.reposition()
            
        self.notifyMenu.expandMenu()
        
        # If no buttons are shown, it's just an informative message
        if buttons == 0 or (not any(b.isVisible() for b in [self.btnOk, self.btnYes, self.btnNo, self.btnCancel])):
            if delay > 0:
                QTimer.singleShot(delay, self.notifyMenu.collapseMenu)
            return QMessageBox.Ok

        # Block and wait
        self.popupLoop.exec()
        
        return self.popupResult
        
    def comAction(self, com, widget=None, action=None):
        connect_btn_text = None
        refresh_btn_status = None
        com_status = False
        
        combtn_dict = {"Connect" : ("Disconnect", False),
                       "Disconnect" : ("Connect", True),
                       "Auto" : ("Disconnect", False)
                       }
        
        if widget is not None:
            action = widget.text()

        self.util.debugPrint(f"action : {action}")

        if action in ["Connect", "Disconnect", "Auto"]:
            com_status = self.configCom(com, action)
            self.util.debugPrint(f"status : {com_status}")
        
        if action == "Refresh":
            self.initCom(com, refresh=True)

        if com_status:
            if action in combtn_dict:
                           
                connect_btn_text, refresh_btn_status = combtn_dict.get(action)
                self.wm.operate(com.connect, "set", connect_btn_text)
                self.wm.operate(com.refresh, "enable", refresh_btn_status)
                self.util.debugPrint(f"connect btn : {connect_btn_text} | refresh btn : {refresh_btn_status}")
        
    def jogAction(self, widget):        
        wobj = widget.objectName()
        
        if hasattr(self.jogWidget, wobj):
            
            if self.util.checkSubString(wobj, "travel"):
                self.travel = getattr(self.jogWidget, wobj)
                
            if self.util.checkSubString(wobj, "home", "center", "plus", "minus"):
                jogcmd = getattr(self.jogWidget, wobj)
                self.axisMotion(jogcmd)
                
    def jogPosDisplay(self):                
        xpos = self.axishandler.getAxis("X").pos
        ypos = self.axishandler.getAxis("Y").pos
        zpos = self.axishandler.getAxis("Z").pos
        
        self.wm.operate(self.jogWidget.xpos, "set", xpos)
        self.wm.operate(self.jogWidget.ypos, "set", ypos)
        self.wm.operate(self.jogWidget.zpos, "set", zpos)
        
    def focusPosDisplay(self):
        zpos = self.axishandler.getAxis("Z").pos
        
        self.wm.operate(self.focusLCD, "set", zpos)
    
    def offsetPosDisplay(self):
        xpos = self.axishandler.getAxis("X").pos
        ypos = self.axishandler.getAxis("Y").pos

        if self.zero_flag:
            self.wm.operate(self.offsetLCD1, "set", xpos - self.xtemp)
            self.wm.operate(self.offsetLCD2, "set", ypos - self.ytemp) 

        else:
            self.wm.operate(self.offsetLCD1, "set", xpos)
            self.wm.operate(self.offsetLCD2, "set", ypos)

    def laserAction(self, widget):
        wobj = widget.objectName()
        set_dict = {"ACTIVATE": "DEACTIVATE", "DEACTIVATE": "ACTIVATE"}
        offset_btn = self.laserWidget.offset

        if hasattr(self.laserWidget, wobj):
            self.util.debugPrint(f"wobj : {wobj}")

            # --- Laser ON/OFF ---
            if self.util.checkSubString(wobj, "laser") and self.util.checkSubString(wobj, "PushButton"):
                if self.util.checkSubString(widget.text(), "ACTIVATE", "DEACTIVATE"):
                    text = set_dict.get(widget.text())
                    self.wm.operate(widget, "set", text)

                    if text == "DEACTIVATE" and "flaser" in wobj:
                        self.wm.operate(self.laserWidget.fplus, "enable", True)
                        self.wm.operate(self.laserWidget.fminus, "enable", True)
                        self.wm.operate(self.laserWidget.focus, "enable", True)

                    if text == "ACTIVATE" and "flaser" in wobj:
                        self.wm.operate(self.laserWidget.fplus, "enable", False)
                        self.wm.operate(self.laserWidget.fminus, "enable", False)
                        self.wm.operate(self.laserWidget.focus, "enable", False)

            # --- Set Draw Z ---
            if wobj == "fsetPushButton":
                self.wm.operate(self.laserWidget.flaser, "set", "ACTIVATE")
                self.wm.operate(self.laserWidget.fplus, "enable", False)
                self.wm.operate(self.laserWidget.fminus, "enable", False)
                self.wm.operate(self.laserWidget.focus, "enable", False)

                draw_z = self.wm.operate(self.laserWidget.zfocus, "get")
                self.draw_z_user = True              
                self.draw_z_value = float(draw_z)     
                self.draw_z_UP = self.draw_z_value / 2.0

                self.conf.addParameter("bed", "draw_z", str(self.draw_z_value))
                self.conf.addParameter("bed", "draw_z_UP", str(self.draw_z_UP))
                self.conf.updateFile(self.config_file_path)

                # Send draw_z_UP value to Z
                self.sendGcode("G90")
                self.sendGcode(f"G0 Z{self.draw_z_UP:.3f} F{self.jogfeed}")
                self.sendGcode("M114")

                msg_text = f"Draw Z value set to {self.draw_z_value:.2f} mm.\ndraw_z_UP set to {self.draw_z_UP:.2f} mm."
                self.showCustomPopup("Draw Z Set", msg_text)


            # --- Set Offset (X/Y) ---
            if self.util.checkSubString(wobj, "offset"):
                xoffset = self.axishandler.getAxis("X").pos - self.xtemp
                yoffset = self.axishandler.getAxis("Y").pos - self.ytemp

                bed_xmin, bed_ymin, bed_xmax, bed_ymax = self.bed_size

                x_final = self.xindex + xoffset
                y_final = self.yindex + yoffset

                if not (bed_xmin <= x_final <= bed_xmax and bed_ymin <= y_final <= bed_ymax):
                    self.xtemp, self.ytemp = 0.0, 0.0
                    msg_text = (f"Nozzle offset out of bed area!\n\n"
                                f"Allowed X range: {bed_xmin}–{bed_xmax}\n"
                                f"Allowed Y range: {bed_ymin}–{bed_ymax}\n"
                                f"Tried: X={x_final:.2f}, Y={y_final:.2f}")
                    self.showCustomPopup("Index Error", msg_text)
                    self.logger.warning("Offset attempt rejected: " + msg_text)
                    self.wm.operate(offset_btn, "enable", True)
                    return

                # Save offsets
                self.offset_user_set = True
                self.offset_x = float(x_final)
                self.offset_y = float(y_final)

                laser = self.laserhandler.getLaser(self.offset_laser)
                if laser:
                    laser.xpos = self.offset_x
                    laser.ypos = self.offset_y
                    setattr(laser, "user_set", True)
                    self.logger.debug(f"Saved to runtime laser: {self.offset_laser} xpos={laser.xpos}, ypos={laser.ypos}")

                # Persist to config
                self.conf.addParameter("offset", "laser", self.offset_laser)
                self.conf.addParameter("offset", "xoffset", str(self.offset_x))
                self.conf.addParameter("offset", "yoffset", str(self.offset_y))
                self.conf.updateFile(self.config_file_path)

                # Keep offset button always enabled
                self.wm.operate(offset_btn, "enable", True)

                # Inform user about X/Y offsets
                msg_text = f"Offsets set to :\nXoffset = {self.offset_x:.2f}\nYoffset = {self.offset_y:.2f}"
                self.showCustomPopup("Offsets Set", msg_text)

                # Send draw_z_UP value to Z
                if hasattr(self, 'draw_z_UP') and self.draw_z_UP is not None:
                    self.sendGcode("G90")
                    self.sendGcode(f"G0 Z{self.draw_z_UP:.3f} F{self.jogfeed}")
                    self.sendGcode("M114")

                self.logger.critical(f"{self.offset_laser} : has offset, Xoffset = {self.offset_x}, Yoffset = {self.offset_y}")
                self.util.debugPrint(f"xoffset : {self.offset_x}, yoffset : {self.offset_y}")
                self.zero_flag = False

            # --- Travel / Jog ---
            if self.util.checkSubString(wobj, "travel"):
                travel_list = [10, 5, 1, 0.1]
                self.travel_index = (self.travel_index + 1) % len(travel_list)
                self.wm.operate(self.laserWidget.travel, "set", str(travel_list[self.travel_index]))

            if self.util.checkSubString(wobj, "plus", "minus"):
                jogcmd = getattr(self.laserWidget, wobj)
                travel, feed = self.travel, self.jogfeed
                self.jogfeed = 500
                if self.util.checkSubString(wobj, "x", "y"):
                    travel = self.wm.operate(self.laserWidget.travel, "get")
                    self.travel = float(travel)
                else:
                    self.travel = 0.1
                self.axisMotion(jogcmd)
                self.travel, self.jogfeed = travel, feed

    def initAxis(self):
        self.axishandler.addAxis("X", 0, 0, 300, 1000, 800)
        self.axishandler.addAxis("Y", 0, 0, 300, 1000, 800)
        self.axishandler.addAxis("Z", 0, 0, 30, 1000, 800)
    
    def axisMotion(self, cmdstr):
        glist = []
        gcode = None
        
        cmd_dict = {"home" : "G28",
                    "linear" : f"G1 F{self.jogfeed}",
                    "relative" : "G91",
                    "absolute" : "G90",
                    "pos" : "M114"
                    }
        
        dir_dict = {'p' : '',
                    'm' : '-'
                    }
        
        center_dict = {'x' : self.xcenter,
                       'y' : self.ycenter,
                       'z' : self.zcenter
                       }
        
        cmd1 = cmdstr.split(" ")[0]
        cmd2 = None
        
        if cmdstr.count(" ") > 0:
            cmd2 = cmdstr.split(" ")[1]
            
        if cmd1 in cmd_dict:
            gcode = f"{cmd_dict.get(cmd1)}"
            
            if cmd2:
                if "home" in cmd1:
                    gcode += f" {cmd2.upper()}"
                    
                if self.util.checkSubString(cmd1, "relative", "absolute"): 
                    glist.append(gcode)
                    
                    gcode = f"{cmd_dict.get("linear")}"
                    
                    for arg in cmd2:
                        if arg in ['x', 'y', 'z']:
                            
                            gcode += f" {arg.upper()}"
                            
                            if "c" in cmd2:
                                gcode += f"{center_dict.get(arg)}"
                            
                        if arg in ['p', 'm']:
                            gcode += f"{dir_dict.get(arg)}{self.travel}"
                            self.util.debugPrint(f"travel: {self.travel}")
                
            glist.append(gcode)
            glist.append(cmd_dict.get("pos"))
            
        for g in glist:
            self.sendGcode(g)

    def programInit(self):
        self.prev_segment = 0
        self.wm.operate(self.programWidget.feed, "enable", False)
        self.wm.operate(self.programWidget.save, "enable", False)

    def programAction(self, widget):
        """Top-level router matching your original UI buttons."""
        wobj = widget.objectName()
        print(f"pgm : {wobj}")

        if not hasattr(self.programWidget, wobj):
            return

        if self.util.checkSubString(wobj, "file"):
            self._handle_file_load()

        elif self.util.checkSubString(wobj, "feed"):
            self._handle_feedrate()

        elif self.util.checkSubString(wobj, "fill"):
            self._handle_fill()

        elif self.util.checkSubString(wobj, "step"):
            self._handle_step()

        elif self.util.checkSubString(wobj, "purge"):
            self._handle_purge()

        elif self.util.checkSubString(wobj, "save"):
            self._handle_save_and_preview()


    # -------------------------------
    # 1) File Load (+ optional SVG→G-code)
    # -------------------------------
    def _handle_file_load(self):
        file_path, _ = QFileDialog.getOpenFileName(
            self,
            "Select File (G-code / SVG / DXF / BMP)",
            "",
            "Supported Files (*.gcode *.nc *.ngc *.txt *.svg *.dxf *.bmp)"
        )
        if not file_path:
            return

        # ---------------------------------------------------------
        # NEW: Clear old data immediately when a new file is selected
        # ---------------------------------------------------------
        self.pgm_file = file_path
        self.pgm_glist = []
        self.filtered_gcode = []
        if hasattr(self, "preview"):
            self.preview.loadGcode([])  # Clear 3D preview
        
        self.wm.operate(self.programWidget.save, "enable", False) # Disable save until valid G-code is ready
        self.logger.info(f"File selected: {self.pgm_file}")
        self.wm.operate(self.programWidget.infile, "set", self.pgm_file)
        self.wm.operate(self.programWidget.feed, "enable", True)

        # If SVG: convert -> STL -> G-code (non-destructive; final is .gcode beside svg)
        if self.pgm_file.lower().endswith(".svg"):
            try:
                converted_file = self._convert_svg_to_gcode(Path(self.pgm_file))
                if not converted_file:
                    raise RuntimeError("SVG conversion produced no G-code.")
                self.pgm_file = converted_file
                self.logger.info(f"G-code ready from SVG: {self.pgm_file}")
                self.wm.operate(self.programWidget.infile, "set", self.pgm_file)
            except Exception as e:
                error_msg = f"SVG conversion failed:\n{e}"
                self.logger.error(error_msg)
                self.util.debugPrint(error_msg)
                self.showCustomPopup("Slicing Error", error_msg) # Show user the error
                return
            
        # --- If DXF -> convert to G-code ---
        if self.pgm_file.lower().endswith(".dxf"):
            try:
                converted_file = self._convert_dxf_to_gcode(Path(self.pgm_file))
                if not converted_file:
                    raise RuntimeError("DXF conversion produced no G-code.")
                self.pgm_file = converted_file
                self.logger.info(f"G-code ready from DXF: {self.pgm_file}")
                self.wm.operate(self.programWidget.infile, "set", self.pgm_file)
            except Exception as e:
                error_msg = f"DXF conversion failed:\n{e}"
                self.logger.error(error_msg)
                self.util.debugPrint(error_msg)
                self.showCustomPopup("Slicing Error", error_msg) # Show user the error
                return
            
        # --- If BMP -> convert to G-code ---
        if self.pgm_file.lower().endswith(".bmp"):
            try:
                converted_file = self._convert_bmp_to_gcode(Path(self.pgm_file))
                if not converted_file:
                    raise RuntimeError("BMP conversion produced no G-code.")
                self.pgm_file = converted_file
                self.logger.info(f"G-code ready from BMP: {self.pgm_file}")
                self.wm.operate(self.programWidget.infile, "set", self.pgm_file)
            except Exception as e:
                error_msg = f"BMP conversion failed:\n{e}"
                self.logger.error(error_msg)
                self.util.debugPrint(error_msg)
                self.showCustomPopup("Conversion Error", error_msg) # Show user the error
                return

        # Parse once and cache (raw, unmodified)
        try:
            self.pgm_glist = self.gcode_parser.parse_file(self.pgm_file)
        except Exception as e:
            error_msg = f"Error parsing G-code file:\n{e}"
            self.logger.error(error_msg)
            self.util.debugPrint(error_msg)
            self.showCustomPopup("Parse Error", error_msg)
            self.pgm_glist = []
            return

        if not self.pgm_glist or len(self.pgm_glist) < 5:
            error_msg = "Parsed G-code is empty or too short."
            self.logger.warning(error_msg)
            self.showCustomPopup("File Error", error_msg)
            return

        self.logger.info(f"Raw G-code parsed ({len(self.pgm_glist)} lines).")


    def _convert_svg_to_gcode(self, svg_path: Path) -> str:
        gcode_file = svg_path.with_suffix(".gcode")

        self.logger.info(f"Converting SVG -> G-code directly: {svg_path}")
        
        success = convert_svg_to_gcode_module(
            svg_file=str(svg_path),
            gcode_file=str(gcode_file)
        )
        
        if not success or not os.path.exists(gcode_file):
            raise RuntimeError("Failed to generate G-code from SVG.")

        self.logger.info(f"G-code created: {gcode_file}")

        return str(gcode_file)

    def _convert_dxf_to_gcode(self, dxf_path: Path) -> str:
        gcode_file = dxf_path.with_suffix(".gcode")

        self.logger.info(f"Converting DXF -> G-code directly: {dxf_path}")
        
        success = convert_dxf_to_gcode_module(
            dxf_file=str(dxf_path),
            gcode_file=str(gcode_file),
            nozzle=getattr(self, 'nozzle_size', 0.4)
        )
        
        if not success or not os.path.exists(gcode_file):
            raise RuntimeError("Failed to generate G-code from DXF.")

        self.logger.info(f"G-code created: {gcode_file}")

        return str(gcode_file)

    def _convert_bmp_to_gcode(self, bmp_path: Path) -> str:
        gcode_file = bmp_path.with_suffix(".gcode")

        self.logger.info(f"Converting BMP -> G-code directly: {bmp_path}")
        
        success = convert_bmp_to_gcode_module(
            bmp_file=str(bmp_path),
            gcode_file=str(gcode_file),
            pixel_size=getattr(self, 'nozzle_size', 0.4)

        )
        
        if not success or not os.path.exists(gcode_file):
            raise RuntimeError("Failed to generate G-code from BMP.")

        self.logger.info(f"G-code created: {gcode_file}")

        return str(gcode_file)

    # -------------------------------
    # 2) Feedrate
    # -------------------------------
    def _handle_feedrate(self):
        feed = self.wm.operate(self.programWidget.infeed, "get")
        if feed is None:
            return
        try:
            self.pgm_feed = float(feed)
        except ValueError:
            self.showCustomPopup("Invalid feedrate", "Please enter a numeric feedrate.")
            return

        msg = f"Feedrate: {self.pgm_feed} mm/min"
        self.logger.info(msg)
        self.util.debugPrint(msg)
        self.wm.operate(self.programWidget.save, "enable", True)


    # -------------------------------
    # 3) Step,Fill,Purge
    # -------------------------------
    def _handle_step(self):
        """Cycle step size: 1 → 5 → 10 → 50 → 1 ..."""
        self.step_index = (self.step_index + 1) % len(self.step_list)
        self.current_step = self.step_list[self.step_index]

        # Update UI label/button
        self.wm.operate(self.programWidget.step, "set", str(self.current_step))

        self.logger.info(f"Step size changed to {self.current_step}")

    def _send_to_blackpill(self, cmd):
        if hasattr(self, 'blackpill_sercom') and self.blackpill_sercom.is_connected:
            self.blackpill_sercom.send(cmd + "\n")
            self.logger.info(f"Sent {cmd} to Blackpill")
        else:
            msg = "Blackpill is not connected. Please connect via the Black COM page."
            self.logger.error(msg)
            self.util.debugPrint(msg)
            self.showCustomPopup("Connection Error", msg)

    def _get_travel_distance(self):
        if hasattr(self, 'travel01_RadioButton') and self.travel01_RadioButton.isChecked(): return "0.1"
        if hasattr(self, 'travel1_RadioButton_3') and self.travel1_RadioButton_3.isChecked(): return "1.0"
        if hasattr(self, 'travel5_RadioButton') and self.travel5_RadioButton.isChecked(): return "5.0"
        if hasattr(self, 'travel10_RadioButton_3') and self.travel10_RadioButton_3.isChecked(): return "10.0"
        return "0.0"

    def _handle_fill(self):
        if not hasattr(self, 'fill_state'):
            self.fill_state = False
            self.purge_state = False

        if not self.fill_state:
            dist = self._get_travel_distance()
            cmd = f"FILL {dist}" if dist != "0.0" else "FILL"
            self._send_to_blackpill(cmd)
            self.fill_state = True
            self.purge_state = False
            self.programWidget.fill.setText("Stop Fill")
            self.programWidget.purge.setText("Purge")
            self.logger.info(f"Fill command ({cmd}) sent to Blackpill.")
        else:
            self._send_to_blackpill("STOP")
            self.fill_state = False
            self.programWidget.fill.setText("Fill")
            self.logger.info("Stop Fill command sent to Blackpill.")

    def _handle_purge(self):
        if not hasattr(self, 'fill_state'):
            self.fill_state = False
            self.purge_state = False

        if not self.purge_state:
            dist = self._get_travel_distance()
            cmd = f"PURGE {dist}" if dist != "0.0" else "PURGE"
            self._send_to_blackpill(cmd)
            self.purge_state = True
            self.fill_state = False
            self.programWidget.purge.setText("Stop Purge")
            self.programWidget.fill.setText("Fill")
            self.logger.info(f"Purge command ({cmd}) sent to Blackpill.")
        else:
            self._send_to_blackpill("STOP")
            self.purge_state = False
            self.programWidget.purge.setText("Purge")
            self.logger.info("Stop Purge command sent to Blackpill.")
                        
    # -------------------------------
    # 4) Save: apply Z height, draw_z, offsets, feed; bounds; preview
    # -------------------------------
    def _handle_save_and_preview(self):
        # -------------------------------
        # Sanity checks
        # -------------------------------
        if not getattr(self, "pgm_file", None) or not os.path.exists(self.pgm_file):
            self.logger.warning("No valid G-code file selected.")
            return

        if not getattr(self, "pgm_glist", None):
            self.showCustomPopup("Error", "Load a G-code file first.")
            return

        if not getattr(self, "zero_laser", None):
            self.showCustomPopup("Laser not set", "Select a laser before saving.")
            return

        # ---------------------------------------------------------
        # DETERMINE FILE TYPE (GCODE vs STL/SVG/DXF)
        # ---------------------------------------------------------
        file_lower = self.pgm_file.lower()
        is_gcode_file = file_lower.endswith((".gcode", ".nc", ".ngc", ".txt"))
        is_stl_svg_dxf = file_lower.endswith((".stl", ".svg", ".dxf"))

        # ---------------------------------------------------------
        # LOAD user-set values (session values)
        # ---------------------------------------------------------
        user_set_offset = getattr(self, "offset_user_set", False)
        user_set_drawz  = getattr(self, "draw_z_user", False)

        # ---------------------------------------------------------
        # LOAD config.ini values
        # ---------------------------------------------------------
        cfg = self.conf.ini_parser
        cfg_x = float(cfg.get("offset", "xoffset", fallback="0.0"))
        cfg_y = float(cfg.get("offset", "yoffset", fallback="0.0"))
        cfg_z = float(cfg.get("bed",    "draw_z",  fallback="0.0"))

        # ---------------------------------------------------------
        # APPLY RULES BASED ON FILE TYPE
        # ---------------------------------------------------------

        if is_gcode_file:
            # --- Case 1: G-code → ALWAYS use live offsets ---
            xindex = float(self.offset_x) if user_set_offset else 0.0
            yindex = float(self.offset_y) if user_set_offset else 0.0
            draw_z = float(self.draw_z_value) if user_set_drawz else 0.0

        else:
            # --- Case 2: STL, SVG, or DXF → PRIORITY selection ---

            # X/Y offset selection
            if user_set_offset:
                xindex = float(self.offset_x)
                yindex = float(self.offset_y)
            else:
                xindex = cfg_x
                yindex = cfg_y

            # draw Z selection
            if user_set_drawz:
                draw_z = float(self.draw_z_value)
            else:
                draw_z = cfg_z

        # Fallback (if somehow all values missing)
        xindex = xindex if xindex is not None else 0.0
        yindex = yindex if yindex is not None else 0.0
        draw_z = draw_z if draw_z is not None else 0.0

        # ---------------------------------------------------------
        # FEEDRATE (same for both types)
        # ---------------------------------------------------------
        feedrate = float(getattr(self, "pgm_feed", 0.0)) if hasattr(self, "pgm_feed") else None

        parser = self.gcode_parser

        # ======================================================
        # 1) Preprocess: cleaning, comments, wipe removal
        # ======================================================
        cleaned, layer_height = parser.preprocess_lines(self.pgm_glist)

        # ======================================================
        # 2) RAW bounds (before shifting)
        # ======================================================
        raw_bounds = parser.get_bounds(cleaned)
        if not raw_bounds:
            self.logger.error("Could not detect bounds of raw G-code.")
            return

        rawMinX = raw_bounds['MINX']
        rawMinY = raw_bounds['MINY']
        rawMaxX = raw_bounds['MAXX']
        rawMaxY = raw_bounds['MAXY']

        # ======================================================
        # 3) NORMALIZE so MINX = MINY = 0
        # ======================================================
        normShiftX = -rawMinX
        normShiftY = -rawMinY

        # ======================================================
        # 4) Apply final offsets AFTER normalization
        # ======================================================
        shiftX = normShiftX + xindex
        shiftY = normShiftY + yindex

        self.logger.info(f"Normalization shift: X={normShiftX:.3f}, Y={normShiftY:.3f}")
        self.logger.info(f"Using OFFSETS: X={xindex:.3f}, Y={yindex:.3f}, drawZ={draw_z:.3f}")
        self.logger.info(f"Final applied shift: X={shiftX:.3f}, Y={shiftY:.3f}")

        # ======================================================
        # 5) Bounds check
        # ======================================================
        finalMinX = rawMinX + shiftX
        finalMaxX = rawMaxX + shiftX
        finalMinY = rawMinY + shiftY
        finalMaxY = rawMaxY + shiftY

        if (finalMinX < self.bed_xmin or finalMaxX > self.bed_xmax or
            finalMinY < self.bed_ymin or finalMaxY > self.bed_ymax):

            error_msg = (
                f"Drawing exceeds bed area!\n\n"
                f"X: {finalMinX:.2f} → {finalMaxX:.2f} (Bed: {self.bed_xmin} → {self.bed_xmax})\n"
                f"Y: {finalMinY:.2f} → {finalMaxY:.2f} (Bed: {self.bed_ymin} → {self.bed_ymax})\n\n"
                "Please re-adjust the offsets."
            )
            
            if hasattr(self, 'logger') and self.logger:
                self.logger.error(f"Out of Bed Range: {error_msg.replace('\\n', ' | ')}")

            self.showCustomPopup(
                "Out of Bed Range",
                error_msg
            )
            self.showMainPage(1)
            return

        # ======================================================
        # 6) Apply full transform
        # ======================================================
        adjusted = parser.apply_full_transform(
            cleaned,
            shiftX, shiftY,
            draw_z,
            feedrate,
            user_set_drawz,
            self.layer_height,
            getattr(self, 'uv_time_ms', 0)
        )

        # ======================================================
        # 7) Save & Preview
        # ======================================================
        adjusted_path = Path(self.config_file_path).parent / "adjusted_preview.gcode"

        try:
            with open(adjusted_path, "w", newline="\n") as f:
                f.write("\n".join(adjusted))
        except Exception as e:
            self.logger.error(f"Failed to save adjusted G-code: {e}")
            return

        self.filtered_gcode = adjusted[:]  # Print buffer

        try:
            self.preview.loadGcode(adjusted)
            self.showMainPage(3)
        except Exception as e:
            self.logger.warning(f"Preview load failed: {e}")

        for ln in adjusted:
            self.util.debugPrint(ln)

    def update_profile_json(profile_path, layer_height, layer_height_0):
        """
        Update profile.json: set layer_height and layer_height_0 (if present in any section).
        Writes string values to match Cura-style profile content.
        """
        try:
            with open(profile_path, "r", encoding="utf-8") as f:
                data = json.load(f)
        except Exception as e:
            # If profile.json doesn't exist or can't be read, log/raise as needed.
            # Here we simply bail out silently (you can change to raise/log).
            print(f"[update_profile_json] failed to read {profile_path}: {e}")
            return

        updated = False
        for section, settings in data.items():
            if isinstance(settings, dict):
                if "layer_height" in settings:
                    settings["layer_height"] = str(layer_height)
                    updated = True
                if "layer_height_0" in settings:
                    settings["layer_height_0"] = str(layer_height_0)
                    updated = True

        if updated:
            try:
                with open(profile_path, "w", encoding="utf-8") as f:
                    json.dump(data, f, indent=4)
                print(f"[update_profile_json] Updated {profile_path} with layer_height={layer_height}, layer_height_0={layer_height_0}")
            except Exception as e:
                print(f"[update_profile_json] failed to write {profile_path}: {e}")
        else:
            # nothing to change
            print(f"[update_profile_json] No layer keys found in {profile_path}; nothing changed.")


    def printAction(self, widget):
        wobj = widget.objectName()
        
        if self.util.checkSubString(wobj, "run"):
            if hasattr(self, "filtered_gcode") and self.filtered_gcode:
                self.runProgram("run")

                self.wm.operate(self.printWidget.run, "enable", False)
                self.wm.operate(self.printWidget.pause, "enable", True)
                self.wm.operate(self.printWidget.abort, "enable", True)

            else:
                error_title = "Gcode File Error"
                error_text = "Filtered G-code not ready. Do SAVE first."
                self.showCustomPopup(error_title, error_text)
                self.showMainPage(2)
                    
        if self.util.checkSubString(wobj, "pause"):
            arg = None
            
            if not self.pause_flag:
                arg = "pause"
                self.pause_flag = True
            else:
                arg = "resume"
                self.pause_flag = False
                
            self.pauseWidget(widget, arg)
            self.runProgram(arg)
        
        if self.util.checkSubString(wobj, "abort"):
            self.runProgram("abort")
            self.wm.operate(self.printWidget.run, "enable", True)

        if self.util.checkSubString(wobj, "para"):
            page = self.findChild(QWidget, "parameterPage")
            if page:
                self.mainStack.setCurrentWidget(page)
                # Default to bedPage and highlight the bed button
                if hasattr(self, 'paraBtn1') and self.paraBtn1:
                    self.parameterAction(self.paraBtn1)
    
    def pauseWidget(self, widget, arg):
        icon_dict = {"pause" : QIcon(":./icons/icons/play-circle.svg"),
                     "resume" : QIcon(":./icons/icons/pause.svg")
                     }
        
        if arg in icon_dict:
            widget.setIcon(icon_dict.get(arg))

    def runProgram(self, arg):
        if arg == "run":
            if hasattr(self, "filtered_gcode") and self.filtered_gcode:
                self.ui.uvonPushButton.setEnabled(False)
                self.ui.uvoffPushButton.setEnabled(False)
                self.pgm_run_flag = True
                self.pgm_pause_flag = False
                self.pgm_index = 0
                self.seg_index = 0
                self.preview.resetPreview()
                self.initProgram()
                self.logger.info("Print Status : RUN")

        elif arg == "pause":
            self.pgm_pause_flag = True
            self.logger.info("Print Status : PAUSE")

        elif arg == "resume":
            self.pgm_pause_flag = False
            self.resumeProgram()
            self.logger.info("Print Status : RESUME")

        elif arg == "abort":
            self.ui.uvonPushButton.setEnabled(True)
            self.ui.uvoffPushButton.setEnabled(True)
            self.pgm_run_flag = False
            self.pgm_pause_flag = False
            self.pgm_index = 0
            self.seg_index = 0

            self.initProgress()
            self.preview.clear()
            self.filtered_gcode = []
            self.pgm_glist = []
            self.pgm_mlist = []

            pausebtn = self.printWidget.pause
            self.pauseWidget(pausebtn, "pause")
            self.wm.operate(self.printWidget.pause, "enable", False)
            self.wm.operate(self.printWidget.abort, "enable", False)

            self.programInit()
            self.sendGcode("G28\n")
            self.logger.info("Print Status : ABORT")
            self.showMainPage(2)

    def startProgram(self):
        gcode = self.filtered_gcode[self.pgm_index]
        self.pgm_index += 1
        self.pgmGcode(gcode)
        self.pgmGcode("G4 S1")
        self.pgmGcode("M114")

    def initProgram(self):
        if self.pgm_run_flag:
            self.util.debugPrint(f"segment dict : {self.preview.segment_dict}")
            self.initProgress()
            self.util.debugPrint(f"len : {len(self.filtered_gcode)}")
            self.util.debugPrint(f"Print init : {self.pgm_index}")
            self.startProgram()

    def resumeProgram(self):
        if self.pgm_run_flag:
            self.util.debugPrint(f"Print resume : {self.pgm_index}")
            self.startProgram()

    def finishProgram(self):
        self.ui.uvonPushButton.setEnabled(True)
        self.ui.uvoffPushButton.setEnabled(True)
        self.pgm_index = 0
        self.seg_index = 0
        self.prev_segment = 0
        self.wm.operate(self.printWidget.run, "enable", True)
        self.wm.operate(self.printWidget.pause, "enable", False)
        self.wm.operate(self.printWidget.abort, "enable", False)

    def indexProgram(self):
        if self.pgm_run_flag and not self.pgm_pause_flag:
            self.util.debugPrint(f"index : {self.pgm_index}")

            if self.pgm_index < len(self.filtered_gcode):
                gcode = self.filtered_gcode[self.pgm_index]

                self.pgm_index += 1
                self.pgmGcode(gcode)
                self.pgmGcode("G4 S1")
                self.pgmGcode("M114")
                self.getProgress(self.pgm_index, len(self.filtered_gcode))
                self.markSegment(gcode)

            else:
                self.pgm_run_flag = False
                self.finishProgram()

    def markSegment(self, gcode):
        self.preview.markSegment(gcode)

    def getProgress(self, index, total):
        if index is not None and total is not None:
            if total > 0:

                frac = 0 if total <= 0 else min(index / total, 1.0)
                self.progress = round(frac * 100, 2)

                self.showProgress()

    def showProgress(self):
        self.updateProgress(self.printWidget.progress_signal, self.progress)
        self.wm.operate(self.printWidget.print, "set", f"{self.progress:.2f}%")

    def initProgress(self):
        self.progress = 0
        self.updateProgress(self.printWidget.progress_signal, self.progress)
        self.wm.operate(self.printWidget.print, "set", f"{self.progress:.2f}%")
        
    def clearPreview(self):
        self.preview.segment_dict = {}
        self.preview.update()
        
    def parabedAction(self, widget):
        wobj = widget.objectName()
        print(f"wobj : {wobj}")
        
        if self.util.checkSubString(wobj, "set"):
            val = self.wm.operate(self.parabedWidget.set_line, "get")
            if val is not None and val != "":
                # Handle bed temperature setting
                gcode = f"M140 S{val}"
                self.sendGcode(gcode)
                self.logger.info(f"Bed temperature set to {val}")
                
        elif self.util.checkSubString(wobj, "parabkbedPushButton"):
            # Go back to print page
            page = self.findChild(QWidget, "printPage")
            if page:
                self.mainStack.setCurrentWidget(page)

    def paraextrusionAction(self, widget):
        wobj = widget.objectName()
        print(f"wobj : {wobj}")
        
        if self.util.checkSubString(wobj, "set"):
            val = self.wm.operate(self.paraextrusionWidget.set_line, "get")
            if val is not None and val != "":
                # Handle pressure/extrusion setting
                gcode = f"M104 S{val}"
                self.sendGcode(gcode)
                self.logger.info(f"Extrusion pressure/temp set to {val}")
                
        elif self.util.checkSubString(wobj, "parabkprPushButton"):
            # Go back to print page
            page = self.findChild(QWidget, "printPage")
            if page:
                self.mainStack.setCurrentWidget(page)

    def parauvAction(self, widget):
        wobj = widget.objectName()
        print(f"wobj : {wobj}")
        
        if self.util.checkSubString(wobj, "uvon"):
            self.logger.info("UV turned ON manually.")
            # Emit UV ON command
            pass
            
        elif self.util.checkSubString(wobj, "uvoff"):
            self.logger.info("UV turned OFF manually.")
            # Emit UV OFF command
            pass
            
        elif self.util.checkSubString(wobj, "parabkuv"):
            # Go back to print page
            page = self.findChild(QWidget, "printPage")
            if page:
                self.mainStack.setCurrentWidget(page)

    def parameterAction(self, widget):
        wobj = widget.objectName()
        para_stack = self.findChild(QStackedWidget, "stackedWidget")
        
        if not para_stack:
            return
            
        # Use Qt's built-in checkable state to trigger the :checked CSS defined in UI
        all_para_btns = [btn for btn in [
            self.findChild(QPushButton, "nozzlePushButton"),
            self.findChild(QPushButton, "printheadPushButton"),
            self.paraBtn1, self.paraBtn2, self.paraBtn3
        ] if btn is not None]
        
        for btn in all_para_btns:
            btn.setCheckable(True)
            btn.setChecked(False)
        
        if widget and widget in all_para_btns:
            widget.setChecked(True)

        if self.util.checkSubString(wobj, "bed"):
            page = self.findChild(QWidget, "bedPage")
            if page:
                para_stack.setCurrentWidget(page)
        elif self.util.checkSubString(wobj, "pressure"):
            page = self.findChild(QWidget, "extrusionPpage")
            if page:
                para_stack.setCurrentWidget(page)
        elif self.util.checkSubString(wobj, "uv"):
            page = self.findChild(QWidget, "uvPpage")
            if page:
                para_stack.setCurrentWidget(page)

    def terminalAction(self, widget):
        wobj = widget.objectName()
        
        if self.util.checkSubString(wobj, "send"):
            gcode = self.wm.operate(self.terminalWidget.input, "get")
            
            if gcode:
                self.wm.operate(self.terminalWidget.input, "clear")
                self.sendGcode(gcode)
                self.sendGcode("M114")
                
    def receiveACK(self, widget, arg):
        if widget:
            self.wm.operate(widget, "add", value=arg)
            
    def profileAction(self, widget):
        wobj = widget.objectName()
        
        if self.util.checkSubString(wobj, "set"):
            
            user = self.wm.operate(self.profileWidget.user, "get")
            password = self.wm.operate(self.profileWidget.password, "get")
            self.wm.operate(self.profileWidget.password, "clear")
            
            self.util.debugPrint(f"user : {user} | password : {password}")
            
            if user == "Operator" and password == "012345":
                self.logger.info("Profile : Operator")
                self.wm.operate(self.leftMenuWidget.terminal, "hide")
                self.wm.operate(self.centerMenuWidget.settings, "hide")
            
            if user == "Supervisor" and password == "452301":
                self.logger.info("Profile : Supervisor")
                self.wm.operate(self.leftMenuWidget.terminal, "show")
                self.wm.operate(self.leftMenuWidget.laser, "show")
                self.wm.operate(self.centerMenuWidget.settings, "hide")

                QTimer.singleShot(600000, self.resetProfile)
            
            if user == "Technician" and password == "543210":
                self.logger.info("Profile : Technician")
                self.wm.operate(self.leftMenuWidget.terminal, "show")
                self.wm.operate(self.leftMenuWidget.laser, "show")
                self.wm.operate(self.centerMenuWidget.settings, "hide")     

                QTimer.singleShot(600000, self.resetProfile)

    def resetProfile(self):
        self.wm.operate(self.leftMenuWidget.terminal, "hide")
        self.wm.operate(self.centerMenuWidget.settings, "hide")

        self.logger.info("Profile is reset")
        self.logger.info("Profile : Operator")

    def changeEvent(self, event):
        """Handle window state changes (maximize/restore) to keep buttons in sync."""
        if event.type() == QEvent.WindowStateChange:
            if hasattr(self.ui, 'restorePushButton'):
                if self.isMaximized():
                    self.ui.restorePushButton.setIcon(QIcon(":/icons/icons/copy.svg"))
                    self.ui.restorePushButton.setToolTip("Restore")
                else:
                    self.ui.restorePushButton.setIcon(QIcon(":/icons/icons/square.svg"))
                    self.ui.restorePushButton.setToolTip("Maximize")
                
                # FIX: Force floating notification container to recalculate its position
                # after a short delay to allow the window resize to complete.
                if hasattr(self, 'notifyMenu'):
                    QTimer.singleShot(100, lambda: self.notifyMenu.update())
                    QTimer.singleShot(200, lambda: self.notifyMenu.updateGeometry())
        
        super().changeEvent(event)
            

import datetime

class Tee:
    def __init__(self, name, mode):
        self.file = open(name, mode)
        self.stdout = sys.stdout
        self.file.write(f"\n{'='*50}\nSession Started: {datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n{'='*50}\n")
        self.file.flush()
    def write(self, data):
        self.file.write(data)
        self.file.flush()
        self.stdout.write(data)
        self.stdout.flush()
    def flush(self):
        self.file.flush()
        self.stdout.flush()

if __name__ == '__main__':
    # Redirect all console output to BOTH the terminal and a file
    tee_logger = Tee("terminal_logs.txt", "a")
    sys.stdout = tee_logger
    sys.stderr = tee_logger
    
    app = QApplication(sys.argv)
    window = MainWindow()
    window.show()
    sys.exit(app.exec_()) 
    