"""Tests for the pairing flow: QR generation, server, setup screens, and state transitions."""

import io
import json
import threading
import time
from pathlib import Path
from unittest.mock import patch

import pytest
from PIL import Image

from baby_macropad.pairing.qr import generate_qr_image
from baby_macropad.pairing.server import (
    PairingServer,
    generate_pairing_code,
    get_local_ip,
    has_valid_pairing,
    load_pairing_config,
    save_pairing_config,
)
from baby_macropad.state import DisplayState
from baby_macropad.ui.framework.screen import ScreenRenderer
from baby_macropad.ui.screens.setup_screen import (
    NAME_PRESETS,
    build_setup_name_screen,
    build_setup_qr_screen,
)
from baby_macropad.ui.state_machine import StateMachine


def _validate_jpeg(data: bytes) -> Image.Image:
    """Assert data is valid 480x272 JPEG and return the image."""
    assert isinstance(data, bytes)
    img = Image.open(io.BytesIO(data))
    assert img.size == (480, 272)
    assert img.format == "JPEG"
    return img


renderer = ScreenRenderer()


class TestGenerateQrImage:
    def test_returns_pil_image(self):
        img = generate_qr_image("test")
        assert isinstance(img, Image.Image)
        assert img.mode == "RGB"

    def test_short_payload_fits_small(self):
        img = generate_qr_image("10.0.0.1:31337:A7X9:Nursery")
        # With box_size=2, border=1, a version 2-3 QR should be under 80px
        assert img.width <= 80
        assert img.height <= 80

    def test_white_on_black(self):
        img = generate_qr_image("test")
        # Check corners — border should be black (0,0,0)
        assert img.getpixel((0, 0)) == (0, 0, 0)


class TestGeneratePairingCode:
    def test_length_is_4(self):
        code = generate_pairing_code()
        assert len(code) == 4

    def test_is_uppercase_hex(self):
        code = generate_pairing_code()
        assert code == code.upper()
        int(code, 16)  # should not raise

    def test_unique(self):
        codes = {generate_pairing_code() for _ in range(20)}
        # With 4 hex chars (65536 possibilities), 20 should be unique
        assert len(codes) > 1


class TestGetLocalIp:
    def test_returns_string(self):
        ip = get_local_ip()
        assert isinstance(ip, str)
        assert "." in ip  # Should be dotted notation


class TestPairingConfig:
    def test_save_and_load(self, tmp_path):
        config_file = tmp_path / "pairing.yaml"
        config = {
            "dev": {"token": "bb_test123", "api_url": "https://dev.example.com/api/v1", "child_id": "uuid-1"},
            "name": "Nursery",
        }
        with patch("baby_macropad.pairing.server.PAIRING_FILE", config_file), \
             patch("baby_macropad.pairing.server.PAIRING_DIR", tmp_path):
            save_pairing_config(config)
            loaded = load_pairing_config()
            assert loaded == config

    def test_load_returns_none_when_no_file(self, tmp_path):
        config_file = tmp_path / "nonexistent.yaml"
        with patch("baby_macropad.pairing.server.PAIRING_FILE", config_file):
            assert load_pairing_config() is None

    def test_has_valid_pairing_true(self, tmp_path):
        config_file = tmp_path / "pairing.yaml"
        config = {
            "dev": {"token": "bb_test", "api_url": "https://dev.example.com", "child_id": "uuid-1"},
        }
        with patch("baby_macropad.pairing.server.PAIRING_FILE", config_file), \
             patch("baby_macropad.pairing.server.PAIRING_DIR", tmp_path):
            save_pairing_config(config)
            assert has_valid_pairing("dev") is True

    def test_has_valid_pairing_false_no_file(self, tmp_path):
        config_file = tmp_path / "nonexistent.yaml"
        with patch("baby_macropad.pairing.server.PAIRING_FILE", config_file):
            assert has_valid_pairing("dev") is False

    def test_has_valid_pairing_false_missing_token(self, tmp_path):
        config_file = tmp_path / "pairing.yaml"
        config = {
            "dev": {"token": "", "api_url": "https://dev.example.com", "child_id": "uuid-1"},
        }
        with patch("baby_macropad.pairing.server.PAIRING_FILE", config_file), \
             patch("baby_macropad.pairing.server.PAIRING_DIR", tmp_path):
            save_pairing_config(config)
            assert has_valid_pairing("dev") is False

    def test_has_valid_pairing_wrong_server(self, tmp_path):
        config_file = tmp_path / "pairing.yaml"
        config = {
            "dev": {"token": "bb_test", "api_url": "https://dev.example.com", "child_id": "uuid-1"},
        }
        with patch("baby_macropad.pairing.server.PAIRING_FILE", config_file), \
             patch("baby_macropad.pairing.server.PAIRING_DIR", tmp_path):
            save_pairing_config(config)
            assert has_valid_pairing("prod") is False


class TestPairingServer:
    def test_start_and_stop(self):
        server = PairingServer(code="ABCD", name="Test", port=0)
        server.start()
        assert server.port > 0
        assert not server.paired
        server.stop()

    def test_rejects_bad_code(self):
        import http.client

        server = PairingServer(code="ABCD", name="Test", port=0)
        server.start()
        try:
            conn = http.client.HTTPConnection("127.0.0.1", server.port)
            body = json.dumps({"token": "t", "api_url": "u", "child_id": "c"})
            conn.request("POST", "/pair", body, {
                "Content-Type": "application/json",
                "X-Pairing-Code": "WRONG",
            })
            resp = conn.getresponse()
            assert resp.status == 403
            assert not server.paired
            conn.close()
        finally:
            server.stop()

    def test_accepts_correct_code(self, tmp_path):
        import http.client

        config_file = tmp_path / "pairing.yaml"
        paired_event = threading.Event()

        def on_paired(config):
            paired_event.set()

        server = PairingServer(code="A1B2", name="Nursery", on_paired=on_paired, port=0)
        with patch("baby_macropad.pairing.server.PAIRING_FILE", config_file), \
             patch("baby_macropad.pairing.server.PAIRING_DIR", tmp_path):
            server.start()
            try:
                conn = http.client.HTTPConnection("127.0.0.1", server.port)
                body = json.dumps({
                    "token": "bb_test_token",
                    "api_url": "https://dev.example.com/api/v1",
                    "child_id": "child-uuid-123",
                    "server": "dev",
                })
                conn.request("POST", "/pair", body, {
                    "Content-Type": "application/json",
                    "X-Pairing-Code": "A1B2",
                })
                resp = conn.getresponse()
                assert resp.status == 200
                data = json.loads(resp.read())
                assert data["status"] == "paired"
                conn.close()

                # Verify callback was called
                assert paired_event.wait(timeout=2)

                # Verify config was saved
                config = load_pairing_config()
                assert config is not None
                assert config["dev"]["token"] == "bb_test_token"
                assert config["name"] == "Nursery"
            finally:
                # Server shuts itself down after pairing, but stop to be safe
                time.sleep(0.5)
                server.stop()

    def test_rejects_missing_fields(self):
        import http.client

        server = PairingServer(code="ABCD", name="Test", port=0)
        server.start()
        try:
            conn = http.client.HTTPConnection("127.0.0.1", server.port)
            body = json.dumps({"token": "t"})  # missing api_url and child_id
            conn.request("POST", "/pair", body, {
                "Content-Type": "application/json",
                "X-Pairing-Code": "ABCD",
            })
            resp = conn.getresponse()
            assert resp.status == 400
            conn.close()
        finally:
            server.stop()

    def test_404_on_wrong_path(self):
        import http.client

        server = PairingServer(code="ABCD", name="Test", port=0)
        server.start()
        try:
            conn = http.client.HTTPConnection("127.0.0.1", server.port)
            conn.request("POST", "/wrong", "")
            resp = conn.getresponse()
            assert resp.status == 404
            conn.close()
        finally:
            server.stop()


class TestSetupNameScreen:
    def test_renders_valid_jpeg(self):
        screen = build_setup_name_screen()
        data = renderer.render(screen)
        _validate_jpeg(data)

    def test_has_back_at_key_1(self):
        screen = build_setup_name_screen()
        assert 1 in screen.cells
        assert screen.cells[1].on_press == "back"

    def test_has_4_presets(self):
        screen = build_setup_name_screen()
        # 4 presets + 1 BACK = 5 cells
        assert len(screen.cells) == 5

    def test_select_on_press_format(self):
        screen = build_setup_name_screen()
        # First 4 option keys: 11, 12, 13, 14
        for i in range(4):
            key = [11, 12, 13, 14][i]
            assert screen.cells[key].on_press == f"select:{i}"


class TestSetupQrScreen:
    def test_renders_valid_jpeg(self):
        qr = generate_qr_image("10.0.0.1:31337:ABCD:Nursery")
        screen = build_setup_qr_screen(qr_image=qr, name="Nursery", code="ABCD")
        data = renderer.render(screen)
        _validate_jpeg(data)

    def test_has_back_at_key_1(self):
        qr = generate_qr_image("test")
        screen = build_setup_qr_screen(qr_image=qr, name="Test", code="1234")
        assert 1 in screen.cells
        assert screen.cells[1].on_press == "back"

    def test_has_header_row(self):
        qr = generate_qr_image("test")
        screen = build_setup_qr_screen(qr_image=qr, name="Test", code="1234")
        for key in (11, 12, 13, 14, 15):
            assert key in screen.cells

    def test_has_label_and_value_cells(self):
        qr = generate_qr_image("test")
        screen = build_setup_qr_screen(qr_image=qr, name="Nursery", code="A7X9")
        # Labels at keys 7, 8, 9
        assert 7 in screen.cells
        assert 8 in screen.cells
        assert 9 in screen.cells
        # Values at keys 2, 3, 4
        assert 2 in screen.cells
        assert 3 in screen.cells
        assert 4 in screen.cells

    def test_paired_status_color(self):
        qr = generate_qr_image("test")
        screen = build_setup_qr_screen(qr_image=qr, name="Test", code="1234", status="Paired!")
        # Status value at key 4 should have green color
        data = renderer.render(screen)
        _validate_jpeg(data)

    def test_has_pre_render(self):
        qr = generate_qr_image("test")
        screen = build_setup_qr_screen(qr_image=qr, name="Test", code="1234")
        assert screen.pre_render is not None


class TestStateMachineSetup:
    def test_enter_setup_name(self):
        sm = StateMachine(DisplayState())
        sm.enter_setup_name()
        assert sm.mode == "setup_name"
        assert sm.state.setup_paired is False

    def test_enter_setup_qr(self):
        sm = StateMachine(DisplayState())
        sm.enter_setup_qr("Nursery", "A7X9")
        assert sm.mode == "setup_qr"
        assert sm.state.setup_name == "Nursery"
        assert sm.state.setup_pairing_code == "A7X9"
        assert sm.state.setup_paired is False

    def test_mark_setup_paired(self):
        sm = StateMachine(DisplayState())
        sm.enter_setup_qr("Nursery", "A7X9")
        sm.mark_setup_paired()
        assert sm.state.setup_paired is True

    def test_return_home_from_setup(self):
        sm = StateMachine(DisplayState())
        sm.enter_setup_name()
        sm.return_home()
        assert sm.mode == "home_grid"
