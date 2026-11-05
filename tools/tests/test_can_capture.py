import io
import json
import threading
import time

import can

import can_capture as cc
import canlog

IP_JSON_LISTEN_ONLY = json.dumps(
    [
        {
            "ifindex": 5,
            "ifname": "can0",
            "flags": ["NOARP", "UP", "LOWER_UP", "ECHO"],
            "link_type": "can",
            "linkinfo": {
                "info_kind": "can",
                "info_data": {
                    "ctrlmode": ["LISTEN-ONLY", "BERR-REPORTING"],
                    "state": "ERROR-ACTIVE",
                    "bittiming": {"bitrate": 250000, "sample_point": "0.875"},
                },
            },
        }
    ]
)

IP_JSON_NORMAL_DOWN = json.dumps(
    [
        {
            "ifname": "can0",
            "flags": ["NOARP", "ECHO"],
            "link_type": "can",
            "linkinfo": {"info_kind": "can", "info_data": {"state": "STOPPED"}},
        }
    ]
)

IP_TEXT_LISTEN_ONLY = """5: can0: <NOARP,UP,LOWER_UP,ECHO> mtu 16 qdisc pfifo_fast state UP mode DEFAULT group default qlen 10
    link/can  promiscuity 0 minmtu 0 maxmtu 0
    can <LISTEN-ONLY,BERR-REPORTING> state ERROR-ACTIVE (berr-counter tx 0 rx 0) restart-ms 0
	  bitrate 500000 sample-point 0.875
"""

IP_TEXT_VCAN = """7: vcan0: <NOARP,UP,LOWER_UP> mtu 72 qdisc noqueue state UNKNOWN mode DEFAULT group default qlen 1000
    link/can  promiscuity 0 minmtu 0 maxmtu 0
    vcan numtxqueues 1 numrxqueues 1
"""


def test_parse_ip_json_listen_only():
    info = cc.parse_ip_json(IP_JSON_LISTEN_ONLY)
    assert info.exists and info.up and info.listen_only
    assert info.bitrate == 250000
    assert info.state == "ERROR-ACTIVE"
    assert cc.capture_blockers(info, "can0") == []


def test_parse_ip_json_dict_ctrlmode():
    data = json.loads(IP_JSON_LISTEN_ONLY)
    data[0]["linkinfo"]["info_data"]["ctrlmode"] = {"LISTEN-ONLY": True, "LOOPBACK": False}
    assert cc.parse_ip_json(json.dumps(data)).listen_only


def test_not_listen_only_blocks_capture():
    info = cc.parse_ip_json(IP_JSON_NORMAL_DOWN)
    assert info.exists and not info.up and not info.listen_only
    problems = cc.capture_blockers(info, "can0")
    assert any("listen-only" in p for p in problems)
    assert any("down" in p for p in problems)


def test_missing_interface_blocks_capture():
    assert cc.capture_blockers(cc.parse_ip_json("[]"), "can0")


def test_parse_ip_text():
    info = cc.parse_ip_text(IP_TEXT_LISTEN_ONLY)
    assert info.up and info.listen_only and info.bitrate == 500000 and info.kind == "can"
    vinfo = cc.parse_ip_text(IP_TEXT_VCAN)
    assert vinfo.is_virtual and vinfo.up
    assert cc.capture_blockers(vinfo, "vcan0") == []


def test_pick_bitrate():
    R = cc.ScanResult
    assert cc.pick_bitrate([R(250000, 0, 500, 0, "ERROR-PASSIVE"), R(500000, 0, 0, 0, "ERROR-ACTIVE")]) is None
    best = cc.pick_bitrate(
        [
            R(250000, 3, 900, 2, "ERROR-PASSIVE"),
            R(500000, 1200, 0, 14, "ERROR-ACTIVE"),
            R(125000, 0, 50, 0, "ERROR-ACTIVE"),
        ]
    )
    assert best.bitrate == 500000


def test_recorder_steps_and_markers(tmp_path):
    rec = cc.Recorder(tmp_path / "s", "can0", steps=["D", "N"], t0=100.0)
    assert rec.mark(None, 101.0).label == "D"
    assert rec.mark("brake on", 102.0).label == "brake on"
    assert rec.next_step() == "N"
    assert rec.mark("N", 103.0).label == "N"  # typing the planned step consumes it
    assert rec.mark(None, 104.0).label == "mark 4"
    rec.close()
    labels = [m.label for m in canlog.read_markers(tmp_path / "s" / "markers.csv")]
    assert labels == ["D", "brake on", "N", "mark 4"]


def test_record_from_virtual_bus(tmp_path):
    rx = can.Bus(interface="virtual", channel="cartdash-test", receive_own_messages=False)
    tx = can.Bus(interface="virtual", channel="cartdash-test")
    rec = cc.Recorder(tmp_path / "s", "can0", steps=["D"])
    stop = threading.Event()
    th = threading.Thread(target=cc.record, args=(rx, rec, stop), kwargs={"status_every": 0, "out": lambda s: None})
    th.start()
    for i in range(50):
        tx.send(can.Message(arbitration_id=0x18FF50E5, is_extended_id=True, data=[i, 0, 0, 0]))
        if i == 25:
            rec.mark()
    deadline = time.time() + 5
    while rec.frames < 50 and time.time() < deadline:
        time.sleep(0.02)
    stop.set()
    th.join(timeout=5)
    rx.shutdown()
    tx.shutdown()
    path = rec.close()
    assert path.name == "can.log.gz"
    s = canlog.load_session(tmp_path / "s")
    assert len(s.data_frames) == 50
    assert [f.data[0] for f in s.data_frames] == list(range(50))
    assert [m.label for m in s.markers] == ["D"]


def test_capture_command_end_to_end(tmp_path, monkeypatch):
    monkeypatch.setattr("sys.stdin", io.StringIO(""))
    rc = cc.main(
        [
            "--channel",
            "cartdash-cli",
            "capture",
            "--interface",
            "virtual",
            "--label",
            "Key On Idle",
            "--duration",
            "0.5",
            "--status-every",
            "0",
            "--out",
            str(tmp_path),
        ]
    )
    assert rc == 0
    folders = list((tmp_path / "factory").iterdir())
    assert len(folders) == 1 and folders[0].name.endswith("_key-on-idle")
    meta = json.loads((folders[0] / "meta.json").read_text())
    assert meta["label"] == "Key On Idle"
    assert meta["frames"] == 0 and meta["log_file"] == "can.log.gz"
    assert (folders[0] / "can.log.gz").exists()


def test_session_dir_names_do_not_collide(tmp_path):
    import datetime as dt

    when = dt.datetime(2026, 11, 6, 10, 15, 0)
    a = cc.make_session_dir(tmp_path, "factory", "gear dnr", when)
    b = cc.make_session_dir(tmp_path, "factory", "gear dnr", when)
    assert a != b and a.name == "20261106-101500_gear-dnr"


class _BrokenBus:
    def __init__(self):
        self.calls = 0

    def recv(self, timeout=None):
        self.calls += 1
        if self.calls > 3:
            raise can.CanOperationError("Network is down")
        return can.Message(timestamp=time.time(), arbitration_id=0x123, data=[self.calls])


def test_record_survives_adapter_unplug(tmp_path):
    rec = cc.Recorder(tmp_path / "s", "can0")
    said = []
    cc.record(_BrokenBus(), rec, threading.Event(), status_every=0, out=said.append)
    rec.close()
    assert rec.frames == 3
    assert said and "Bus error" in said[0]
    assert len(canlog.load_session(tmp_path / "s").data_frames) == 3
