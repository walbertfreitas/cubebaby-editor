"""Usa o PyQt6 (pacote do sistema no Ubuntu/Zorin) ou, se não houver, o PySide6."""
try:
    from PyQt6 import QtCore, QtGui, QtWidgets
    from PyQt6.QtCore import pyqtSignal as Signal
except ImportError:  # ambiente de desenvolvimento com PySide6
    from PySide6 import QtCore, QtGui, QtWidgets
    from PySide6.QtCore import Signal

__all__ = ["QtCore", "QtGui", "QtWidgets", "Signal"]
