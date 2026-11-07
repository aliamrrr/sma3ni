import io

import pytest
from botocore.exceptions import ClientError, EndpointConnectionError

from sma3ni.storage import AudioNotFound, LocalAudioStore, S3AudioStore, StorageError, validate_key

KEY = "2026/11/07/0b3c6a4e-1d2f-4a5b-9c8d-7e6f5a4b3c2d.ogg"


def test_validate_key_rejects_traversal_and_absolute_paths():
    assert validate_key(KEY) == KEY
    for bad in ("../etc/passwd", "/etc/passwd", "a/../../b", "a b", "", "x" * 201):
        with pytest.raises(ValueError):
            validate_key(bad)


def test_local_store_roundtrip(tmp_path):
    store = LocalAudioStore(str(tmp_path))
    store.put(KEY, b"OggS-data", "audio/ogg")
    assert store.get(KEY) == b"OggS-data"
    assert not list(tmp_path.rglob(".upload-*"))  # no temp file left behind
    store.delete(KEY)
    store.delete(KEY)  # idempotent
    with pytest.raises(AudioNotFound):
        store.get(KEY)


class FakeS3:
    """Records calls; mimics botocore errors."""

    def __init__(self):
        self.objects: dict[str, bytes] = {}
        self.calls: list[tuple[str, dict]] = []
        self.down = False

    def _check(self):
        if self.down:
            raise EndpointConnectionError(endpoint_url="https://s3.eu-west-3.amazonaws.com")

    def put_object(self, **kw):
        self._check()
        self.calls.append(("put", kw))
        self.objects[kw["Key"]] = kw["Body"]

    def get_object(self, **kw):
        self._check()
        if kw["Key"] not in self.objects:
            raise ClientError({"Error": {"Code": "NoSuchKey", "Message": "missing"}}, "GetObject")
        return {"Body": io.BytesIO(self.objects[kw["Key"]])}

    def delete_object(self, **kw):
        self._check()
        self.calls.append(("delete", kw))
        self.objects.pop(kw["Key"], None)


def test_s3_store_prefix_and_encryption():
    fake = FakeS3()
    store = S3AudioStore("bucket", "audio/", kms_key_id="arn:aws:kms:eu-west-3:111122223333:key/abc", client=fake)
    store.put(KEY, b"data", "audio/ogg")
    _, kw = fake.calls[0]
    assert kw["Bucket"] == "bucket"
    assert kw["Key"] == f"audio/{KEY}"
    assert kw["ServerSideEncryption"] == "aws:kms"
    assert kw["SSEKMSKeyId"].endswith("key/abc")
    assert kw["ContentType"] == "audio/ogg"
    assert store.get(KEY) == b"data"


def test_s3_store_without_sse_header():
    fake = FakeS3()
    S3AudioStore("bucket", sse="", client=fake).put(KEY, b"data")
    assert "ServerSideEncryption" not in fake.calls[0][1]


def test_s3_store_maps_errors():
    fake = FakeS3()
    store = S3AudioStore("bucket", client=fake)
    with pytest.raises(AudioNotFound):
        store.get(KEY)
    fake.down = True
    with pytest.raises(StorageError):
        store.put(KEY, b"data")
    with pytest.raises(StorageError):
        store.delete(KEY)


def test_s3_store_rejects_bad_keys_before_calling_s3():
    fake = FakeS3()
    with pytest.raises(ValueError):
        S3AudioStore("bucket", client=fake).put("../escape", b"x")
    assert fake.calls == []


def test_s3_store_requires_bucket():
    with pytest.raises(RuntimeError):
        S3AudioStore("", client=FakeS3())
