from PySide6.QtWidgets import QWidget, QHBoxLayout, QPushButton, QLabel, QTextEdit, QMessageBox, QProgressBar
from PySide6.QtCore import Qt, QEventLoop, QTimer

class NotifierUI:
    @staticmethod
    def setup(main_window):
        # Increase size limits to accommodate buttons
        if hasattr(main_window, 'notify_menu_widgets') and main_window.notify_menu_widgets.notify:
            main_window.notify_menu_widgets.notify.setMaximumHeight(180)
        
        # Manually find sub-container because it wasn't mapped in setupNotifyMenu
        notifySubContainer = main_window.findChild(QWidget, "notifySubContainer")
        
        if notifySubContainer:
            notifySubContainer.setMaximumHeight(180)
            notifySubContainer.layout().setContentsMargins(0, 0, 0, 0)
            notifySubContainer.setStyleSheet("""
                QWidget#notifySubContainer {
                    background-color: rgb(167, 198, 229);
                    color: rgb(16, 42, 83);
                    border-radius: 15px;
                    border: 2px solid rgb(16, 42, 131);
                }
            """)

        notifyLabel = main_window.findChild(QLabel, "notifyLabel")
        if notifyLabel:
            main_window.notifyLabel = notifyLabel
            notifyLabel.setMinimumHeight(35)
            notifyLabel.setStyleSheet("""
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

        notifyTextEdit = main_window.findChild(QTextEdit, "notifyTextEdit")
        if notifyTextEdit:
            main_window.notifyTextEdit = notifyTextEdit
            notifyTextEdit.setReadOnly(True)
            notifyTextEdit.setStyleSheet("""
                QTextEdit {
                    background-color: transparent;
                    color: rgb(16, 42, 83);
                    border: none;
                    font-size: 13px;
                    padding: 10px 15px;
                }
            """)

        # Style the close button
        closeNotifyBtn = main_window.findChild(QPushButton, "closeNotifyPushButton")
        if closeNotifyBtn:
            closeNotifyBtn.setStyleSheet("""
                QPushButton {
                    background-color: transparent;
                    border: none;
                    padding: 5px;
                    margin-right: 5px;
                }
                QPushButton:hover {
                    background-color: rgba(16, 42, 131, 50);
                    border-radius: 15px;
                }
            """)
            closeNotifyBtn.clicked.connect(lambda: main_window.onPopupBtnClicked(QMessageBox.Cancel))

        if notifySubContainer:
            # Container for buttons.
            main_window.notifyBtnContainer = QWidget(notifySubContainer)
            main_window.notifyBtnContainer.setStyleSheet("background-color: transparent;")
            main_window.notifyBtnLayout = QHBoxLayout(main_window.notifyBtnContainer)
            main_window.notifyBtnLayout.setContentsMargins(0, 0, 0, 5)
            main_window.notifyBtnLayout.setSpacing(10)
            main_window.notifyBtnLayout.setAlignment(Qt.AlignCenter)
            
            notifySubContainer.layout().addWidget(main_window.notifyBtnContainer)
            
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
                
            main_window.btnOk.clicked.connect(lambda: main_window.onPopupBtnClicked(QMessageBox.Ok))
            main_window.btnYes.clicked.connect(lambda: main_window.onPopupBtnClicked(QMessageBox.Yes))
            main_window.btnNo.clicked.connect(lambda: main_window.onPopupBtnClicked(QMessageBox.No))
            main_window.btnCancel.clicked.connect(lambda: main_window.onPopupBtnClicked(QMessageBox.Cancel))

            main_window.notifyProgressBar = QProgressBar()
            main_window.notifyProgressBar.setRange(0, 100)
            main_window.notifyProgressBar.setTextVisible(True)
            main_window.notifyProgressBar.setStyleSheet("""
                QProgressBar {
                    border: 2px solid rgb(16, 42, 131);
                    border-radius: 5px;
                    text-align: center;
                    color: rgb(16, 42, 83);
                    font-weight: bold;
                }
                QProgressBar::chunk {
                    background-color: rgb(16, 42, 131);
                    width: 10px;
                    margin: 0.5px;
                }
            """)
            main_window.notifyProgressBar.hide()
            main_window.notifyBtnLayout.addWidget(main_window.notifyProgressBar)

            main_window.btnCancelDownload = QPushButton("Cancel")
            main_window.btnCancelDownload.setStyleSheet(btn_style)
            main_window.btnCancelDownload.hide()
            main_window.notifyBtnLayout.addWidget(main_window.btnCancelDownload)
            main_window.btnCancelDownload.clicked.connect(lambda: main_window.onCancelDownloadClicked())

        # --- Notification System Setup ---
        main_window.popupLoop = QEventLoop(main_window)
        main_window.popupResult = QMessageBox.Ok

    @staticmethod
    def onPopupBtnClicked(main_window, result):
        main_window.popupResult = result
        if main_window.popupLoop.isRunning():
            main_window.popupLoop.quit()
            
        # Only collapse if it's not a 'Yes' to an update prompt (to prevent jarring transition to progress bar)
        if result != QMessageBox.Yes:
            if hasattr(main_window, 'notifyMenu') and main_window.notifyMenu:
                main_window.notifyMenu.collapseMenu()
            elif hasattr(main_window, 'notify_menu_widgets') and main_window.notify_menu_widgets.notify:
                main_window.notify_menu_widgets.notify.collapseMenu()
        
    @staticmethod
    def showCustomPopup(main_window, title, message, buttons=QMessageBox.Ok):
        """Show notification in the slide-in panel and block until user responds."""
        # Stop auto-close timer if it's currently ticking from a previous message
        if hasattr(main_window, '_auto_close_timer') and main_window._auto_close_timer.isActive():
            main_window._auto_close_timer.stop()
            
        if hasattr(main_window, "notifyLabel"):
            main_window.notifyLabel.setText(title)
        if hasattr(main_window, "notifyTextEdit"):
            main_window.notifyTextEdit.setText(message)

        # Reset all buttons & progress bar
        if hasattr(main_window, "notifyProgressBar"):
            main_window.notifyProgressBar.hide()
        if hasattr(main_window, "btnCancelDownload"):
            main_window.btnCancelDownload.hide()
        main_window.btnOk.hide()
        main_window.btnYes.hide()
        main_window.btnNo.hide()
        main_window.btnCancel.hide()

        if buttons & QMessageBox.Ok:     main_window.btnOk.show()
        if buttons & QMessageBox.Yes:    main_window.btnYes.show()
        if buttons & QMessageBox.No:     main_window.btnNo.show()
        if buttons & QMessageBox.Cancel: main_window.btnCancel.show()

        if hasattr(main_window, 'notifyMenu') and main_window.notifyMenu:
            main_window.notifyMenu.expandMenu()
        elif hasattr(main_window, 'notify_menu_widgets') and main_window.notify_menu_widgets.notify:
            main_window.notify_menu_widgets.notify.expandMenu()
            
        if main_window.popupLoop.isRunning():
            main_window.popupLoop.quit()
            
        main_window.popupLoop.exec()
        return main_window.popupResult

    @staticmethod
    def showAutoCloseMessage(main_window, title, message, timeout_ms=5000):
        """Show notification that auto-collapses after timeout_ms ms."""
        if hasattr(main_window, "notifyLabel"):
            main_window.notifyLabel.setText(title)
        if hasattr(main_window, "notifyTextEdit"):
            main_window.notifyTextEdit.setText(message)

        if hasattr(main_window, "notifyProgressBar"):
            main_window.notifyProgressBar.hide()
        if hasattr(main_window, "btnCancelDownload"):
            main_window.btnCancelDownload.hide()
        main_window.btnOk.hide()
        main_window.btnYes.hide()
        main_window.btnNo.hide()
        main_window.btnCancel.hide()

        if hasattr(main_window, 'notifyMenu') and main_window.notifyMenu:
            main_window.notifyMenu.expandMenu()
        elif hasattr(main_window, 'notify_menu_widgets') and main_window.notify_menu_widgets.notify:
            main_window.notify_menu_widgets.notify.expandMenu()
        
        # Keep a persistent reference to the timer to prevent garbage collection
        if hasattr(main_window, '_auto_close_timer'):
            main_window._auto_close_timer.stop()
            main_window._auto_close_timer.deleteLater()
            
        main_window._auto_close_timer = QTimer(main_window)
        main_window._auto_close_timer.setSingleShot(True)
        
        if hasattr(main_window, 'notifyMenu') and main_window.notifyMenu:
            main_window._auto_close_timer.timeout.connect(main_window.notifyMenu.collapseMenu)
        elif hasattr(main_window, 'notify_menu_widgets') and main_window.notify_menu_widgets.notify:
            main_window._auto_close_timer.timeout.connect(main_window.notify_menu_widgets.notify.collapseMenu)
            
        main_window._auto_close_timer.start(timeout_ms)

    @staticmethod
    def showProgressUI(main_window, title, message):
        """Shows the notifier panel with a progress bar and hides all buttons."""
        if hasattr(main_window, '_auto_close_timer') and main_window._auto_close_timer.isActive():
            main_window._auto_close_timer.stop()
            
        if hasattr(main_window, "notifyLabel"):
            main_window.notifyLabel.setText(title)
        if hasattr(main_window, "notifyTextEdit"):
            main_window.notifyTextEdit.setText(message)

        # Hide buttons
        main_window.btnOk.hide()
        main_window.btnYes.hide()
        main_window.btnNo.hide()
        main_window.btnCancel.hide()

        # Show progress bar and cancel button
        if hasattr(main_window, "notifyProgressBar"):
            main_window.notifyProgressBar.setValue(0)
            main_window.notifyProgressBar.show()
        if hasattr(main_window, "btnCancelDownload"):
            main_window.btnCancelDownload.show()

        if hasattr(main_window, 'notifyMenu') and main_window.notifyMenu:
            main_window.notifyMenu.expandMenu()
        elif hasattr(main_window, 'notify_menu_widgets') and main_window.notify_menu_widgets.notify:
            main_window.notify_menu_widgets.notify.expandMenu()

    @staticmethod
    def updateProgress(main_window, value):
        if hasattr(main_window, "notifyProgressBar"):
            main_window.notifyProgressBar.setValue(int(value))

