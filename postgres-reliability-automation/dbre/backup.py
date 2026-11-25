"""Backup verification: manifest + checksum validation of synthetic backup files."""
import hashlib, json, pathlib

def file_checksum(path):
    h=hashlib.sha256()
    h.update(pathlib.Path(path).read_bytes())
    return h.hexdigest()

def write_backup(directory, name, content: bytes):
    d=pathlib.Path(directory); d.mkdir(parents=True, exist_ok=True)
    p=d/name; p.write_bytes(content)
    manifest={"file":name,"sha256":hashlib.sha256(content).hexdigest(),"bytes":len(content)}
    (d/(name+".manifest.json")).write_text(json.dumps(manifest,indent=2))
    return manifest

def verify_backup(directory, name):
    d=pathlib.Path(directory); p=d/name; mpath=d/(name+".manifest.json")
    if not p.exists(): return {"file":name,"ok":False,"reason":"missing backup file"}
    if not mpath.exists(): return {"file":name,"ok":False,"reason":"missing manifest"}
    manifest=json.loads(mpath.read_text())
    actual=file_checksum(p)
    if actual!=manifest["sha256"]: return {"file":name,"ok":False,"reason":"checksum mismatch"}
    if p.stat().st_size!=manifest["bytes"]: return {"file":name,"ok":False,"reason":"size mismatch"}
    return {"file":name,"ok":True,"reason":"checksum and size match manifest"}
