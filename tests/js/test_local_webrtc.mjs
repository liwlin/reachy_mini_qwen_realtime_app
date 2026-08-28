import assert from "node:assert/strict";
import test from "node:test";

import localWebRtc from "../../src/reachy_mini_conversation_app/local_control/static/local-webrtc.js";


const { ReachyLocalVideo } = localWebRtc;

class FakeTrack {
  constructor(kind) {
    this.kind = kind;
    this.enabled = true;
    this.stopped = false;
  }

  stop() {
    this.stopped = true;
  }
}

class FakeMediaStream {
  constructor(tracks = []) {
    this.tracks = [...tracks];
  }

  getTracks() {
    return [...this.tracks];
  }

  getVideoTracks() {
    return this.tracks.filter((track) => track.kind === "video");
  }

  getAudioTracks() {
    return this.tracks.filter((track) => track.kind === "audio");
  }
}

class FakeWebSocket {
  static instances = [];

  constructor(url) {
    this.url = url;
    this.readyState = 0;
    this.sent = [];
    FakeWebSocket.instances.push(this);
  }

  open() {
    this.readyState = 1;
    this.onopen?.();
  }

  receive(message) {
    this.onmessage?.({ data: JSON.stringify(message) });
  }

  failWithMalformedJson() {
    this.onmessage?.({ data: "not-json" });
  }

  send(payload) {
    this.sent.push(JSON.parse(payload));
  }

  close() {
    const wasOpen = this.readyState !== 3;
    this.readyState = 3;
    if (wasOpen) this.onclose?.();
  }

  drop() {
    this.readyState = 3;
    this.onclose?.();
  }
}

class FakePeerConnection {
  static instances = [];

  constructor(configuration) {
    this.configuration = configuration;
    this.localDescription = null;
    this.remoteDescription = null;
    this.remoteIce = [];
    this.closed = false;
    this.audioTrack = new FakeTrack("audio");
    this.videoTrack = new FakeTrack("video");
    this.transceivers = [
      { receiver: { track: this.audioTrack }, direction: "sendrecv" },
      { receiver: { track: this.videoTrack }, direction: "sendrecv" },
    ];
    FakePeerConnection.instances.push(this);
  }

  async setRemoteDescription(description) {
    this.remoteDescription = description;
  }

  async createAnswer() {
    return { type: "answer", sdp: "browser-answer" };
  }

  async setLocalDescription(description) {
    this.localDescription = description;
  }

  async addIceCandidate(candidate) {
    this.remoteIce.push(candidate);
  }

  getTransceivers() {
    return this.transceivers;
  }

  emitTrack(track) {
    this.ontrack?.({ track, streams: [new FakeMediaStream([this.audioTrack, this.videoTrack])] });
  }

  emitIce(candidate) {
    this.onicecandidate?.({ candidate });
  }

  connectIce() {
    this.iceConnectionState = "connected";
    this.oniceconnectionstatechange?.();
  }

  emitDataChannel() {
    const channel = { closed: false, close() { this.closed = true; } };
    this.ondatachannel?.({ channel });
    return channel;
  }

  close() {
    this.closed = true;
    this.iceConnectionState = "closed";
  }
}

function fixture() {
  FakeWebSocket.instances = [];
  FakePeerConnection.instances = [];
  const states = [];
  const timers = [];
  const cleared = [];
  const video = {
    srcObject: null,
    playCalls: 0,
    async play() {
      this.playCalls += 1;
    },
  };
  const controller = new ReachyLocalVideo({
    hostname: "reachy-mini.local",
    video,
    onState: (state, detail) => states.push({ state, detail }),
    WebSocketCtor: FakeWebSocket,
    RTCPeerConnectionCtor: FakePeerConnection,
    MediaStreamCtor: FakeMediaStream,
    setTimer(callback, delay) {
      const timer = { callback, delay };
      timers.push(timer);
      return timer;
    },
    clearTimer(timer) {
      cleared.push(timer);
    },
  });
  return { controller, video, states, timers, cleared };
}

function parseSent(socket) {
  return socket.sent;
}

async function flush() {
  await new Promise((resolve) => setImmediate(resolve));
}

async function establishSession(controller) {
  controller.connect();
  const socket = FakeWebSocket.instances[0];
  socket.open();
  socket.receive({ type: "welcome", peerId: "phone-peer" });
  socket.receive({
    type: "list",
    producers: [
      { id: "other-producer", meta: { name: "other" } },
      { id: "producer-1", meta: { name: "reachymini" } },
    ],
  });
  socket.receive({ type: "sessionStarted", sessionId: "session-1" });
  return { socket, peer: FakePeerConnection.instances[0] };
}

test("uses the local GStreamer listener protocol and renders video only", async () => {
  const { controller, video, states } = fixture();
  const { socket, peer } = await establishSession(controller);

  assert.equal(socket.url, "ws://reachy-mini.local:8443");
  assert.deepEqual(parseSent(socket).slice(0, 3), [
    { type: "setPeerStatus", roles: ["listener"], meta: { name: "local-mobile-control" } },
    { type: "list" },
    { type: "startSession", peerId: "producer-1" },
  ]);

  socket.receive({
    type: "peer",
    sessionId: "session-1",
    sdp: { type: "offer", sdp: "robot-offer" },
  });
  await flush();

  assert.deepEqual(peer.remoteDescription, { type: "offer", sdp: "robot-offer" });
  assert.equal(peer.transceivers[0].direction, "recvonly");
  assert.equal(peer.transceivers[1].direction, "recvonly");
  assert.deepEqual(parseSent(socket).at(-1), {
    type: "peer",
    sessionId: "session-1",
    sdp: { type: "answer", sdp: "browser-answer" },
  });

  peer.emitTrack(peer.audioTrack);
  assert.equal(peer.audioTrack.enabled, false);
  assert.equal(video.srcObject, null);

  peer.emitTrack(peer.videoTrack);
  peer.connectIce();
  await flush();

  assert.equal(video.srcObject.getVideoTracks()[0], peer.videoTrack);
  assert.equal(video.srcObject.getAudioTracks().length, 0);
  assert.equal(video.playCalls, 1);
  assert.equal(states.at(-1).state, "live");
  assert.deepEqual(peer.configuration, { iceServers: [] });

  const channel = peer.emitDataChannel();
  assert.equal(channel.closed, true);
});

test("forwards ICE and explicitly ends the local session on disconnect", async () => {
  const { controller, video, states } = fixture();
  const { socket, peer } = await establishSession(controller);
  const remoteIce = { candidate: "remote-candidate", sdpMLineIndex: 0, sdpMid: "video0" };
  socket.receive({ type: "peer", sessionId: "session-1", ice: remoteIce });
  await flush();
  assert.deepEqual(peer.remoteIce, []);
  socket.receive({
    type: "peer",
    sessionId: "session-1",
    sdp: { type: "offer", sdp: "robot-offer" },
  });
  await flush();
  assert.deepEqual(peer.remoteIce, [remoteIce]);

  const localIce = { candidate: "local-candidate", sdpMLineIndex: 0, sdpMid: "video0" };
  peer.emitIce(localIce);
  assert.deepEqual(parseSent(socket).at(-1), {
    type: "peer",
    sessionId: "session-1",
    ice: localIce,
  });

  peer.emitTrack(peer.videoTrack);
  controller.disconnect();

  assert.deepEqual(parseSent(socket).at(-1), { type: "endSession", sessionId: "session-1" });
  assert.equal(peer.closed, true);
  assert.equal(peer.videoTrack.stopped, true);
  assert.equal(video.srcObject, null);
  assert.equal(states.at(-1).state, "stopped");
});

test("ignores malformed signalling and retries unexpected drops with a cap", async () => {
  const { controller, states, timers, cleared } = fixture();
  controller.connect();
  const first = FakeWebSocket.instances[0];
  first.open();
  first.failWithMalformedJson();
  first.drop();

  assert.equal(states.at(-1).state, "reconnecting");
  assert.equal(timers[0].delay, 1000);
  timers[0].callback();
  assert.equal(FakeWebSocket.instances.length, 2);

  const second = FakeWebSocket.instances[1];
  second.open();
  second.drop();
  assert.equal(timers[1].delay, 2000);

  for (let index = 0; index < 5; index += 1) {
    timers.at(-1).callback();
    const socket = FakeWebSocket.instances.at(-1);
    socket.open();
    socket.drop();
  }
  assert.equal(timers.at(-1).delay, 10000);

  controller.disconnect();
  assert.equal(cleared.at(-1), timers.at(-1));
  const count = FakeWebSocket.instances.length;
  timers.at(-1).callback();
  assert.equal(FakeWebSocket.instances.length, count);
  assert.equal(states.at(-1).state, "stopped");
});
