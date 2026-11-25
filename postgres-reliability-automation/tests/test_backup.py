import sys, pathlib
sys.path.insert(0, str(pathlib.Path(__file__).parent.parent))
from dbre.backup import write_backup, verify_backup
def test_roundtrip_ok(tmp_path):
    write_backup(tmp_path,"a.dump",b"hello-backup"); assert verify_backup(tmp_path,"a.dump")["ok"] is True
def test_tamper_detected(tmp_path):
    write_backup(tmp_path,"a.dump",b"hello-backup"); (tmp_path/"a.dump").write_bytes(b"tampered")
    assert verify_backup(tmp_path,"a.dump")["ok"] is False
def test_missing_file(tmp_path):
    assert verify_backup(tmp_path,"nope.dump")["ok"] is False
