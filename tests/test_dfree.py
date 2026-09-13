from unittest import mock
from dsh_lib import dfree

SAMPLE = (
    "Filesystem 1024-blocks      Used Available Capacity iused ifree %iused  Mounted on\n"
    "/dev/disk3s5 970662016 895000000  27000000      98%  9500000 260000000 3% /System/Volumes/Data\n"
)


def test_free_bytes_parses_available():
    with mock.patch("subprocess.run") as run:
        run.return_value = mock.Mock(stdout=SAMPLE, returncode=0)
        assert dfree.free_bytes("/System/Volumes/Data") == 27000000 * 1024
