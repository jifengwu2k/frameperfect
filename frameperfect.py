import os
import sys

import attr
import cv2
from numpy import ndarray
from pyqtcompat import (
    Format_RGB888,
    QApplication,
    QFileDialog,
    QHBoxLayout,
    QImage,
    QLabel,
    QMainWindow,
    QMessageBox,
    QPixmap,
    QPushButton,
    QSlider,
    QTimer,
    QVBoxLayout,
    QWidget,
    QT_ALIGN_CENTER,
    QT_HORIZONTAL,
    QT_KEEP_ASPECT_RATIO,
    QT_SMOOTH_TRANSFORMATION,
    SLIDER_MOVE,
    SLIDER_PAGE_STEP_ADD,
    SLIDER_PAGE_STEP_SUB,
    SLIDER_SINGLE_STEP_ADD,
    SLIDER_SINGLE_STEP_SUB,
    execute,
)

PLAYBACK_SPEEDS = (0.5, 1.0, 2.0, 4.0)
DEFAULT_PLAYBACK_SPEED_INDEX = 1


@attr.s
class VideoPlayerState(object):
    pass


@attr.s
class VideoNotOpened(VideoPlayerState):
    pass


@attr.s
class VideoPlaybackInformation(object):
    video_path = attr.ib()  # type: str
    video_capture = attr.ib()  # type: cv2.VideoCapture
    total_frames = attr.ib()  # type: int
    curr_frame_idx = attr.ib()  # type: int
    curr_hwc_bgr_frame = attr.ib()  # type: ndarray
    fps = attr.ib()  # type: float


@attr.s
class VideoOpenedAndPaused(VideoPlayerState):
    video_playback_information = attr.ib()  # type: VideoPlaybackInformation


@attr.s
class VideoOpenedAndPlaying(VideoPlayerState):
    video_playback_information = attr.ib()  # type: VideoPlaybackInformation


class VideoPlayer(QMainWindow):
    def __init__(self):
        super(VideoPlayer, self).__init__()
        self.setWindowTitle('FramePerfect Video Analyzer')
        self.setGeometry(128, 128, 1280, 720)

        # Playback speed
        self.playback_speed = PLAYBACK_SPEEDS[DEFAULT_PLAYBACK_SPEED_INDEX]

        # Central widget and main layout
        central_widget = QWidget()
        self.setCentralWidget(central_widget)
        main_layout = QVBoxLayout(central_widget)

        # Video display label
        self.video_label = QLabel()
        self.video_label.setAlignment(QT_ALIGN_CENTER)
        self.video_label.setStyleSheet('background-color: black; color: white')
        main_layout.addWidget(self.video_label, 1)

        # Controls layout
        controls_layout = QHBoxLayout()

        # Open button
        self.open_button = QPushButton('Open Video')
        self.open_button.clicked.connect(self.open_video_callback)
        controls_layout.addWidget(self.open_button)

        # Play/Pause button
        self.play_button = QPushButton('Play')
        self.play_button.clicked.connect(self.toggle_play_pause_callback)
        controls_layout.addWidget(self.play_button)

        # Previous frame button
        self.prev_button = QPushButton('Previous Frame')
        self.prev_button.clicked.connect(self.prev_callback)
        controls_layout.addWidget(self.prev_button)

        # Next frame button
        self.next_button = QPushButton('Next Frame')
        self.next_button.clicked.connect(self.next_callback)
        controls_layout.addWidget(self.next_button)

        # Save frame button
        self.save_button = QPushButton('Save Frame')
        self.save_button.clicked.connect(self.save_callback)
        controls_layout.addWidget(self.save_button)

        # Playback speed controls
        controls_layout.addWidget(QLabel('Playback Speed:'))
        self.speed_slider = QSlider(QT_HORIZONTAL)
        self.speed_slider.setRange(0, len(PLAYBACK_SPEEDS) - 1)
        self.speed_slider.setSingleStep(1)
        self.speed_slider.setPageStep(1)
        self.speed_slider.setValue(DEFAULT_PLAYBACK_SPEED_INDEX)
        self.speed_slider.setFixedWidth(120)
        self.speed_slider.setToolTip('Playback speed: 0.5x, 1x, 2x, 4x')
        self.speed_slider.valueChanged.connect(self.playback_speed_changed_callback)
        controls_layout.addWidget(self.speed_slider)

        self.speed_label = QLabel('%gx' % self.playback_speed)
        self.speed_label.setFixedWidth(40)
        controls_layout.addWidget(self.speed_label)

        main_layout.addLayout(controls_layout)

        # Progress slider
        self.slider = QSlider(QT_HORIZONTAL)
        # Enable slider tracking
        self.slider.setEnabled(True)
        self.slider.actionTriggered.connect(self.slider_action_triggered_callback)
        main_layout.addWidget(self.slider)

        # Status label
        self.status_label = QLabel('Ready')
        main_layout.addWidget(self.status_label)

        # Timer for video playback
        self.timer = QTimer(self)
        self.timer.timeout.connect(self.timer_callback)

        # State
        self.state = VideoPlayerState()  # type: VideoPlayerState
        self.handle_state_transition(VideoNotOpened())

    def handle_state_transition(self, new_state):
        # Cache the old state
        old_state = self.state
        # Save the new state
        self.state = new_state

        # Any state -> VideoNotOpened
        if isinstance(new_state, VideoNotOpened):
            # Clear video display label
            self.video_label.clear()

            # Disable buttons and slider
            for component in (
                    self.play_button,
                    self.prev_button,
                    self.next_button,
                    self.save_button,
                    self.slider,
                    self.speed_slider
            ):
                component.setEnabled(False)

            # Display 'Play' on the play/pause button
            self.play_button.setText('Play')

            # Move the slider back
            self.slider.setValue(0)

            # Display 'Ready' on the status label
            self.status_label.setText('Ready')

            # Stop timer
            self.timer.stop()
        elif isinstance(new_state, VideoOpenedAndPaused):
            # VideoNotOpened -> VideoOpenedAndPaused
            if isinstance(old_state, VideoNotOpened):
                # Enable buttons and slider
                for component in (
                        self.play_button,
                        self.prev_button,
                        self.next_button,
                        self.save_button,
                        self.slider,
                        self.speed_slider
                ):
                    component.setEnabled(True)

                # Update slider
                self.slider.setRange(0, new_state.video_playback_information.total_frames - 1)

                # Display current frame
                self.display_current_frame()
            # VideoOpenedAndPlaying -> VideoOpenedAndPaused
            elif isinstance(old_state, VideoOpenedAndPlaying):
                # Display 'Play' on the play/pause button
                self.play_button.setText('Play')

                # Stop timer
                self.timer.stop()
        elif isinstance(new_state, VideoOpenedAndPlaying):
            # VideoOpenedAndPaused -> VideoOpenedAndPlaying
            if isinstance(old_state, VideoOpenedAndPaused):
                # Display 'Pause' on the play/pause button
                self.play_button.setText('Pause')

                # Start timer
                self.update_timer_interval()
                self.timer.start()

    def load_video(self, video_path):
        # Transition to `VideoNotOpened` state
        self.handle_state_transition(VideoNotOpened())

        video_capture = cv2.VideoCapture(video_path)

        if not video_capture.isOpened():
            QMessageBox.critical(self, 'Error', 'Could not open video file %s' % video_path)
            return False

        total_frames = int(video_capture.get(cv2.CAP_PROP_FRAME_COUNT))
        curr_frame_idx = 0
        fps = video_capture.get(cv2.CAP_PROP_FPS)

        ret, curr_hwc_bgr_frame_or_none = video_capture.read()
        if not ret or curr_hwc_bgr_frame_or_none is None:
            QMessageBox.critical(self, 'Error', 'Could not open video file %s' % video_path)
            return False

        video_playback_information = VideoPlaybackInformation(
            video_path=video_path,
            video_capture=video_capture,
            total_frames=total_frames,
            curr_frame_idx=curr_frame_idx,
            curr_hwc_bgr_frame=curr_hwc_bgr_frame_or_none,
            fps=fps
        )

        # Transition to `VideoOpenedAndPaused` state
        self.handle_state_transition(VideoOpenedAndPaused(video_playback_information))

        return True

    def prev_frame(self):
        if isinstance(self.state, VideoOpenedAndPaused):
            video_playback_information = self.state.video_playback_information

            video_capture = video_playback_information.video_capture
            new_frame_idx = video_playback_information.curr_frame_idx - 1

            if new_frame_idx >= 0:
                video_capture.set(cv2.CAP_PROP_POS_FRAMES, new_frame_idx)
                ret, new_hwc_bgr_frame_or_none = video_capture.read()
                if ret and new_hwc_bgr_frame_or_none is not None:
                    new_hwc_bgr_frame = new_hwc_bgr_frame_or_none

                    # Update video playback information
                    video_playback_information.curr_frame_idx = new_frame_idx
                    video_playback_information.curr_hwc_bgr_frame = new_hwc_bgr_frame
                    return True
        return False

    def next_frame(self):
        if isinstance(self.state, (VideoOpenedAndPaused, VideoOpenedAndPlaying)):
            video_playback_information = self.state.video_playback_information

            video_capture = video_playback_information.video_capture
            curr_frame_idx = video_playback_information.curr_frame_idx
            total_frames = video_playback_information.total_frames

            if curr_frame_idx >= total_frames - 1:
                return False  # Already at last frame

            ret, new_hwc_bgr_frame_or_none = video_capture.read()
            if ret and new_hwc_bgr_frame_or_none is not None:
                # Update video playback information
                video_playback_information.curr_frame_idx += 1
                video_playback_information.curr_hwc_bgr_frame = new_hwc_bgr_frame_or_none
                return True
        return False

    def seek_frame(self, new_frame_idx):
        if isinstance(self.state, VideoOpenedAndPaused):
            video_playback_information = self.state.video_playback_information

            video_capture = video_playback_information.video_capture
            total_frames = video_playback_information.total_frames

            if 0 <= new_frame_idx < total_frames:
                video_capture.set(cv2.CAP_PROP_POS_FRAMES, new_frame_idx)
                ret, new_hwc_bgr_frame_or_none = video_capture.read()
                if ret and new_hwc_bgr_frame_or_none is not None:
                    new_hwc_bgr_frame = new_hwc_bgr_frame_or_none

                    # Update video playback information
                    video_playback_information.curr_frame_idx = new_frame_idx
                    video_playback_information.curr_hwc_bgr_frame = new_hwc_bgr_frame
                    return True
        return False

    def display_current_frame(self):
        if isinstance(self.state, (VideoOpenedAndPaused, VideoOpenedAndPlaying)):
            video_playback_information = self.state.video_playback_information

            total_frames = video_playback_information.total_frames
            curr_frame_idx = video_playback_information.curr_frame_idx
            curr_hwc_bgr_frame = video_playback_information.curr_hwc_bgr_frame
            fps = video_playback_information.fps

            # Convert BGR to RGB
            curr_hwc_rgb_frame = cv2.cvtColor(curr_hwc_bgr_frame, cv2.COLOR_BGR2RGB)

            # Convert to QImage
            height, width, channel = curr_hwc_rgb_frame.shape
            bytes_per_line = 3 * width
            q_img = QImage(curr_hwc_rgb_frame.data, width, height, bytes_per_line, Format_RGB888)

            # Scale to fit label while maintaining aspect ratio
            pixmap = QPixmap.fromImage(q_img)
            pixmap = pixmap.scaled(
                self.video_label.width(),
                self.video_label.height(),
                QT_KEEP_ASPECT_RATIO,
                QT_SMOOTH_TRANSFORMATION
            )

            self.slider.setValue(curr_frame_idx)
            self.video_label.setPixmap(pixmap)
            self.status_label.setText('Frame: %d/%d; Time: %.3fs/%.3fs' % (curr_frame_idx, total_frames - 1, curr_frame_idx / fps, total_frames / fps))

    def update_timer_interval(self):
        if isinstance(self.state, VideoOpenedAndPlaying):
            fps = self.state.video_playback_information.fps
            interval = int(1000 / (fps * self.playback_speed))
            self.timer.setInterval(max(1, interval))

    def playback_speed_changed_callback(self, value):
        self.playback_speed = PLAYBACK_SPEEDS[value]
        self.speed_label.setText('%gx' % self.playback_speed)
        self.update_timer_interval()

    def open_video_callback(self):
        file_dialog = QFileDialog()
        file_dialog.setNameFilter('Video Files (*.mp4 *.avi *.mov *.mkv *.flv)')
        video_path, _ = file_dialog.getOpenFileName(self, 'Open Video File')

        if video_path:
            self.load_video(video_path)

    def play_callback(self):
        if isinstance(self.state, VideoOpenedAndPaused):
            self.handle_state_transition(VideoOpenedAndPlaying(self.state.video_playback_information))

    def pause_callback(self):
        if isinstance(self.state, VideoOpenedAndPlaying):
            self.handle_state_transition(VideoOpenedAndPaused(self.state.video_playback_information))

    def toggle_play_pause_callback(self):
        if isinstance(self.state, VideoOpenedAndPaused):
            self.play_callback()
        elif isinstance(self.state, VideoOpenedAndPlaying):
            self.pause_callback()

    def stop_callback(self):
        if isinstance(self.state, (VideoOpenedAndPaused, VideoOpenedAndPlaying)):
            self.state.video_playback_information.video_capture.release()

        self.handle_state_transition(VideoNotOpened())

    def timer_callback(self):
        if isinstance(self.state, VideoOpenedAndPlaying):
            is_successful = self.next_frame()
            if not is_successful:
                self.pause_callback()
            self.display_current_frame()

    def prev_callback(self):
        self.pause_callback()
        if isinstance(self.state, VideoOpenedAndPaused):
            self.prev_frame()
            self.display_current_frame()

    def next_callback(self):
        self.pause_callback()
        if isinstance(self.state, VideoOpenedAndPaused):
            self.next_frame()
            self.display_current_frame()

    def seek_callback(self, new_frame_idx):
        self.pause_callback()
        if isinstance(self.state, VideoOpenedAndPaused):
            self.seek_frame(new_frame_idx)
            self.display_current_frame()

    def save_callback(self):
        self.pause_callback()
        if isinstance(self.state, VideoOpenedAndPaused):
            video_playback_information = self.state.video_playback_information
            video_path = video_playback_information.video_path
            curr_frame_idx = video_playback_information.curr_frame_idx
            curr_hwc_bgr_frame = video_playback_information.curr_hwc_bgr_frame

            # Set default filename
            video_name = os.path.splitext(os.path.basename(video_path))[0]
            default_filename = '%s_frame_%d.png' % (video_name, curr_frame_idx)

            # Open save dialog
            file_path, _ = QFileDialog.getSaveFileName(
                self,
                'Save Current Frame',
                default_filename,
                'PNG Image (*.png);;JPEG Image (*.jpg *.jpeg)'
            )

            if file_path:
                imwrite_ret = cv2.imwrite(file_path, curr_hwc_bgr_frame)
                if imwrite_ret:
                    self.status_label.setText('Frame saved to %s' % file_path)
                else:
                    QMessageBox.critical(self, 'Error', 'Could not save frame to %s' % file_path)

    def slider_action_triggered_callback(self, action):
        self.pause_callback()
        if isinstance(self.state, VideoOpenedAndPaused):
            if action == SLIDER_SINGLE_STEP_ADD:
                self.next_callback()
            elif action == SLIDER_SINGLE_STEP_SUB:
                self.prev_callback()
            elif action in (
                    SLIDER_PAGE_STEP_ADD,
                    SLIDER_PAGE_STEP_SUB,
                    SLIDER_MOVE
            ):
                self.seek_callback(self.slider.sliderPosition())

    def closeEvent(self, event):
        self.stop_callback()
        event.accept()


def main():
    current_script_path, *video_paths = sys.argv
    app = QApplication([])
    player = VideoPlayer()

    # Interactive Mode
    if not video_paths:
        player.show()
        return execute(app)
    # Sequential Batch Mode
    else:
        success_count = 0
        for video_path in video_paths:
            if player.load_video(video_path):
                player.show()
                QApplication.processEvents()
                execute(app)
                success_count += 1
                player.hide()
            else:
                sys.stderr.write('Could not open video file %s\n' % video_path)
        sys.stdout.write('Processed %d/%d videos\n' % (success_count, len(video_paths)))
        player.close()
        app.quit()

        if success_count == len(video_paths):
            return 0
        else:
            return 1


if __name__ == '__main__':
    sys.exit(main())