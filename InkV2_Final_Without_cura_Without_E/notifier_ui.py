from PySide6.QtWidgets import QWidget, QHBoxLayout, QPushButton, QLabel, QTextEdit, QMessageBox
from PySide6.QtCore import Qt, QEventLoop, QTimer

class NotifierUI:
    @staticmethod
    def setup(main_window):
        # notify menu widgets
        main_window.notifyMenu = main_window.findChild(QWidget, "notifyContainer") # Usually QCustomSlideMenu, but QWidget is safe for findChild
        main_window.notifyMenuBtn1 = main_window.findChild(QPushButton, "closeNotifyPushButton")
        main_window.notifyLabel = main_window.findChild(QLabel, "notifyLabel")
        main_window.notifyTextEdit = main_window.findChild(QTextEdit, "notifyTextEdit")
        main_window.notifySubContainer = main_window.findChild(QWidget, "notifySubContainer")

        if main_window.notifyTextEdit:
            main_window.notifyTextEdit.setReadOnly(True)

        # Apply Premium CSS for the notification container
        if main_window.notifySubContainer:
            main_window.notifySubContainer.layout().setContentsMargins(0, 0, 0, 0)
            main_window.notifySubContainer.setStyleSheet("""
                QWidget#notifySubContainer {
                    background-color: rgb(167, 198, 229); 
                    color: rgb(16, 42, 83); 
                    border-radius: 15px;
                    border: 2px solid rgb(16, 42, 131);
                }
            """)
        if main_window.notifyLabel:
            main_window.notifyLabel.setMinimumHeight(35)
            main_window.notifyLabel.setStyleSheet("""
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
        if main_window.notifyTextEdit:
             main_window.notifyTextEdit.setStyleSheet("""
                QTextEdit {
                    background-color: transparent; 
                    color: rgb(16, 42, 83); 
                    border: none; 
                    font-size: 13px; 
                    padding: 10px 15px;
                }
             """)

        # Increase size limits to accommodate buttons
        if main_window.notifyMenu:
            main_window.notifyMenu.setMaximumHeight(180)
        if main_window.notifySubContainer:
            main_window.notifySubContainer.setMaximumHeight(180)

        # --- Notification System Setup ---
        main_window.popupLoop = QEventLoop(main_window)
        main_window.popupResult = QMessageBox.Ok

        # Container for buttons
        if main_window.notifySubContainer:
            main_window.notifyBtnContainer = QWidget(main_window.notifySubContainer)
            main_window.notifyBtnContainer.setStyleSheet("background-color: transparent;")
            main_window.notifyBtnLayout = QHBoxLayout(main_window.notifyBtnContainer)
            main_window.notifyBtnLayout.setContentsMargins(0, 0, 0, 5)
            main_window.notifyBtnLayout.setSpacing(10)
            main_window.notifyBtnLayout.setAlignment(Qt.AlignCenter)

            main_window.notifySubContainer.layout().addWidget(main_window.notifyBtnContainer)

            main_window.btnOk = QPushButton("OK")
            main_window.btnYes = QPushButton("Yes")
            main_window.btnNo = QPushButton("No")
            main_window.btnCancel = QPushButton("Cancel")

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

            for btn in [main_window.btnOk, main_window.btnYes, main_window.btnNo, main_window.btnCancel]:
                btn.setStyleSheet(btn_style)
                btn.hide()
                main_window.notifyBtnLayout.addWidget(btn)

            main_window.btnOk.clicked.connect(lambda: NotifierUI.onPopupBtnClicked(main_window, QMessageBox.Ok))
            main_window.btnYes.clicked.connect(lambda: NotifierUI.onPopupBtnClicked(main_window, QMessageBox.Yes))
            main_window.btnNo.clicked.connect(lambda: NotifierUI.onPopupBtnClicked(main_window, QMessageBox.No))
            main_window.btnCancel.clicked.connect(lambda: NotifierUI.onPopupBtnClicked(main_window, QMessageBox.Cancel))

            if main_window.notifyMenuBtn1:
                main_window.notifyMenuBtn1.clicked.disconnect()
                main_window.notifyMenuBtn1.clicked.connect(lambda: NotifierUI.onPopupBtnClicked(main_window, QMessageBox.Cancel))

    @staticmethod
    def onPopupBtnClicked(main_window, result):
        main_window.popupResult = result
        if main_window.popupLoop.isRunning():
            main_window.popupLoop.quit()
        if hasattr(main_window.notifyMenu, 'collapseMenu'):
            main_window.notifyMenu.collapseMenu()
        else:
            main_window.notifyMenu.hide()

    @staticmethod
    def showCustomPopup(main_window, title, message, icon_type="info", buttons=QMessageBox.Ok, delay=0):
        """
        Displays a notification in the notifyContainer.
        Blocks until user interaction if buttons are provided, matching Bio4D style.
        """
        if main_window.notifyLabel:
            main_window.notifyLabel.setText(title)
        if main_window.notifyTextEdit:
            main_window.notifyTextEdit.setPlainText(message)
        
        # Reset buttons
        main_window.btnOk.hide()
        main_window.btnYes.hide()
        main_window.btnNo.hide()
        main_window.btnCancel.hide()
        
        # Show requested buttons
        if buttons & QMessageBox.Ok:
            main_window.btnOk.show()
        if buttons & QMessageBox.Yes:
            main_window.btnYes.show()
        if buttons & QMessageBox.No:
            main_window.btnNo.show()
        if buttons & QMessageBox.Cancel:
            main_window.btnCancel.show()

        # Slide in
        # FIX: Force the floating menu to recalculate its position relative to the window
        if hasattr(main_window.notifyMenu, 'floatReposition'):
            main_window.notifyMenu.floatReposition()
        elif hasattr(main_window.notifyMenu, 'reposition'):
            main_window.notifyMenu.reposition()
            
        if hasattr(main_window.notifyMenu, 'expandMenu'):
            main_window.notifyMenu.expandMenu()
        else:
            main_window.notifyMenu.show()
        
        # If no buttons are shown, it's just an informative message
        if buttons == 0 or (not any(b.isVisible() for b in [main_window.btnOk, main_window.btnYes, main_window.btnNo, main_window.btnCancel])):
            if delay > 0:
                if hasattr(main_window.notifyMenu, 'collapseMenu'):
                    QTimer.singleShot(delay, main_window.notifyMenu.collapseMenu)
                else:
                    QTimer.singleShot(delay, main_window.notifyMenu.hide)
            return QMessageBox.Ok

        # Block and wait
        main_window.popupLoop.exec()
        
        return main_window.popupResult
