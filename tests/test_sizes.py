import os
from dsh_lib import sizes


def test_physical_vs_logical_on_sparse(tmp_path):
    f = tmp_path / "sparse.bin"
    with open(f, "wb") as fh:
        fh.truncate(50 * 1024 * 1024)  # 50 MiB logical, ~0 physical
    st = os.lstat(f)
    assert sizes.logical_bytes(st) == 50 * 1024 * 1024
    assert sizes.physical_bytes(st) < sizes.logical_bytes(st)


def test_is_dataless():
    assert sizes.is_dataless(sizes.SF_DATALESS) is True
    assert sizes.is_dataless(0) is False
    assert sizes.is_dataless(sizes.SF_DATALESS | 0x1) is True


def test_classify():
    home = os.path.expanduser("~")
    assert sizes.classify(f"{home}/Library/Caches/foo") == "system-cache"
    assert sizes.classify(f"{home}/Downloads/big.dmg") == "downloads"
    assert sizes.classify(f"{home}/Dropbox/x") == "cloud-dropbox"
    assert sizes.classify(f"{home}/Library/Mobile Documents/x") == "cloud-icloud"
    assert sizes.classify(f"{home}/proj/node_modules/x") == "dev-cache"
    assert sizes.classify(f"{home}/Movies/clip.mov") == "media"
    assert sizes.classify(f"{home}/Library/Application Support/x") == "app-support"
    assert sizes.classify(f"{home}/random/thing.txt") == "other"
