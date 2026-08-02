import sys
import numpy as np # Assuming image data will be numpy arrays
from PyQt5.QtWidgets import QApplication, QMainWindow, QGraphicsView, QGraphicsScene, QVBoxLayout, QWidget, QLabel, QAction, QFileDialog
from PyQt5.QtGui import QPixmap, QImage, QPainter
from PyQt5.QtCore import Qt, QRectF, QPointF, QThread, pyqtSignal, pyqtSlot
from ui.config.cfgcxt import config_context # Import config_context
from utils.utils import logger # Import logger


# For IPC
from multiprocessing import Queue
import queue
import time # For simulation

class ImageReceiverThread(QThread):
    image_received = pyqtSignal(np.ndarray) # Signal to send numpy array to main thread

    def __init__(self, image_queue: Queue):
        super().__init__()
        self.image_queue = image_queue
        self._running = True

    def run(self):
        while self._running:
            try:
                image_data = self.image_queue.get(timeout=0.1)
            except queue.Empty:
                continue

            if image_data is None: # Sentinel for shutdown
                self._running = False
                break

            self.image_received.emit(image_data)

    def stop(self):
        self._running = False
        self.wait() # Wait for the thread to finish execution

class ImageGraphicsView(QGraphicsView):
    def __init__(self, scene, parent=None):
        super().__init__(scene, parent)
        self.setDragMode(QGraphicsView.NoDrag)
        self.setCursor(Qt.ArrowCursor)
        self._pan_active = False
        self._pan_start = None

    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton:
            self._pan_active = True
            self._pan_start = event.pos()
            self.setCursor(Qt.ClosedHandCursor)
            event.accept()
        else:
            super().mousePressEvent(event)

    def mouseMoveEvent(self, event):
        if self._pan_active and self._pan_start is not None:
            delta = event.pos() - self._pan_start
            self._pan_start = event.pos()
            self.horizontalScrollBar().setValue(self.horizontalScrollBar().value() - delta.x())
            self.verticalScrollBar().setValue(self.verticalScrollBar().value() - delta.y())
            event.accept()
        else:
            super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event):
        if event.button() == Qt.LeftButton:
            self._pan_active = False
            self._pan_start = None
            self.setCursor(Qt.ArrowCursor)
            event.accept()
        else:
            super().mouseReleaseEvent(event)

    def wheelEvent(self, event):
        factor = 1.2
        if event.angleDelta().y() > 0:
            self.scale(factor, factor)
        else:
            self.scale(1 / factor, 1 / factor)
        event.accept()

class RealtimeImageViewer(QMainWindow):
    def __init__(self, image_queue: Queue = None):
        super().__init__()
        self.setWindowTitle("Real-time Image Display")
        self.setGeometry(100, 100, 800, 600)

        self.scene = QGraphicsScene(self)
        self.view = ImageGraphicsView(self.scene)
        self.view.setRenderHint(QPainter.Antialiasing)
        self.view.setCursor(Qt.ArrowCursor)
        self.view.setTransformationAnchor(QGraphicsView.AnchorUnderMouse)

        self.image_item = None
        self.image_list = [] # Initialize a list to store incoming images

        self.status_label = QLabel("X: -, Y: -")
        self.statusBar().addWidget(self.status_label)

        central_widget = QWidget()
        layout = QVBoxLayout(central_widget)
        layout.addWidget(self.view)
        self.setCentralWidget(central_widget)

        self._create_actions()
        self._create_menus()

        # Mouse tracking for coordinates
        self.view.setMouseTracking(True)
        self.view.coord_callback = self._custom_mouse_move_event

        self.image_queue = image_queue
        logger.info(f"RealtimeImageViewer received queue: {self.image_queue}")
        if self.image_queue is not None:
            logger.info("Create ImageReciverThread")
            self.receiver_thread = ImageReceiverThread(self.image_queue)
            self.receiver_thread.image_received.connect(self.update_image_from_numpy)
            self.receiver_thread.start()
        else:
            self.receiver_thread = None

    def closeEvent(self, event):
        if self.receiver_thread:
            self.receiver_thread.stop()
        super().closeEvent(event)

    def _create_actions(self):
        self.save_action = QAction("&Save Image...", self)
        self.save_action.setShortcut("Ctrl+S")
        self.save_action.setStatusTip("Save current displayed image")
        self.save_action.triggered.connect(self._save_image)

    def _create_menus(self):
        file_menu = self.menuBar().addMenu("&File")
        file_menu.addAction(self.save_action)

    def _custom_mouse_move_event(self, event):
        if self.image_item:
            scene_pos = self.view.mapToScene(event.pos())
            item_pos = self.image_item.mapFromScene(scene_pos)
            # Ensure coordinates are within image bounds for display
            pixmap = self.image_item.pixmap()
            if pixmap and 0 <= item_pos.x() < pixmap.width() and 0 <= item_pos.y() < pixmap.height():
                self.status_label.setText(f"X: {item_pos.x():.0f}, Y: {item_pos.y():.0f}")
            else:
                self.status_label.setText("X: -, Y: -")
        else:
            self.status_label.setText("X: -, Y: -")
        # Call the original QGraphicsView's mouseMoveEvent for internal handling (e.g., ScrollHandDrag)
        QGraphicsView.mouseMoveEvent(self.view, event)

    def _save_image(self):
        if not self.image_item:
            return

        file_name, _ = QFileDialog.getSaveFileName(self, "Save Image", "", "TIFF Image (*.tif);;All Files (*)")
        if file_name:
            # Get the full image from the QGraphicsPixmapItem
            full_pixmap = self.image_item.pixmap()
            full_image = full_pixmap.toImage()

            # For DPI, QImage has setDpiX/Y. Get DPI from config_context.
            try:
                target_dpi = float(config_context.config.get("dpi", "300")) # Default to 300 if not found or invalid
            except ValueError:
                target_dpi = 300.0 # Fallback if conversion fails

            full_image.setDotsPerMeterX(int(target_dpi / 0.0254))
            full_image.setDotsPerMeterY(int(target_dpi / 0.0254))

            full_image.save(file_name, "TIFF")
            logger.info(f"Image saved to {file_name}")

    @pyqtSlot(np.ndarray)
    def update_image_from_numpy(self, numpy_image):
        self.image_list.append(numpy_image)
        # Vertically stack all images in the list
        stacked_image = np.vstack(self.image_list)

        # Convert stacked_image to QImage
        h, w = stacked_image.shape[:2]
        bytes_per_line = stacked_image.strides[0]

        if stacked_image.ndim == 2: # Grayscale
            q_image = QImage(stacked_image.data, w, h, bytes_per_line, QImage.Format_Grayscale8)
        elif stacked_image.ndim == 3 and stacked_image.shape[2] == 3: # RGB
            q_image = QImage(stacked_image.data, w, h, bytes_per_line, QImage.Format_RGB888)
            q_image = q_image.rgbSwapped() # OpenCV/numpy is BGR, QImage is RGB
        elif stacked_image.ndim == 3 and stacked_image.shape[2] == 4: # RGBA
            q_image = QImage(stacked_image.data, w, h, bytes_per_line, QImage.Format_RGBA8888)
            q_image = q_image.rgbSwapped() # OpenCV/numpy is BGRA, QImage is RGBA
        else:
            logger.error("Unsupported NumPy image format.")
            return

        pixmap = QPixmap.fromImage(q_image)
        if self.image_item:
            self.image_item.setPixmap(pixmap)
        else:
            self.image_item = self.scene.addPixmap(pixmap)
            self.view.fitInView(self.image_item, Qt.KeepAspectRatio) # Fit image on first load
        self.scene.setSceneRect(self.image_item.boundingRect()) # Set scene rect to image bounds

    # Mouse wheel event for zooming
    def wheelEvent(self, event):
        factor = 1.2 # Zoom factor
        if event.angleDelta().y() > 0:
            self.view.scale(factor, factor) # Zoom in
        else:
            self.view.scale(1 / factor, 1 / factor) # Zoom out

def run_viewer(image_queue: Queue = None):
    app = QApplication(sys.argv)
    viewer = RealtimeImageViewer(image_queue)
    viewer.show()
    sys.exit(app.exec_())
