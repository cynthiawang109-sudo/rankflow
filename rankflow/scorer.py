"""Bounded local inference subprocess with a deadline enforced by the caller."""
from concurrent.futures import ThreadPoolExecutor, TimeoutError
import json
import logging
import os
import subprocess
import sys
from threading import Lock, Timer
from time import monotonic

from .operations import emit


class Scorer:
    def __init__(self, worker="rankflow.scorer"):
        self.worker = worker
        self.executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix="rankflow-scorer")
        self.flight = Lock()
        self.lifecycle = Lock()
        self.process = None
        self.warmed = None
        self.closed = False

    def start(self):
        with self.lifecycle:
            if self.closed:
                raise RuntimeError("Scorer is closed")
            if self.process is None or self.process.poll() is not None:
                if self.process:
                    self.process.stdin.close()
                    self.process.stdout.close()
                self.warmed = None
                env = dict(os.environ, OMP_NUM_THREADS="1", OPENBLAS_NUM_THREADS="1",
                           MKL_NUM_THREADS="1", NUMEXPR_NUM_THREADS="1")
                self.process = subprocess.Popen([sys.executable, "-m", self.worker],
                                                stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                                                env=env)
            return self.process

    def exchange(self, process, path, digest, rows):
        process.stdin.write(json.dumps([str(path), digest, rows]).encode() + b"\n")
        process.stdin.flush()
        reply = process.stdout.readline()
        if not reply:
            raise ValueError("Scorer exited without a response")
        return json.loads(reply)

    def kill(self, process):
        try:
            process.kill()
        except ProcessLookupError:
            pass

    def prepare(self, path, digest):
        process = self.start()
        watchdog = Timer(15, self.kill, args=(process,))
        watchdog.daemon = True
        watchdog.start()
        try:
            self.exchange(process, path, digest, [])
            self.warmed = (process, path, digest)
        except Exception:
            emit("scorer_warm_failed", logging.WARNING, artifact_sha256=digest)
            raise
        finally:
            watchdog.cancel()

    def score(self, path, digest, rows, deadline_ms):
        deadline = monotonic() + deadline_ms / 1000
        if deadline_ms <= 0 or not self.flight.acquire(blocking=False):
            raise TimeoutError("No scoring capacity before deadline")
        try:
            process = self.process
            if self.warmed != (process, path, digest) or process.poll() is not None:
                future = self.executor.submit(self.prepare, path, digest)
                warming = True
            else:
                future = self.executor.submit(self.exchange, process, path, digest, rows)
                warming = False
        except BaseException:
            self.flight.release()
            raise
        future.add_done_callback(lambda _: self.flight.release())
        if warming:
            raise TimeoutError("Model is warming")
        try:
            return future.result(timeout=max(0, deadline - monotonic()))
        except TimeoutError:
            self.kill(process)
            raise

    def close(self):
        with self.lifecycle:
            self.closed = True
            if self.process and self.process.poll() is None:
                self.kill(self.process)
        self.executor.shutdown()
        if self.process:
            self.process.wait()
            self.process.stdin.close()
            self.process.stdout.close()


def limit_memory():
    max_memory = 1024**3
    if os.name != "nt":
        import resource

        resource.setrlimit(resource.RLIMIT_AS, (max_memory, max_memory))
        return

    import ctypes
    from ctypes import wintypes

    class BasicLimits(ctypes.Structure):
        _fields_ = [("process_time", ctypes.c_longlong), ("job_time", ctypes.c_longlong),
                    ("flags", wintypes.DWORD), ("minimum_working_set", ctypes.c_size_t),
                    ("maximum_working_set", ctypes.c_size_t), ("active_processes", wintypes.DWORD),
                    ("affinity", ctypes.c_size_t), ("priority", wintypes.DWORD),
                    ("scheduling", wintypes.DWORD)]

    class ExtendedLimits(ctypes.Structure):
        _fields_ = [("basic", BasicLimits), ("io", ctypes.c_ulonglong * 6),
                    ("process_memory", ctypes.c_size_t), ("job_memory", ctypes.c_size_t),
                    ("peak_process_memory", ctypes.c_size_t), ("peak_job_memory", ctypes.c_size_t)]

    kernel = ctypes.WinDLL("kernel32", use_last_error=True)
    kernel.CreateJobObjectW.argtypes = [ctypes.c_void_p, wintypes.LPCWSTR]
    kernel.CreateJobObjectW.restype = wintypes.HANDLE
    kernel.SetInformationJobObject.argtypes = [wintypes.HANDLE, ctypes.c_int, ctypes.c_void_p, wintypes.DWORD]
    kernel.AssignProcessToJobObject.argtypes = [wintypes.HANDLE, wintypes.HANDLE]
    kernel.GetCurrentProcess.restype = wintypes.HANDLE
    job = kernel.CreateJobObjectW(None, None)
    limits = ExtendedLimits()
    limits.basic.flags = 0x100 | 0x8  # JOB_OBJECT_LIMIT_PROCESS_MEMORY | JOB_OBJECT_LIMIT_ACTIVE_PROCESS
    limits.basic.active_processes = 1
    limits.process_memory = max_memory
    if not job or not kernel.SetInformationJobObject(job, 9, ctypes.byref(limits), ctypes.sizeof(limits)):
        raise ctypes.WinError(ctypes.get_last_error())
    if not kernel.AssignProcessToJobObject(job, kernel.GetCurrentProcess()):
        raise ctypes.WinError(ctypes.get_last_error())


def serve():
    limit_memory()
    from pathlib import Path

    from .data.ingestion import file_hash
    from .strategies import load_model

    cached = None
    for raw in sys.stdin.buffer:
        path, digest, rows = json.loads(raw)
        if cached != (path, digest):
            artifact = Path(path)
            if file_hash(artifact) != digest:
                raise ValueError("Scorer artifact checksum mismatch")
            model = load_model(artifact, threads=1)
            cached = path, digest
        scores = model.score(rows).tolist() if rows else []
        print(json.dumps(scores, allow_nan=False), flush=True)


if __name__ == "__main__":
    serve()
