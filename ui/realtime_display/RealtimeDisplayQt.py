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

# Rows of stitched web the live viewer keeps. At the production canvas width
# (21259 px) this caps the buffer at roughly 87 MB; a strip is ~834 rows, so
# about five strips stay visible. The viewer is a monitor, not the archive -
# the full image goes out on the data socket.
MAX_VIEW_ROWS = 4096

class ImageReceiverThread(QThread):
    image_received = pyqtSignal(np.ndarray) # Signal to send numpy array to main thread
    shutdown_requested = pyqtSignal()       # sentinel arrived - close the window

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
                self.shutdown_requested.emit()
                break

            self.image_received.emit(image_data)

    def stop(self):
        self._running = False
        # bounded wait: the loop polls at 100 ms, so this returns promptly. Never
        # block the GUI thread forever on a wedged queue.
        if not self.wait(2000):
            self.terminate()
            self.wait(500)

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
        # Report image coordinates for every pointer movement, including while panning.
        coord_callback = getattr(self, "coord_callback", None)
        if coord_callback:
            coord_callback(event)

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
        # Rolling view buffer. The old code kept every strip in a list and
        # re-ran np.vstack over the whole history on each frame: unbounded
        # memory and O(n^2) copying, which on a long roll (17.7 MB per strip)
        # exhausts RAM and freezes the display. Now a preallocated window is
        # written in place, and the oldest half is dropped in one shift when it
        # fills, so memory is capped and the per-strip copy is O(strip).
        self._canvas = None
        self._filled = 0

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
            # sentinel from the parent process must actually leave the event loop
            self.receiver_thread.shutdown_requested.connect(self.close)
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
        strip = np.ascontiguousarray(numpy_image)
        if self._canvas is None or self._canvas.shape[1:] != strip.shape[1:] \
                or self._canvas.dtype != strip.dtype:
            self._canvas = np.zeros((MAX_VIEW_ROWS,) + strip.shape[1:], dtype=strip.dtype)
            self._filled = 0

        rows = strip.shape[0]
        if rows >= MAX_VIEW_ROWS:
            self._canvas[:] = strip[-MAX_VIEW_ROWS:]
            self._filled = MAX_VIEW_ROWS
        else:
            if self._filled + rows > MAX_VIEW_ROWS:
                # drop the oldest half in one move, so this costs O(window) once
                # every window/2 rows instead of O(history) every strip
                keep = max(0, MAX_VIEW_ROWS // 2 - rows)
                if keep:
                    self._canvas[:keep] = self._canvas[self._filled - keep:self._filled]
                self._filled = keep
            self._canvas[self._filled:self._filled + rows] = strip
            self._filled += rows

        stacked_image = self._canvas[:self._filled]

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
