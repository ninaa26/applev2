from pathlib import Path

import numpy as np
import pytest

cv2 = pytest.importorskip("cv2")

from sentinel_device.tools import camera_bench

BOARD = Path(__file__).resolve().parents[2] / "hardware" / "print" / "checkerboard.png"  # 300 dpi


def fake_photo(tmp_path: Path, scale: float, blur: float, noise: float) -> Path:
    board = cv2.resize(cv2.imread(str(BOARD), 0), None, fx=scale, fy=scale, interpolation=cv2.INTER_AREA)
    canvas = np.full((int(board.shape[0] * 1.6), int(board.shape[1] * 1.4)), 230, np.float32)
    y0, x0 = (canvas.shape[0] - board.shape[0]) // 2, (canvas.shape[1] - board.shape[1]) // 2
    canvas[y0:y0 + board.shape[0], x0:x0 + board.shape[1]] = board * 0.8 + 30
    canvas = cv2.GaussianBlur(canvas, (0, 0), blur) + np.random.default_rng(0).normal(0, noise, canvas.shape)
    path = tmp_path / f"s{scale}_b{blur}_n{noise}.jpg"
    cv2.imwrite(str(path), np.clip(canvas, 0, 255).astype(np.uint8))
    return path


def test_scale_blur_and_noise_are_measured(tmp_path):
    sharp = camera_bench.score(fake_photo(tmp_path, 0.6, 0.5, 2), (180, 180))
    blurry = camera_bench.score(fake_photo(tmp_path, 0.6, 3.0, 2), (180, 180))
    noisy = camera_bench.score(fake_photo(tmp_path, 0.6, 0.5, 15), (180, 180))
    assert sharp["px_per_mm"] == pytest.approx(300 / 25.4 * 0.6, rel=0.02)
    assert sharp["ofm_px"] == round(6 * sharp["px_per_mm"])
    assert blurry["edge_blur_mm"] > 3 * sharp["edge_blur_mm"]
    assert noisy["edge_blur_mm"] < 1.5 * sharp["edge_blur_mm"]  # noise must not read as blur
    assert noisy["contrast_noise"] < sharp["contrast_noise"] / 3
    assert sharp["liner_fits"] and sharp["fov_mm"][0] > 250


def test_missing_board_is_reported(tmp_path):
    blank = tmp_path / "blank.jpg"
    cv2.imwrite(str(blank), np.full((480, 640), 200, np.uint8))
    assert "error" in camera_bench.score(blank, (180, 180))
