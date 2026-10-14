"""POSIX append-only journal with locks, hash chain and exported checkpoints.

There is intentionally no update/delete method. Hashes detect modifications,
not a malicious owner able to rewrite the entire chain and every checkpoint.
"""

import copy
import fcntl
import os
import stat
import uuid
from contextlib import contextmanager
from pathlib import Path

from .common import (
    FLAGS,
    ValidationError,
    canonical,
    digest,
    instant,
    loads,
    schema_errors,
    timestamp,
    utc_now,
)
from .evaluator import evaluate
from .validation import validate_dossier

ZERO_HASH = "0" * 64
MAX_JOURNAL_BYTES = 64 * 1024 * 1024


class Registry:
    def __init__(self, directory, *, mode="real_only", _clock=utc_now):
        if mode not in ("real_only", "synthetic_test"):
            raise ValueError("invalid_mode")
        self.directory = Path(directory)
        self.directory.mkdir(parents=True, exist_ok=True, mode=0o700)
        self.path = self.directory / "journal.jsonl"
        self.mode = mode
        self.clock = _clock

    @contextmanager
    def _locked(self):
        # O_NOFOLLOW prevents replacing the journal with a symlink. Directory
        # ownership and trusted local clock are deployment prerequisites.
        fd = os.open(
            self.path, os.O_RDWR | os.O_CREAT | os.O_APPEND | os.O_NOFOLLOW, 0o600
        )
        try:
            if not stat.S_ISREG(os.fstat(fd).st_mode):
                raise ValidationError("journal_not_regular_file")
            fcntl.flock(fd, fcntl.LOCK_EX)
            with os.fdopen(fd, "r+b", closefd=False) as stream:
                yield stream
        finally:
            os.close(fd)

    def _read(self, stream):
        stream.seek(0)
        raw = stream.read(MAX_JOURNAL_BYTES + 1)
        if len(raw) > MAX_JOURNAL_BYTES:
            raise ValidationError("journal_capacity_exceeded")
        if raw and not raw.endswith(b"\n"):
            raise ValidationError("journal_partial_write")
        records, seen, previous = [], set(), ZERO_HASH
        for sequence, line in enumerate(raw.splitlines(), 1):
            record = loads(line)
            errors = schema_errors(record, "record")
            if errors:
                raise ValidationError("journal_record_invalid")
            body = {
                key: value for key, value in record.items() if key != "content_hash"
            }
            if (
                record["sequence"] != sequence
                or record["previous_hash"] != previous
                or record["content_hash"] != digest(body)
                or record["record_id"] in seen
            ):
                raise ValidationError("journal_integrity_failed")
            seen.add(record["record_id"])
            if record["record_type"] != "prediction":
                target = next(
                    (
                        r
                        for r in records
                        if r["record_id"] == record["data"]["prediction_id"]
                    ),
                    None,
                )
                if (
                    target is None
                    or target["record_type"] != "prediction"
                    or target["content_hash"] != record["data"]["prediction_hash"]
                ):
                    raise ValidationError("journal_link_invalid")
            records.append(record)
            previous = record["content_hash"]
        return records

    @staticmethod
    def _checkpoint(records):
        return {
            "count": len(records),
            "head_hash": records[-1]["content_hash"] if records else ZERO_HASH,
        }

    def verify(self, checkpoint=None):
        with self._locked() as stream:
            records = self._read(stream)
        if checkpoint is not None:
            count = checkpoint["count"]
            if (
                count < 0
                or len(records) < count
                or self._checkpoint(records[:count]) != checkpoint
            ):
                raise ValidationError("checkpoint_mismatch")
        return self._checkpoint(records)

    def get(self, record_id):
        with self._locked() as stream:
            records = self._read(stream)
        for record in records:
            if record["record_id"] == record_id:
                return copy.deepcopy(record)
        raise ValidationError("record_not_found")

    def _append(self, stream, records, kind, data, recorded_at):
        if kind == "prediction":
            # Final pre-write check: validation/serialization preparation may
            # have crossed expiry or kickoff since the first validation.
            now = self.clock()
            final = validate_dossier(
                data["snapshot"], mode=self.mode, _clock=lambda: now
            )
            if final["status"] != "validated":
                raise ValidationError("dossier_blocked:" + ",".join(final["reasons"]))
            data["validation"] = final
            recorded_at = timestamp(now)
        if records and instant(recorded_at) < instant(records[-1]["recorded_at"]):
            raise ValidationError("clock_moved_backwards")
        record = {
            "schema_version": "1.0.0",
            **FLAGS,
            "sequence": len(records) + 1,
            "record_id": str(uuid.uuid4()),
            "record_type": kind,
            "recorded_at": recorded_at,
            "previous_hash": self._checkpoint(records)["head_hash"],
            "mode": self.mode,
            "data": data,
        }
        record["content_hash"] = digest(record)
        if schema_errors(record, "record"):
            raise ValidationError("record_schema_invalid")
        blob = canonical(record) + b"\n"
        stream.seek(0, os.SEEK_END)
        if stream.tell() + len(blob) > MAX_JOURNAL_BYTES:
            raise ValidationError("journal_capacity_exceeded")
        if stream.write(blob) != len(blob):
            raise ValidationError("journal_partial_write")
        stream.flush()
        os.fsync(stream.fileno())
        directory_fd = os.open(self.directory, os.O_RDONLY | os.O_DIRECTORY)
        try:
            os.fsync(directory_fd)
        finally:
            os.close(directory_fd)
        return copy.deepcopy(record)

    def record_prediction(self, dossier):
        snapshot = copy.deepcopy(dossier)
        with self._locked() as stream:
            records = self._read(stream)
            # Recheck freshness and kickoff after acquiring the lock. The JSON
            # never supplies this clock, and the CLI offers no override.
            now = self.clock()
            validation = validate_dossier(snapshot, mode=self.mode, _clock=lambda: now)
            if validation["status"] != "validated":
                raise ValidationError(
                    "dossier_blocked:" + ",".join(validation["reasons"])
                )
            selected = next(
                (
                    c
                    for c in snapshot["candidates"]
                    if c["id"] == snapshot["decision"]["candidate_id"]
                ),
                None,
            )
            quote = next(
                (
                    e
                    for e in snapshot["evidence"]
                    if selected and e["id"] == selected["quote_id"]
                ),
                None,
            )
            data = {
                "snapshot": snapshot,
                "validation": validation,
                "evaluated_market": selected["market"] if selected else None,
                "evaluated_quote": quote["payload"]["decimal"] if quote else None,
                "decision": copy.deepcopy(snapshot["decision"]),
            }
            return self._append(stream, records, "prediction", data, timestamp(now))

    def record_outcome(self, prediction_id, result):
        result = copy.deepcopy(result)
        if schema_errors(result, "result"):
            raise ValidationError("result_schema_invalid")
        with self._locked() as stream:
            records = self._read(stream)
            prediction = next(
                (
                    r
                    for r in records
                    if r["record_id"] == prediction_id
                    and r["record_type"] == "prediction"
                ),
                None,
            )
            if prediction is None:
                raise ValidationError("prediction_not_found")
            if prediction["mode"] != self.mode:
                raise ValidationError("registry_mode_mismatch")
            now = self.clock()
            evaluation = evaluate(
                prediction, result, mode=self.mode, _clock=lambda: now
            )
            # An unverified/insufficient outcome may be archived as a separate
            # diagnostic attempt, but never becomes a settled win or loss.
            data = {
                "prediction_id": prediction_id,
                "prediction_hash": prediction["content_hash"],
                "result": result,
                "evaluation": evaluation,
            }
            return self._append(stream, records, "outcome", data, timestamp(now))
