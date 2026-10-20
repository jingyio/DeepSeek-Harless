#!/usr/bin/env python3
"""Five fresh invited members, real native RPC, overlapping scenes and follow-ups.

Default is a network-free preview. Run on the configured Linux service host:
  python scripts/check-five-user-stress.py --execute-real --results /PRIVATE/.local/stress-ID
  python scripts/check-five-user-stress.py --execute-real --resume /PRIVATE/.local/stress-ID --phase delivery

Use --base-url with the configured publicOrigin to include the public website
path; the default remains gateway loopback. Invite administration is always
loopback-only and account credentials are never followed to another origin.
An optional --https-proxy http://127.0.0.1:PORT routes only public HTTPS through
a local CONNECT proxy; the internal invitation API remains a direct request.

Does not start/restart services, rewrite quotas, reset accounting, use existing
members, author presentations, or automatically cancel timed-out requests.
Credentials, synthetic inputs, raw answers and evidence stay in --results (0600).
No fixed provider replies are used. Delivery quality is a narrow synthetic
contract, not a scientific or presentation design quality evaluation.
"""
from __future__ import annotations

import argparse
import concurrent.futures
from datetime import datetime, timezone
import hashlib
import io
import json
import math
import os
from pathlib import Path
import re
import secrets
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
from uuid import uuid4
import zipfile


TERMINAL = {"completed", "failed", "cancelled", "budget_exhausted"}
SCENES = {"paper": "/paper ", "ppt": "/ppt ", "data": "/data ", "chat": ""}
TASK_ID = re.compile(r"[a-f0-9]{32}")
USER_AGENT = "Mozilla/5.0 GeneLoopStress/1.0"


def now():
    return datetime.now(timezone.utc).isoformat()


def epoch(value):
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00")).timestamp()
    except (AttributeError, TypeError, ValueError):
        return None


def load(path):
    return json.loads(Path(path).read_text(encoding="utf-8-sig"))


def save(path, value):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    temporary = path.with_name(path.name + ".tmp")
    with temporary.open("w", encoding="utf-8") as stream:
        os.chmod(temporary, 0o600)
        json.dump(value, stream, ensure_ascii=False, indent=2)
        stream.write("\n")
    os.replace(temporary, path)


def error_code(error):
    # Do not include request bodies, cookies, invitations or credential URLs.
    if isinstance(error, HttpFailure):
        return f"HTTP {error.status}: {error.path}"
    return type(error).__name__ + ": " + str(error)[:220]


class HttpFailure(RuntimeError):
    def __init__(self, status, path, value=None):
        self.status, self.path, self.value = status, path.split("?")[0], value
        super().__init__(f"HTTP {status}: {self.path}")


def normalized_origin(value):
    parsed = urllib.parse.urlsplit(str(value))
    if (parsed.scheme not in {"http", "https"} or not parsed.hostname
            or parsed.username is not None or parsed.password is not None
            or parsed.path not in {"", "/"} or parsed.query or parsed.fragment):
        raise ValueError("Expected an HTTP(S) origin without credentials, path, query or fragment")
    port = parsed.port
    host = parsed.hostname.lower()
    host = "[" + host + "]" if ":" in host else host
    suffix = "" if port is None or port == (443 if parsed.scheme == "https" else 80) else ":" + str(port)
    return parsed.scheme + "://" + host + suffix


def loopback_proxy(value):
    parsed = urllib.parse.urlsplit(str(value))
    if (parsed.scheme != "http" or parsed.hostname != "127.0.0.1" or parsed.port is None
            or not 1 <= parsed.port <= 65535 or parsed.username is not None or parsed.password is not None
            or parsed.path not in {"", "/"} or parsed.query or parsed.fragment):
        raise ValueError("HTTPS proxy must be http://127.0.0.1:PORT without credentials, path, query or fragment")
    return "http://127.0.0.1:" + str(parsed.port)


class SameOriginRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, request, response, code, message, headers, newurl):
        target = urllib.parse.urljoin(request.full_url, newurl)
        if normalized_origin(urllib.parse.urlunsplit((*urllib.parse.urlsplit(target)[:2], "", "", ""))) != normalized_origin(
                urllib.parse.urlunsplit((*urllib.parse.urlsplit(request.full_url)[:2], "", "", ""))):
            raise RuntimeError("Cross-origin redirect blocked; credentials were not forwarded")
        if urllib.parse.urlsplit(target).username is not None or urllib.parse.urlsplit(target).password is not None:
            raise RuntimeError("Redirect credentials are not allowed")
        return super().redirect_request(request, response, code, message, headers, target)


class Client:
    def __init__(self, base, origin, cookie="", *, https_proxy=None):
        self.base, self.origin, self.cookie = base.rstrip("/"), origin, cookie
        if https_proxy and (not self.base.startswith("https://") or normalized_origin(self.base) != normalized_origin(origin)):
            raise ValueError("HTTPS proxy is restricted to this client's configured public HTTPS origin")
        self.https_proxy = loopback_proxy(https_proxy) if https_proxy else None
        # A member has several concurrent conversations. Keep urllib handler
        # instances thread-local; the authenticated account cookie is fixed
        # before workers start and no shared CookieJar is mutated by requests.
        self.local = threading.local()

    def request(self, path, body=None, *, binary=False, timeout=120, headers=None):
        request_headers = {"Origin": self.origin, "User-Agent": USER_AGENT, **(headers or {})}
        if self.cookie:
            request_headers["Cookie"] = self.cookie
        data = None if body is None else body if binary else json.dumps(body).encode()
        if data is not None:
            request_headers["Content-Type"] = "application/octet-stream" if binary else "application/json"
        request = urllib.request.Request(self.base + path, data=data, headers=request_headers)
        if not hasattr(self.local, "opener"):
            proxies = {"https": self.https_proxy} if self.https_proxy else {}
            self.local.opener = urllib.request.build_opener(urllib.request.ProxyHandler(proxies), SameOriginRedirect())
        try:
            with self.local.opener.open(request, timeout=timeout) as response:
                raw = response.read()
                value = raw if binary else json.loads(raw) if raw else None
                return response.status, value, dict(response.headers)
        except urllib.error.HTTPError as error:
            try:
                value = json.loads(error.read())
            except (ValueError, OSError):
                value = None
            raise HttpFailure(error.code, path, value) from None

    def rpc(self, method, request):
        envelope = {"type": "client-request", "rpcId": str(uuid4()), "method": method,
                    "payload": {"args": {"request": request}}}
        _, body, _ = self.request("/api/" + method, envelope)
        result = body.get("result", {})
        if result.get("ok") is not True:
            raise RuntimeError(method + ": " + str(result.get("error", {}).get("code", "unknown")))
        return result.get("value", {})

    def upload(self, session, name, data):
        query = urllib.parse.urlencode({"sessionId": session, "name": name})
        _, answer, _ = self.request("/api/session/uploadFileBinary?" + query, data, binary=True)
        # Binary describes request bytes; the upload response is always JSON.
        if isinstance(answer, bytes):
            answer = json.loads(answer)
        if answer.get("ok") is not True:
            raise RuntimeError("uploadFileBinary rejected")
        return {"type": "file", "receiptId": answer["value"]["receiptId"]}


def cookie_from(headers):
    value = next((v for k, v in headers.items() if k.lower() == "set-cookie"), "")
    cookie = value.split(";", 1)[0]
    if not cookie or "=" not in cookie:
        raise RuntimeError("Registration/login did not issue an account cookie")
    return cookie


def preparation_id(comparison, lane, attempt):
    payload = json.dumps([comparison, lane, attempt], separators=(",", ":")).encode()
    return "compare-" + hashlib.sha256(payload).hexdigest()[:48]


def comparison_turn(output, session, request):
    path = output / "comparisons.json"
    if not path.exists():
        return None
    try:
        turns = load(path).get("turns", [])
    except (OSError, ValueError):
        return None
    return next((row for row in turns if row.get("session_id") == session and row.get("request_id") == request), None)


def discover(output, records):
    """Exact own session/request bindings, including unpublished prepare failures."""
    expected, explicit = {}, set()
    for row in records:
        expected[(row["session_id"], row["request_id"])] = {"record_id": row["id"], "lane": "native"}
        turn = comparison_turn(output, row["session_id"], row["request_id"])
        if turn:
            for name, lane in turn.get("lanes", {}).items():
                if lane.get("session_id"):
                    expected[(lane["session_id"], preparation_id(turn["id"], name, lane.get("attempt", 0)))] = {
                        "record_id": row["id"], "lane": name, "comparison_id": turn["id"]}
                if TASK_ID.fullmatch(str(lane.get("task_id", ""))):
                    explicit.add(lane["task_id"])
    indexed = set(explicit)
    for path in output.glob("task-index-*.json"):
        try:
            indexed.update(tid for tid in load(path).get("tasks", []) if TASK_ID.fullmatch(str(tid)))
        except (OSError, ValueError):
            pass
    result = {}
    for task_id in indexed:
        path = output / "tasks" / task_id / "task-state.json"
        try:
            state = load(path)
        except (OSError, ValueError):
            continue
        binding = expected.get((state.get("session_id"), state.get("request_id")))
        if binding and state.get("task_id") == task_id:
            result[task_id] = {**state, **binding}
    return result


def parse_json_answer(answer):
    answer = re.sub(r"^```(?:json)?\s*\n([\s\S]*?)\n```$", r"\1", answer.strip())
    try:
        return json.loads(answer)
    except ValueError:
        return None


def peak(intervals):
    events = [(start, 1) for start, end in intervals if start is not None and end is not None and end > start]
    events += [(end, -1) for start, end in intervals if start is not None and end is not None and end > start]
    value = maximum = 0
    for _, delta in sorted(events):
        value += delta
        maximum = max(maximum, value)
    return maximum


def upstream_interval(receipt):
    # Both cost gates stamp request_utc_epoch when the upstream call returns.
    # elapsed_seconds measures that call, so the receipt describes [end-dt,end).
    end, elapsed = receipt.get("request_utc_epoch"), receipt.get("elapsed_seconds")
    if (type(end) not in (int, float) or type(elapsed) not in (int, float)
            or not math.isfinite(end) or not math.isfinite(elapsed) or elapsed <= 0):
        return None
    return end - elapsed, end


def expected_data():
    # Independent, standard-library recomputation, never supplied to GeneLoop.
    x = list(range(1, 13))
    y = [2.3, 3.5, 5.8, 6.4, 8.1, 8.7, 10.9, 11.6, 13.2, 15.1, 15.4, 17.3]
    mx, my = sum(x) / len(x), math.fsum(y) / len(y)
    slope = math.fsum((a - mx) * (b - my) for a, b in zip(x, y)) / math.fsum((a - mx) ** 2 for a in x)
    intercept = my - slope * mx
    r_squared = 1 - math.fsum((b - intercept - slope * a) ** 2 for a, b in zip(x, y)) / math.fsum((b - my) ** 2 for b in y)
    return {"n": len(x), "sum_x": sum(x), "sum_y": math.fsum(y), "mean_x": mx, "mean_y": my,
            "slope": slope, "intercept": intercept, "r_squared": r_squared}


class Stress:
    def __init__(self, args, plan, config, directory):
        self.args, self.plan, self.config, self.directory = args, plan, config, directory
        self.lock, self.stop = threading.RLock(), threading.Event()
        self.loopback = f'http://127.0.0.1:{int(config["port"])}'
        self.base = normalized_origin(args.base_url) if args.base_url else self.loopback
        self.origin = config["publicOrigin"]
        self.https_proxy = args.https_proxy if self.base.startswith("https://") and self.base == normalized_origin(self.origin) else None
        self.members = Path(config["membersDir"])
        self.clients, self.credentials = {}, {}
        self.result = load(directory / "results.json") if args.resume else {
            "experiment": directory.name, "started_at": now(), "users": [], "attempts": [], "errors": [],
            "observations": [], "executions": [], "scientific_quality_reviewed": False,
            "configuration": {"model": "deepseek-flash", "reasoning_effort": "off", "application_caps": None,
                              "provider_max_tokens": 393216, "synthetic": True, "protocol": "account gateway + native HTTP RPC"}}
        self.result.setdefault("account_requests", [])

    def persist(self):
        with self.lock:
            save(self.directory / "results.json", self.result)

    def update(self, row, **fields):
        with self.lock:
            row.update(fields)
            self.persist()

    def issue(self, scope, error):
        with self.lock:
            self.result["errors"].append({"at": now(), "scope": scope, "error": error_code(error)})
            self.persist()

    def account_request(self, client, index, path, body):
        metadata = {"user_index": index, "action": path.rsplit("/", 1)[-1], "started_at": now(), "status": "pending"}
        with self.lock:
            self.result["account_requests"].append(metadata)
            self.persist()
        try:
            answer = client.request(path, body)
            self.update(metadata, finished_at=now(), status="http_success", http_status=answer[0])
            return answer
        except Exception as error:
            self.update(metadata, finished_at=now(), status="failed_or_unknown", error=error_code(error),
                        http_status=error.status if isinstance(error, HttpFailure) else None)
            raise

    def account_setup(self):
        if self.args.resume:
            credentials = load(self.directory / "credentials.json")
            if set(credentials) != {str(index) for index in range(1, 6)}:
                raise RuntimeError("Resume requires the original five private diagnostic identities")
            for index in range(1, 6):
                private = credentials[str(index)]
                client = Client(self.base, self.origin, https_proxy=self.https_proxy)
                try:
                    _, _, headers = self.account_request(client, index, "/api/account/login", {
                        "username": private["username"], "password": private["password"]})
                except HttpFailure as error:
                    if error.status != 401:
                        raise
                    # Setup may have stopped between registrations. Reuse only
                    # this run's original invite/identity; never mint another.
                    _, _, headers = self.account_request(client, index, "/api/account/register", {
                        "inviteCode": private["inviteCode"], "username": private["username"],
                        "displayName": f"压力诊断 {index}", "password": private["password"]})
                client.cookie = cookie_from(headers)
                _, profile, _ = client.request("/api/account/me")
                actual = profile.get("user")
                if not actual or actual.get("role") != "member" or actual.get("username") != private["username"]:
                    raise RuntimeError("Resumed member identity mismatch")
                user = next((row for row in self.result["users"] if row["index"] == index), None)
                if user and user["id"] != actual["id"]:
                    raise RuntimeError("Resumed member ID changed")
                if not user:
                    if any(row["id"] == actual["id"] for row in self.result["users"]):
                        raise RuntimeError("Resumed account identities are not distinct")
                    self.result["users"].append({"index": index, "id": actual["id"], "username": actual["username"],
                        "registration_recovered_at": now(), "invite_sha256": hashlib.sha256(private["inviteCode"].encode()).hexdigest(),
                        "output": str(self.members / actual["id"] / "tasks"), "sessions": {}})
                    self.persist()
                private.update(cookie=client.cookie, user_id=actual["id"])
                self.clients[index] = client
            self.credentials = credentials
            save(self.directory / "credentials.json", credentials)
        else:
            admin = Client(self.loopback, self.origin)
            _, response, _ = admin.request("/api/internal/admin", {"action": "invite", "count": 5},
                                         headers={"X-Harless-Admin": self.config["adminToken"]})
            codes = response["codes"]
            if len(codes) != 5 or len(set(codes)) != 5:
                raise RuntimeError("Expected five distinct invitations")
            # Save before registration: a failed setup can be examined without
            # minting new invitations, and no secret enters stdout or results.
            for index, code in enumerate(codes, 1):
                self.credentials[str(index)] = {"username": "stress_" + uuid4().hex[:14] + "_" + str(index),
                    "password": secrets.token_urlsafe(28), "inviteCode": code}
            save(self.directory / "credentials.json", self.credentials)
            for index in range(1, 6):
                private = self.credentials[str(index)]
                client = Client(self.base, self.origin, https_proxy=self.https_proxy)
                _, answer, headers = self.account_request(client, index, "/api/account/register", {
                    "inviteCode": private["inviteCode"], "username": private["username"],
                    "displayName": f"压力诊断 {index}", "password": private["password"]})
                client.cookie = cookie_from(headers)
                _, profile, _ = client.request("/api/account/me")
                user = profile.get("user")
                if not user or user.get("role") != "member" or user.get("username") != private["username"]:
                    raise RuntimeError("New member identity mismatch")
                if user["id"] == "owner" or any(old["id"] == user["id"] for old in self.result["users"]):
                    raise RuntimeError("Account identities are not distinct")
                private.update(cookie=client.cookie, user_id=user["id"])
                self.clients[index] = client
                self.result["users"].append({"index": index, "id": user["id"], "username": user["username"],
                    "registered_at": now(), "invite_sha256": hashlib.sha256(private["inviteCode"].encode()).hexdigest(),
                    "output": str(self.members / user["id"] / "tasks"), "sessions": {}})
                save(self.directory / "credentials.json", self.credentials)
                self.persist()
        def ready(user):
            client = self.clients[user["index"]]
            started = time.monotonic()
            deadline = started + self.args.startup_timeout
            while time.monotonic() < deadline:
                try:
                    status, value, _ = client.request("/api/workspace/ready", timeout=30)
                    if status == 200 and value.get("ready"):
                        break
                except HttpFailure as error:
                    if error.status not in {429, 503}:
                        raise
                time.sleep(self.args.poll_interval)
            else:
                raise RuntimeError("Member cold start timeout")
            self.update(user, cold_start_seconds=round(time.monotonic() - started, 3))
            for scene in SCENES:
                if scene in user["sessions"]:
                    continue
                session = client.rpc("session/create", {})["sessionId"]
                title = self.directory.name + f" U{user['index']} {scene}"
                client.rpc("session/rename", {"sessionId": session, "title": title})
                catalog = client.request("/api/harless/models?" + urllib.parse.urlencode({"session_id": session}))[1]
                model = next((row for row in catalog["models"] if row.get("available") and row.get("model") == "deepseek-flash"), None)
                if not model:
                    raise RuntimeError("DeepSeek Flash is not available for new member")
                client.rpc("session/selectModel", {"sessionId": session, "provider": model["provider"],
                    "model": model["model"], "reasoningEffort": "off"})
                with self.lock:
                    user["sessions"][scene] = {"id": session, "marker": "GLST-" + uuid4().hex[:18],
                                                "memory": secrets.token_hex(7)}
                    self.persist()
        with concurrent.futures.ThreadPoolExecutor(max_workers=5) as executor:
            futures = {executor.submit(ready, user): user for user in self.result["users"]}
            for future, user in [(future, futures[future]) for future in concurrent.futures.as_completed(futures)]:
                try:
                    future.result()
                except Exception as error:
                    self.issue(f"account_setup/U{user['index']}", error)
                    raise

    def own_records(self, user):
        with self.lock:
            return [dict(row) for row in self.result["attempts"] if row["user_index"] == user["index"]]

    def monitor(self):
        while not self.stop.is_set():
            running = []
            try:
                for user in self.result["users"]:
                    for task in discover(Path(user["output"]), self.own_records(user)).values():
                        if task.get("status") == "running":
                            running.append({"task_id": task["task_id"], "user": user["index"],
                                "record_id": task["record_id"], "lane": task["lane"], "scene": task.get("scene"),
                                "started_at": task.get("started_at")})
                sample = {"at": now(), "tasks": running}
                with self.lock:
                    previous = self.result["observations"][-1] if self.result["observations"] else None
                    if not previous or previous["tasks"] != running:
                        self.result["observations"].append(sample)
                        self.persist()
            except Exception as error:
                self.issue("monitor", error)
            self.stop.wait(.5)

    def wait(self, user, row):
        client, output = self.clients[user["index"]], Path(user["output"])
        deadline, last = time.monotonic() + self.args.timeout, None
        while time.monotonic() < deadline:
            turn = comparison_turn(output, row["session_id"], row["request_id"])
            if turn:
                query = urllib.parse.urlencode({"session_id": row["session_id"], "id": turn["id"]})
                try:
                    _, view, _ = client.request("/api/harless/comparisons?" + query, timeout=30)
                except (HttpFailure, OSError) as error:
                    with self.lock:
                        row.setdefault("read_errors", []).append({"at": now(), "error": error_code(error)})
                        self.persist()
                    time.sleep(max(1, self.args.poll_interval))
                    continue
                states = {name: lane.get("status") for name, lane in view.get("lanes", {}).items()}
                if row.get("status") != view["status"] or row.get("lane_states") != states:
                    self.update(row, comparison_id=view["id"], status=view["status"],
                                presentation=view.get("presentation"), lane_states=states)
                for name, lane in view.get("lanes", {}).items():
                    answer = lane.get("answer_display") or lane.get("answer") or ""
                    if answer:
                        with self.lock:
                            if name not in row.setdefault("first_text_at", {}):
                                row["first_text_at"][name] = now()
                if view["status"] in TERMINAL:
                    return view
            else:
                tasks = discover(output, [row])
                if tasks:
                    task = next(iter(tasks.values()))
                    if row.get("status") != task.get("status"):
                        self.update(row, status=task.get("status"))
                    if task.get("status") in TERMINAL:
                        path = output / "tasks" / task["task_id"] / "answer.md"
                        answer = path.read_text(encoding="utf-8") if path.exists() else ""
                        return {"status": task["status"], "presentation": "single", "lanes": {
                            "baseline": {"status": task["status"], "task_id": task["task_id"],
                                         "answer": answer, "artifacts": [], "stats": task.get("stats", {})}}}
            if last != row.get("status"):
                last = row.get("status")
                self.persist()
            time.sleep(self.args.poll_interval)
        self.update(row, timed_out=True, status="unknown_timeout")
        raise TimeoutError("Request remains unverified; not automatically resubmitted or cancelled")

    def foreign_denied(self, user, row, query):
        other = next(member for member in self.result["users"] if member["index"] != user["index"])
        try:
            self.clients[other["index"]].request("/api/harless/comparisons?" + query, binary=True, timeout=30)
        except HttpFailure as error:
            return error.status == 404
        return False

    def collect(self, user, row, view, expected):
        self.update(row, terminal_at=now(), status=view["status"])
        # No partially built dict is shared with the observer/JSON writer.
        # All evidence stays local until published once under the same lock.
        completed_lanes = {}
        for name, lane in view.get("lanes", {}).items():
            answer = lane.get("answer_display") or lane.get("answer") or ""
            details = {key: lane.get(key) for key in ("status", "task_id", "failure", "stats", "output_sha256")}
            details.update(answer=answer, artifacts=[])
            completed_lanes[name] = details
            own = self.directory / "evidence" / row["id"] / name
            save(own / "lane.json", lane)
            checks = {"completed": lane.get("status") == "completed", "nonempty_answer": bool(answer.strip())}
            if row["phase_round"] == "scheduler_initial":
                calls = []
                task_id = str(lane.get("task_id", ""))
                if TASK_ID.fullmatch(task_id):
                    events = Path(user["output"]) / "tasks" / task_id / "events.jsonl"
                    if events.is_file():
                        with events.open(encoding="utf-8") as stream:
                            for line in stream:
                                event = json.loads(line)
                                data = event.get("data", {})
                                if event.get("type") == "tool/call" and str(data.get("name", "")).lower() == "bash":
                                    arguments = data.get("arguments", {})
                                    if isinstance(arguments, str):
                                        try:
                                            arguments = json.loads(arguments)
                                        except ValueError:
                                            arguments = {}
                                    if re.search(r"\bsleep\s+" + str(self.args.sleep_seconds) + r"\b", str(arguments.get("command", ""))):
                                        calls.append({"seq": event.get("seq"), "call_id": data.get("callId"), "time": event.get("time")})
                checks["real_sleep_tool_call"] = bool(calls)
                details["sleep_tool_evidence"] = calls
            if expected["kind"] == "json":
                checks["exact_json"] = parse_json_answer(answer) == expected["value"]
            elif expected["kind"] == "greeting":
                checks["greeting"] = bool(re.search(r"你好|您好|嗨|hello|hi\b", answer, re.I)) and len(answer) < 600
                checks["no_replayed_document"] = not re.search(r"视觉|覆盖对齐|哈希一致|这份资料和|同一份\s*PDF|只读提取结果", answer)
            for artifact in lane.get("artifacts", []):
                if not row.get("comparison_id"):
                    continue
                query = urllib.parse.urlencode({"session_id": row["session_id"], "id": row["comparison_id"],
                                                "lane": name, "file": artifact["id"]})
                _, data, _ = self.clients[user["index"]].request("/api/harless/comparisons?" + query, binary=True)
                digest = hashlib.sha256(data).hexdigest()
                basename = Path(artifact["name"]).name
                destination = own / (artifact["id"] + "-" + re.sub(r"[^\w.\-]", "_", basename))
                destination.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
                destination.write_bytes(data)
                os.chmod(destination, 0o600)
                record = {**artifact, "download_sha256_matches": digest == artifact["sha256"],
                          "download_size_matches": len(data) == artifact["bytes"],
                          "foreign_account_404": self.foreign_denied(user, row, query), "local_file": str(destination)}
                details["artifacts"].append(record)
                if basename.lower().endswith(".pdf"):
                    try:
                        import fitz
                        with fitz.open(stream=data, filetype="pdf") as document:
                            record["pdf_pages"] = len(document)
                            record["extracted_text"] = "\n".join(page.get_text() for page in document)
                    except Exception as error:
                        record["inspection_error"] = error_code(error)
                if basename.lower().endswith(".pptx"):
                    try:
                        with zipfile.ZipFile(io.BytesIO(data)) as archive:
                            slides = [item for item in archive.namelist() if re.fullmatch(r"ppt/slides/slide\d+\.xml", item)]
                            record["pptx_slides"] = len(slides)
                            record["contains_marker"] = expected.get("marker", "").encode() in b"\n".join(archive.read(item) for item in slides)
                    except Exception as error:
                        record["inspection_error"] = error_code(error)
            checks["downloads"] = all(all(item[key] for key in ("download_sha256_matches", "download_size_matches", "foreign_account_404")) for item in details["artifacts"])
            if row.get("comparison_id"):
                query = urllib.parse.urlencode({"session_id": row["session_id"], "id": row["comparison_id"]})
                checks["foreign_result_404"] = self.foreign_denied(user, row, query)
            if expected["kind"] == "delivery":
                artifacts = details["artifacts"]
                checks["has_artifacts"] = bool(artifacts)
                if row["scene"] == "ppt":
                    checks["editable_three_slides"] = any(item.get("pptx_slides") == 3 and item.get("contains_marker") for item in artifacts)
                    checks["three_page_pdf"] = any(item.get("pdf_pages") == 3 for item in artifacts)
                elif row["scene"] == "paper":
                    texts = [item.get("extracted_text", "") for item in artifacts]
                    for item in artifacts:
                        if item["name"].lower().endswith((".md", ".csv", ".txt")):
                            texts.append(Path(item["local_file"]).read_text(encoding="utf-8", errors="replace"))
                    combined = "\n".join(texts)
                    checks["report_marker"] = expected["marker"] in combined
                    checks["known_arithmetic_error_explained"] = "50" in combined and "60" in combined
                    checks["pdf_readable"] = any(item.get("pdf_pages", 0) > 0 for item in artifacts)
                    checks["markdown_delivered"] = any(item["name"].endswith(".md") for item in artifacts)
                elif row["scene"] == "data":
                    checks["pdf_readable"] = any(item.get("pdf_pages", 0) > 0 for item in artifacts)
                    checks["figure_delivered"] = any(item["name"].lower().endswith(".png") for item in artifacts)
                    checks["n12_in_pdf"] = any(re.search(r"\b12\b", item.get("extracted_text", "")) for item in artifacts)
                    summaries = [item for item in artifacts if Path(item["name"]).name == "summary.json"]
                    checks["numeric_summary_delivered"] = len(summaries) == 1
                    truth = expected_data()
                    actual = load(summaries[0]["local_file"]) if len(summaries) == 1 else {}
                    checks["numeric_summary_marker"] = actual.get("marker") == expected["marker"]
                    for key, value in truth.items():
                        observed = actual.get(key)
                        checks["numeric_" + key] = type(observed) in (float, int) and math.isclose(observed, value, rel_tol=1e-7, abs_tol=1e-9)
                    details["numeric_oracle"] = {"expected": truth, "actual": actual}
            details["checks"], details["passed"] = checks, bool(checks) and all(checks.values())
        passed = view["status"] == "completed" and bool(completed_lanes) and all(item["passed"] for item in completed_lanes.values())
        self.update(row, lanes=completed_lanes, passed=passed)

    def attempt(self, user, scene, label, prompt, attachments, expected, *, retry_of=None, barrier=None):
        session = user["sessions"][scene]["id"]
        row = {"id": uuid4().hex, "request_id": str(uuid4()), "user_index": user["index"], "scene": scene,
               "session_id": session, "phase_round": label, "prompt": prompt, "created_at": now(),
               "retry_of": retry_of, "source_sha": self.plan.get("source_sha"), "status": "uploading"}
        with self.lock:
            self.result["attempts"].append(row)
            self.persist()
        try:
            content = [{"type": "text", "text": prompt}]
            sources = []
            for name, data in attachments:
                if Path(name).name != name or "/" in name or "\\" in name:
                    raise RuntimeError("Diagnostic input name must be a basename")
                source = self.directory / "inputs" / row["id"] / name
                source.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
                source.write_bytes(data)
                os.chmod(source, 0o600)
                sources.append({"name": name, "bytes": len(data), "sha256": hashlib.sha256(data).hexdigest(), "local_file": str(source)})
                content.append(self.clients[user["index"]].upload(session, name, data))
            self.update(row, input_files=sources)
            if barrier:
                barrier.wait(timeout=self.args.startup_timeout)
            self.update(row, sent_at=now(), status="submitting")
            accepted = self.clients[user["index"]].rpc("session/prompt", {"sessionId": session,
                "requestId": row["request_id"], "mode": "queue", "clientTimeZone": "Asia/Shanghai", "content": content})
            self.update(row, accepted_at=now(), admission=accepted, status="accepted")
            view = self.wait(user, row)
            self.collect(user, row, view, expected)
        except Exception as error:
            self.update(row, error=error_code(error), passed=False)
            self.issue(f"U{user['index']}/{scene}/{label}", error)
        return row

    def run_one(self, user, scene, phase, barrier):
        session = user["sessions"][scene]
        marker, memory = session["marker"], session["memory"]
        if phase == "scheduler":
            jobs = [
                ("scheduler_initial", SCENES[scene] + f'这是合成并行调度诊断。记住当前对话唯一标记{marker}。请先调用一次Bash执行sleep {self.args.sleep_seconds}，然后读取本轮memory.txt。只输出JSON，字段marker（当前对话标记）和memory（附件memory值）。本轮不生成文件，不需要制作PPT、论文或统计报告。',
                 [("memory.txt", f"Synthetic diagnostic note; not observational data.\nmarker={marker}\nmemory={memory}\n".encode())],
                 {"kind": "json", "value": {"marker": marker, "memory": memory}}),
                ("scheduler_greeting", "你好", [], {"kind": "greeting"}),
                ("scheduler_recall", SCENES[scene] + '本轮没有新附件。请回忆当前对话第一轮的marker与memory，仅输出同样两个字段的JSON，不调用工具，不生成文件；不要把另一对话或另一用户的标记混入。', [],
                 {"kind": "json", "value": {"marker": marker, "memory": memory}}),
            ]
        else:
            jobs = [self.delivery_job(scene, marker)]
        for index, (label, prompt, files, expected) in enumerate(jobs):
            row = self.attempt(user, scene, label, prompt, files, expected, barrier=barrier if index == 0 else None)
            for _ in range(self.args.retry_failed):
                if row.get("passed") or row.get("status") not in TERMINAL:
                    break
                row = self.attempt(user, scene, label, prompt, files, expected, retry_of=row["id"])
            if row.get("status") not in TERMINAL:
                # Unknown submission/timeout may still be active. Do not start
                # another turn or turn an idempotent resend into a new request.
                break

    def delivery_job(self, scene, marker):
        expected = {"kind": "delivery", "marker": marker}
        if scene == "ppt":
            article = f"""Synthetic pilot study — {marker}
This is software-test material, not a real scientific finding.
Eight independent synthetic observations compare a baseline cost of 0.20 USD
with a candidate cost of 0.12 USD. This is a 40% relative cost reduction.
Accuracy changes from 90.4% to 90.0%: a 0.4 percentage-point decline.
No statistical significance or broad deployment benefit has been established.
"""
            prompt = f"/ppt 请只使用本轮article.txt，按完整ppt-master流程自主制作严格3页可编辑英文PPTX和对应3页PDF。第1页问题与合成声明，第2页数据及40%与0.4百分点的区别，第3页局限。全部统一白底、深蓝标题、青色强调、16:9；每页清楚可读，交付前实际导出和检查。封面原样写入唯一标记{marker}。不要让我制作，不联网，不使用历史附件作本文来源。"
            return "delivery", prompt, [("article.txt", article.encode())], expected
        if scene == "paper":
            article = f"""Synthetic manuscript {marker}
P1. This is a synthetic diagnostic, not a real research paper.
P2. Three observed counts are 10, 20, and 30. Their total is 50.
P3. The arithmetic mean is 20. There are three observations.
P4. These synthetic counts do not establish causal effects or generalization.
"""
            prompt = f"/paper 请只读校对本轮manuscript.txt，检查算术与内部一致性。给出段落位置、原句短引、正确值与理由，明确保留原文正确的平均数。交付简短review.md和可下载review.pdf，最多2页，标题原样包含{marker}。无需联网；不讨论附件解析/OCR流程，不修改原件。"
            return "delivery", prompt, [("manuscript.txt", article.encode())], expected
        if scene == "data":
            csv = b"x,y\n1,2.3\n2,3.5\n3,5.8\n4,6.4\n5,8.1\n6,8.7\n7,10.9\n8,11.6\n9,13.2\n10,15.1\n11,15.4\n12,17.3\n"
            study = {"title": marker, "synthetic": True,
                     "description": "Each row is an independent synthetic experimental sample. x is a continuous predictor; y is a continuous outcome. Both are dimensionless. This is synthetic software-test data, not real research.",
                     "report_requirements": {"figure_count": 1}}
            prompt = f"/data 本轮study.csv和study.json是唯一统计来源，忽略历史memory.txt。每行独立，x与y连续且无单位，带截距一元OLS研究线性关联，不推断因果。完成真实统计、1幅scatter_fit PNG、1张关键统计表（包含R-squared）和最多2页英文PDF，标题含{marker}。实际调用deliver_report成功后交付，不把中间回执当成品。每个标题最多两句，正文数字使用工具返回token；允许修复自己的排版。另请实际用Python读取同一份study.csv重算并保存outputs/code/summary.json，可下载JSON字段严格为marker,n,sum_x,sum_y,mean_x,mean_y,slope,intercept,r_squared；marker填{marker}，数字至少8位有效数字，不硬编码推断结果。明确合成数据限制，不汇报附件解析流程。"
            return "delivery", prompt, [("study.csv", csv), ("study.json", json.dumps(study).encode())], expected
        # Ordinary Chat is used for isolated context, not the three delivery
        # comparisons. Its exact JSON result keeps this load case lightweight.
        prompt = f'无需调用工具，不生成文件。当前对话原始marker是{marker}；只输出JSON {{"marker":"{marker}","ok":true}}。'
        return "delivery", prompt, [], {"kind": "json", "value": {"marker": marker, "ok": True}}

    def phase(self, name):
        # 15 distinct scenario conversations enter together. Chat adds another
        # five concurrent sessions, while each completed conversation proceeds
        # immediately into its next round without waiting for the slowest one.
        unresolved = [row["id"] for row in self.result["attempts"]
                      if row.get("sent_at") and row.get("status") not in TERMINAL]
        if unresolved:
            self.issue("phase/" + name, RuntimeError("Prior submitted requests remain unverified; resolve their exact identities before sending new rounds"))
            return
        jobs = [(user, scene) for user in self.result["users"] for scene in SCENES]
        scenario_barrier = threading.Barrier(15)
        with concurrent.futures.ThreadPoolExecutor(max_workers=20) as executor:
            futures = {executor.submit(self.run_one, user, scene, name, scenario_barrier if scene != "chat" else None): (user, scene)
                       for user, scene in jobs}
            for future in concurrent.futures.as_completed(futures):
                user, scene = futures[future]
                try:
                    future.result()
                except Exception as error:
                    self.issue(f"phase/{name}/U{user['index']}/{scene}", error)

    def accounting(self):
        selected = {}
        for user in self.result["users"]:
            for task_id, task in discover(Path(user["output"]), self.own_records(user)).items():
                selected[task_id] = {"user_index": user["index"], "task_id": task_id, "record_id": task["record_id"],
                    "lane": task["lane"], "session_id": task.get("session_id"), "request_id": task.get("request_id"),
                    "status": task.get("status"), "started_at": task.get("started_at"), "finished_at": task.get("finished_at"),
                    "model": task.get("model"), "provider": task.get("provider"), "reasoning_effort": task.get("reasoning_effort"),
                    "scene": task.get("scene"), "failure": task.get("failure"),
                    "stats": {key: value for key, value in task.get("stats", {}).items() if not key.startswith("global_")},
                    "receipts": []}
        fields = {"task_id", "session_id", "request_id", "task_request_id", "global_request_id", "model", "kind",
                  "response_status", "response_usage", "observed_peak_usd", "request_utc_epoch", "elapsed_seconds"}
        ledger = Path(self.args.ledger) if self.args.ledger else self.default_ledger()
        if ledger and ledger.exists():
            with ledger.open(encoding="utf-8") as stream:
                for line in stream:
                    if not line.strip():
                        continue
                    receipt = json.loads(line)
                    if receipt.get("task_id") in selected and "response_status" in receipt:
                        selected[receipt["task_id"]]["receipts"].append({key: value for key, value in receipt.items() if key in fields})
        complete = bool(selected)
        for task in selected.values():
            rows = task["receipts"]
            stats = task["stats"]
            prices = [row.get("observed_peak_usd") for row in rows]
            cost_known = all(type(value) in (float, int) and math.isfinite(value) for value in prices)
            ids = [row.get("global_request_id") for row in rows]
            checks = {"request_count": stats.get("upstream_requests") == len(rows),
                      "usage_complete": stats.get("usage_complete") is True and stats.get("pending_requests", 0) == 0 and stats.get("unknown_usage_requests", 0) == 0,
                      "receipt_ids_unique": None not in ids and len(ids) == len(set(ids)), "cost_known": cost_known}
            observed_cost = stats.get("observed_peak_cost_usd", stats.get("estimated_cost_usd"))
            checks["cost_matches_task"] = cost_known and type(observed_cost) in (float, int) and abs(math.fsum(prices) - observed_cost) <= len(rows) * 0.000000005 + 1e-12
            task.update(accounting_checks=checks, receipt_cost_usd=math.fsum(prices) if cost_known else None)
            complete = complete and all(checks.values())
        run_receipts = [row for task in selected.values() for row in task["receipts"]]
        receipt_ids = [row.get("global_request_id") for row in run_receipts]
        complete = complete and len(receipt_ids) == len(set(receipt_ids)) and None not in receipt_ids
        unmatched = [row["id"] for row in self.result["attempts"] if row.get("sent_at") and not any(task["record_id"] == row["id"] for task in selected.values())]
        complete = complete and not unmatched
        upstream_intervals = [interval for row in run_receipts if (interval := upstream_interval(row)) is not None]
        result = {"tasks": list(selected.values()), "ledger_available": bool(ledger and ledger.exists()),
                  "accounting_complete": complete, "actual_paid_usd": None,
                  "estimated_cost_usd": math.fsum(task["receipt_cost_usd"] for task in selected.values()) if complete else None,
                  "upstream_requests": len(run_receipts), "max_overlapping_upstream_requests": peak(upstream_intervals),
                  "upstream_interval_basis": "[request_utc_epoch - elapsed_seconds, request_utc_epoch); epoch is response completion time",
                  "upstream_requests_without_intervals": len(run_receipts) - len(upstream_intervals),
                  "unmatched_sent_attempts": unmatched,
                  "token_usage": {key: sum(row.get("response_usage", {}).get(key, 0) or 0 for row in run_receipts)
                                  for key in ("prompt_tokens", "prompt_cache_hit_tokens", "prompt_cache_miss_tokens", "completion_tokens", "total_tokens")},
                  "cost_basis": "Own exact session/request-bound tasks, including failed preparation, and matching proxy ledger receipts; not provider invoice"}
        save(self.directory / "accounting.json", result)
        return result

    def default_ledger(self):
        # The service's budget component may expose its checkpoint/ledger path
        # directly. Do not search unrelated users or assume a historic host root.
        for block in (self.plan, self.plan.get("budget", {}), self.config):
            for key in ("ledger", "ledger_path", "budgetLedger"):
                if isinstance(block.get(key), str):
                    return Path(block[key])
        return None

    def summary(self, accounting):
        observations, attempts = self.result["observations"], self.result["attempts"]
        final = {}
        for row in attempts:
            final[(row["user_index"], row["scene"], row["phase_round"])] = row
        scheduler_first = [row for row in final.values() if row["scene"] != "chat" and row["phase_round"] == "scheduler_initial"]
        max_sessions = max((len({task["record_id"] for task in sample["tasks"]}) for sample in observations), default=0)
        max_tasks = max((len(sample["tasks"]) for sample in observations), default=0)
        max_users = max((len({task["user"] for task in sample["tasks"]}) for sample in observations), default=0)
        scheduler_record_ids = {row["id"] for row in scheduler_first}
        scheduler_peak = max((len({task["record_id"] for task in sample["tasks"] if task["record_id"] in scheduler_record_ids}) for sample in observations), default=0)
        scheduler_lanes_peak = max((sum(task["record_id"] in scheduler_record_ids for task in sample["tasks"]) for sample in observations), default=0)
        intervals = [(epoch(task.get("started_at")), epoch(task.get("finished_at"))) for task in accounting["tasks"]]
        overlapping_pairs = []
        for row in scheduler_first:
            tasks = {task["lane"]: task for task in accounting["tasks"] if task["record_id"] == row["id"]}
            a, b = tasks.get("baseline", {}), tasks.get("motif", {})
            starts = [epoch(task.get("started_at")) for task in (a, b)]
            finishes = [epoch(task.get("finished_at")) for task in (a, b)]
            if None not in starts + finishes and max(starts) < min(finishes):
                overlapping_pairs.append(row["id"])
        followups = [row for row in final.values() if row["phase_round"] in {"scheduler_greeting", "scheduler_recall"}]
        interleaved = []
        for row in followups:
            sent = epoch(row.get("sent_at"))
            if sent is None:
                continue
            overlapping = [task["task_id"] for task in accounting["tasks"]
                           if task["record_id"] != row["id"]
                           and epoch(task.get("started_at")) is not None and epoch(task.get("finished_at")) is not None
                           and epoch(task["started_at"]) < sent < epoch(task["finished_at"])]
            if overlapping:
                interleaved.append({"record_id": row["id"], "overlapping_other_tasks": overlapping})
        phases = {execution["phase"] for execution in self.result["executions"]}
        expected_rounds = 60 * bool(phases & {"scheduler", "all"}) + 20 * bool(phases & {"delivery", "all"})
        summary = {"new_registered_users": len(self.result["users"]), "distinct_conversations": sum(len(user["sessions"]) for user in self.result["users"]),
            "attempts": len(attempts), "failed_attempts_preserved": sum(not row.get("passed", False) for row in attempts),
            "latest_rounds": len(final), "latest_rounds_passed": sum(bool(row.get("passed")) for row in final.values()),
            "expected_rounds": expected_rounds, "all_planned_rounds_observed": len(final) == expected_rounds,
            "max_running_tasks_sampled": max_tasks, "max_running_conversations_sampled": max_sessions,
            "max_running_users_sampled": max_users, "initial_scenario_conversations_peak": scheduler_peak,
            "initial_scenario_lanes_peak": scheduler_lanes_peak, "initial_pairs_with_overlapping_lanes": len(overlapping_pairs),
            "max_tasks_from_final_intervals": peak(intervals), "max_overlapping_upstream_requests": accounting["max_overlapping_upstream_requests"],
            "all_final_results_passed": bool(final) and all(row.get("passed") for row in final.values()),
            "five_users_observed_running": max_users == 5, "fifteen_scenarios_observed_running": scheduler_peak == 15,
            "accounting_complete": accounting["accounting_complete"], "estimated_cost_usd": accounting["estimated_cost_usd"],
            "followups_sent_while_other_tasks_running": len(interleaved), "interleaved_followup_evidence": interleaved,
            "quality_scope": "Synthetic isolation, exact values, file structure/download and concurrency; human scientific/design quality not reviewed"}
        summary["pass"] = summary["all_final_results_passed"] and summary["all_planned_rounds_observed"] and summary["five_users_observed_running"] and (not scheduler_first or summary["fifteen_scenarios_observed_running"] and len(overlapping_pairs) == 15 and bool(interleaved)) and summary["accounting_complete"]
        self.update(self.result, summary=summary, finished_at=now())
        return summary


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--execute-real", action="store_true")
    parser.add_argument("--service-plan", type=Path, default=os.environ.get("GENELOOP_SERVICE_CONFIG"))
    parser.add_argument("--base-url", help="Configured publicOrigin or gateway loopback only; default loopback")
    parser.add_argument("--https-proxy", help="Optional http://127.0.0.1:PORT CONNECT proxy for public HTTPS only")
    parser.add_argument("--results", type=Path)
    parser.add_argument("--resume", type=Path, help="Existing private run; reuses only its five test members")
    parser.add_argument("--phase", choices=("scheduler", "delivery", "all", "audit"), default="all")
    parser.add_argument("--timeout", type=float, default=1200, help="Per request; timeout never means success")
    parser.add_argument("--startup-timeout", type=float, default=180)
    parser.add_argument("--poll-interval", type=float, default=1, help="HTTP status polling seconds; local concurrency sampling stays 0.5 s")
    parser.add_argument("--sleep-seconds", type=int, default=20)
    parser.add_argument("--retry-failed", type=int, default=0, help="Explicit new attempts for terminal failures only; defaults to none")
    parser.add_argument("--ledger", type=Path, help="Existing cumulative proxy JSONL; read-only, no reset")
    args = parser.parse_args()
    if args.https_proxy:
        try:
            args.https_proxy = loopback_proxy(args.https_proxy)
        except (TypeError, ValueError):
            parser.error("--https-proxy must be http://127.0.0.1:PORT without credentials, path, query or fragment")
    if args.sleep_seconds < 1 or args.retry_failed < 0 or args.timeout <= 0:
        parser.error("Invalid duration or retry count")
    if not math.isfinite(args.poll_interval) or args.poll_interval <= 0:
        parser.error("--poll-interval must be a finite positive number")
    preview = {"executed": False, "users": 5, "new_accounts_via_invites": True, "conversations_per_user": list(SCENES),
               "initial_concurrent_scenario_conversations": 15, "initial_scene_lanes": 30, "extra_chat_conversations": 5,
               "scheduler_rounds_per_conversation": 3, "delivery_rounds_per_conversation": 1, "phase": args.phase,
               "transport": "explicit origin, checked against service plan at execution" if args.base_url else "gateway loopback",
               "public_https_proxy_requested": bool(args.https_proxy), "admin_proxy": False,
               "user_agent": USER_AGENT, "http_poll_interval_seconds": args.poll_interval,
               "local_task_sample_interval_seconds": .5,
               "real_model": "DeepSeek Flash / Off", "application_budget_and_request_caps": None, "provider_max_tokens": 393216,
               "accounting": "Cumulative ledger remains unchanged; only exact own task receipts are reported", "credentials_printed": False}
    if not args.execute_real:
        print(json.dumps(preview, ensure_ascii=False))
        return 0
    if not args.service_plan or not args.service_plan.is_file():
        parser.error("Set GENELOOP_SERVICE_CONFIG or --service-plan to the existing service plan")
    if args.results and args.resume:
        parser.error("Use --results for new runs or --resume for existing runs")
    directory = args.resume or args.results
    if not directory or not directory.is_absolute() or not args.resume and directory.exists():
        parser.error("--results must be a new absolute private directory; --resume must already exist")
    if args.resume and (not (directory / "credentials.json").is_file() or not (directory / "results.json").is_file()):
        parser.error("Resume credentials or result metadata are missing")
    if args.phase == "audit" and not args.resume:
        parser.error("--phase audit requires --resume and never creates users or calls models")
    os.umask(0o077)
    directory.mkdir(parents=True, exist_ok=bool(args.resume), mode=0o700)
    plan = load(args.service_plan)
    config = load(plan["gateway_config"])
    if args.base_url:
        try:
            selected = normalized_origin(args.base_url)
            allowed = {normalized_origin(config["publicOrigin"]), f'http://127.0.0.1:{int(config["port"])}'}
            if selected not in allowed:
                parser.error("--base-url must be this service's publicOrigin or default gateway loopback")
        except (TypeError, ValueError, KeyError):
            parser.error("--base-url must be a valid configured origin without credentials, path, query or fragment")
    if not config.get("adminToken") or not config.get("membersDir"):
        parser.error("Existing gateway does not support the required private admin/member paths")
    policy = config.get("memberPolicy", {})
    for key in ("budget_usd", "run_budget_usd", "request_limit", "run_request_limit", "max_output_tokens"):
        if policy.get(key) is not None:
            parser.error("Published member policy has an application cap: " + key)
    runner = Stress(args, plan, config, directory)
    runner.result["executions"].append({"at": now(), "phase": args.phase, "source_sha": plan.get("source_sha"),
                                         "resume": bool(args.resume), "base_url": runner.base, "https_proxy": runner.https_proxy,
                                         "admin_transport": "gateway loopback", "admin_proxy": False,
                                         "user_agent": USER_AGENT, "http_poll_interval_seconds": args.poll_interval,
                                         "local_task_sample_interval_seconds": .5})
    runner.persist()
    thread = None
    try:
        if args.phase != "audit":
            runner.account_setup()
            thread = threading.Thread(target=runner.monitor, daemon=True)
            thread.start()
            for phase in (["scheduler", "delivery"] if args.phase == "all" else [args.phase]):
                runner.phase(phase)
    except Exception as error:
        runner.issue("run", error)
    finally:
        runner.stop.set()
        if thread:
            thread.join(timeout=10)
        try:
            accounting = runner.accounting()
            summary = runner.summary(accounting)
        except Exception as error:
            runner.issue("finalization", error)
            summary = {"pass": False, "error": error_code(error), "accounting_complete": False}
            save(directory / "summary.json", summary)
        print(json.dumps({"executed": True, **summary, "private_results": str(directory)}, ensure_ascii=False))
    return 0 if summary.get("pass") else 1


if __name__ == "__main__":
    raise SystemExit(main())
